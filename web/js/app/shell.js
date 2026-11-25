// The app shell: swipeable pages, the tab bar, the "Disconnected" banner, and keyed
// rendering of widgets so live widgets survive layout changes.
import { h, icon, onTap, transition, storage, debounce } from '../core/dom.js';
import { toast, toastError } from '../core/ui.js';
import { WIDGETS, mountItem } from '../widgets/index.js';
import { refreshSparklineColors } from '../ui/sparkline.js';
import * as edit from './editmode.js';
import { openSettings } from './settings.js';
import { startRepair } from './pairing.js';
import { FullScreenMode } from './fullscreen.js';

const CONFIG_CACHE = 'paddock.config';
const PAGE_KEY = 'paddock.page';

export class Shell {
  constructor(root, conn) {
    this.root = root;
    this.conn = conn;
    this.config = storage.get(CONFIG_CACHE, { pages: [], actions: {}, appearance: {}, weather: {} });
    this.pages = structuredClone(this.config.pages || []);
    this.mounted = new Map(); // item id -> {el, inst, sig, ctx}
    this.pageEls = new Map(); // page id -> {el, grid, addBtn}
    this.current = storage.get(PAGE_KEY, 0);
    this.editing = false;
    this.saving = false;
    this._incoming = null;
    this.saveLayout = debounce(() => this._save(), 500);
    this._build();
    this.applyAppearance();
    this.renderPages();

    conn.subscribe('config', (cfg) => this._onConfig(cfg));
    conn.addEventListener('state', (e) => this._onState(e.detail));
    conn.addEventListener('retry', (e) => this._retryAt = e.detail);
    this._onState(conn.state);
  }

  // ---- static chrome --------------------------------------------------
  _build() {
    this.pager = h('main', { class: 'pager', 'aria-live': 'off' });
    this.tabs = h('nav', { class: 'tabs', role: 'tablist', 'aria-label': 'Pages' });
    this.editBtn = h('button', { class: 'btn icon', 'aria-label': 'Edit layout', 'aria-pressed': 'false' }, icon('edit'));
    onTap(this.editBtn, () => this.setEditing(!this.editing));
    const settingsBtn = h('button', { class: 'btn icon', 'aria-label': 'Settings' }, icon('settings'));
    onTap(settingsBtn, () => openSettings(this));
    const addPage = h('button', { class: 'tab tab-add', 'aria-label': 'Add page' }, icon('plus'), 'Page');
    onTap(addPage, () => edit.addPage(this));
    this.addPageBtn = addPage;
    this.fullscreen = new FullScreenMode(this);

    this.bannerText = h('small', null, 'Reconnecting…');
    const retry = h('button', { class: 'btn primary' }, 'Retry');
    onTap(retry, () => this.conn.retryNow());
    const repair = h('button', { class: 'btn' }, 'Re-pair');
    onTap(repair, () => startRepair());
    this.banner = h('div', { class: 'banner', role: 'alert' },
      icon('wifioff'), h('div', { class: 'msg' }, h('b', null, 'Disconnected from PC'), this.bannerText), repair, retry);

    this.root.replaceChildren(
      h('div', { class: 'shell' },
        this.pager,
        h('footer', { class: 'tabbar', onpointerdown: () => this.fullscreen.touchedBar() },
          this.tabs,
          h('div', { class: 'tools' }, h('span', { class: 'conn-dot', title: 'Connection' }),
            this.fullscreen.button, this.editBtn, settingsBtn))),
      this.fullscreen.handle,
      this.banner);

    let raf = 0;
    this.pager.addEventListener('scroll', () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        const i = Math.round(this.pager.scrollLeft / Math.max(1, this.pager.clientWidth));
        if (i !== this.current) { this.current = i; storage.set(PAGE_KEY, i); this._syncTabs(); }
      });
    }, { passive: true });
    // Keep the same page in view when the window is resized (Split View, Stage Manager, rotation).
    new ResizeObserver(() => { this.pager.scrollLeft = this.current * this.pager.clientWidth; }).observe(this.pager);

    setInterval(() => this._updateBanner(), 500);
  }

  _onState(state) {
    document.documentElement.dataset.conn = state;
    this._updateBanner();
    if (state === 'unauthorized') this.onUnauthorized?.();
  }

  _updateBanner() {
    if (this.conn.state !== 'down') return;
    const s = Math.max(0, Math.ceil((this._retryAt - Date.now()) / 1000));
    this.bannerText.textContent = this.conn.ws ? 'Connecting…' : s > 0 ? `PC asleep or off the network · retrying in ${s}s` : 'Connecting…';
  }

  // ---- config ---------------------------------------------------------
  _onConfig(cfg) {
    if (this.saving || this.saveLayout.pending) { this._incoming = cfg; return; }
    this.config = cfg;
    storage.set(CONFIG_CACHE, cfg);
    this.pages = structuredClone(cfg.pages || []);
    this.applyAppearance();
    this.renderPages();
  }

  applyAppearance() {
    const accent = this.config.appearance?.accent || '#0a84ff';
    document.documentElement.style.setProperty('--accent', accent);
    refreshSparklineColors();
  }

  /** Mark the layout as changed: re-render now, save to the PC shortly. */
  layoutChanged({ animate = true } = {}) {
    this.saveLayout.pending = true;
    const run = () => this.renderPages();
    animate ? transition(run) : run();
    this.saveLayout();
  }

  async _save() {
    this.saving = true;
    this.saveLayout.pending = false;
    try {
      await this.conn.call('core', 'save_layout', { pages: this.pages });
    } catch (e) {
      toastError(new Error(`Couldn't save the layout: ${e.message}`));
    } finally {
      this.saving = false;
      if (this._incoming) { const c = this._incoming; this._incoming = null; this._onConfig(c); }
    }
  }

  // ---- pages ----------------------------------------------------------
  renderPages() {
    const pages = this.pages.length ? this.pages : [{ id: 'home', title: 'Home', items: [] }];
    const keepItems = new Set();
    const keepPages = new Set();
    const pageNodes = [];

    for (const page of pages) {
      keepPages.add(page.id);
      let p = this.pageEls.get(page.id);
      if (!p) {
        const grid = h('div', { class: 'grid' });
        const addBtn = h('button', { class: 'add-item', 'aria-label': 'Add to page' }, icon('plus'), 'Add');
        onTap(addBtn, () => edit.openAddSheet(this, page.id));
        p = { el: h('section', { class: 'page', 'aria-label': page.title }, grid), grid, addBtn };
        this.pageEls.set(page.id, p);
      }
      p.el.setAttribute('aria-label', page.title);
      const nodes = [];
      for (const item of page.items) {
        keepItems.add(item.id);
        nodes.push(this._itemNode(item, page.id));
      }
      nodes.push(p.addBtn);
      syncChildren(p.grid, nodes);
      pageNodes.push(p.el);
    }
    syncChildren(this.pager, pageNodes);

    for (const [id, m] of this.mounted) {
      if (!keepItems.has(id)) { safeDestroy(m); this.mounted.delete(id); }
    }
    for (const [id, p] of this.pageEls) if (!keepPages.has(id)) { p.el.remove(); this.pageEls.delete(id); }

    this._renderTabs(pages);
    this.current = Math.min(this.current, pages.length - 1);
    this.pager.scrollLeft = this.current * this.pager.clientWidth;
    this._syncTabs();
  }

  _itemNode(item, pageId) {
    const sig = itemSignature(item, this.config.actions);
    let m = this.mounted.get(item.id);
    if (m && m.sig !== sig) { safeDestroy(m); m = null; }
    if (!m) {
      const el = h('div', { class: 'item', dataset: { id: item.id, kind: item.kind } });
      const ctx = this._ctx(item);
      let inst = null;
      try {
        inst = mountItem(el, item, ctx);
      } catch (e) {
        console.error(e);
        el.replaceChildren(h('div', { class: 'card' }, h('div', { class: 'empty-note' }, `Widget failed: ${e.message}`)));
      }
      edit.addItemChrome(this, el);
      m = { el, inst, sig, ctx };
      this.mounted.set(item.id, m);
    }
    const optsChanged = m.item && JSON.stringify(m.item.options || null) !== JSON.stringify(item.options || null);
    m.item = item;
    m.pageId = pageId;
    if (optsChanged) m.inst?.update?.(item);
    const def = item.kind === 'widget' ? WIDGETS[item.type] : null;
    m.el.dataset.w = item.kind === 'action' ? 1 : item.w ?? def?.sizes?.[0]?.[0] ?? 2;
    m.el.dataset.h = item.kind === 'action' ? 1 : item.h ?? def?.sizes?.[0]?.[1] ?? 2;
    m.el.style.viewTransitionName = `it-${item.id.replace(/[^\w-]/g, '_')}`;
    m.ctx.item = item;
    return m.el;
  }

  _ctx(item) {
    const shell = this;
    const unsubs = [];
    return {
      item,
      conn: this.conn,
      get config() { return shell.config; },
      call: (mod, act, args, timeout) => this.conn.call(mod, act, args, timeout),
      fire: (mod, act, args) => this.conn.fire(mod, act, args),
      subscribe(topic, fn) { const u = shell.conn.subscribe(topic, fn); unsubs.push(u); return u; },
      saveOptions(options) {
        // Persist per-widget options (e.g. which audio app is pinned) into the layout.
        for (const p of shell.pages) for (const it of p.items) if (it.id === this.item.id) it.options = { ...it.options, ...options };
        shell.saveLayout.pending = true;
        shell.saveLayout();
      },
      toast, toastError,
      _cleanup: () => unsubs.splice(0).forEach((u) => u()),
    };
  }

  _renderTabs(pages) {
    const nodes = pages.map((p, i) => {
      const b = h('button', { class: 'tab', role: 'tab', dataset: { page: p.id } }, h('span', { class: 'dot' }), p.title);
      onTap(b, () => {
        if (this.editing && i === this.current) edit.openPageSheet(this, p.id);
        else this.goTo(i);
      });
      return b;
    });
    nodes.push(this.addPageBtn);
    this.tabs.replaceChildren(...nodes);
  }

  _syncTabs() {
    [...this.tabs.querySelectorAll('.tab[role=tab]')].forEach((t, i) => {
      t.setAttribute('aria-selected', String(i === this.current));
      if (i === this.current) t.scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: 'smooth' });
    });
    this.fullscreen?.syncDots();
  }

  goTo(i, smooth = true) {
    this.current = i;
    storage.set(PAGE_KEY, i);
    this.pager.scrollTo({ left: i * this.pager.clientWidth, behavior: smooth ? 'smooth' : 'instant' });
    this._syncTabs();
  }

  setEditing(on) {
    this.editing = on;
    this.fullscreen.setPinned(on);
    transition(() => {
      if (on) document.documentElement.dataset.edit = '';
      else delete document.documentElement.dataset.edit;
      this.editBtn.setAttribute('aria-pressed', String(on));
    });
    if (!on && this.saveLayout.pending) this.saveLayout.flush();
    if (on) toast('Drag ⠿ to reorder · tap ••• for size and options · tap the page name to rename it');
  }

  currentPage() { return this.pages[this.current]; }
}

function itemSignature(item, actions) {
  if (item.kind === 'action') return `a:${item.action}:${JSON.stringify(actions?.[item.action] || null)}`;
  return `w:${item.type}`; // options changes are passed to inst.update() instead of remounting
}

function safeDestroy(m) {
  try { m.inst?.destroy?.(); } catch (e) { console.error(e); }
  m.ctx?._cleanup();
  m.el.remove();
}

/** Make parent's children exactly `nodes`, in order, moving as few nodes as possible. */
function syncChildren(parent, nodes) {
  nodes.forEach((n, i) => { if (parent.children[i] !== n) parent.insertBefore(n, parent.children[i] || null); });
  while (parent.children.length > nodes.length) parent.lastElementChild.remove();
}
