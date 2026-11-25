// Pages: the dock layout. Add, rename, reorder and delete pages; add, resize, reorder
// (drag in the preview) and move items. Saved straight to config.json; the dock updates live.
import { h, icon, uid } from '/ui/js/core/dom.js';
import { confirmDialog, promptDialog, toastError } from '/ui/js/core/ui.js';
import { WIDGETS } from '/ui/js/widgets/index.js';
import { savePages } from '../api.js';
import { TYPES, art, head } from './common.js';
import { openEditor } from './shortcuts.js';

let selectedPage = null;
let selectedItem = null;

export default {
  id: 'pages',
  title: 'Pages',
  icon: 'page',
  render(main, data) {
    const pages = structuredClone(data.config.pages || []);
    const actions = data.config.actions || {};
    if (!pages.find((p) => p.id === selectedPage)) selectedPage = pages[0]?.id || null;
    const page = pages.find((p) => p.id === selectedPage);

    const save = async () => { try { await savePages(pages); } catch (e) { toastError(e); } };

    // ---- page list ----
    const addPage = async () => {
      const title = await promptDialog({ title: 'New page', placeholder: 'Page name', confirm: 'Add' });
      if (!title) return;
      const id = uid('p');
      pages.push({ id, title: title.slice(0, 40), items: [] });
      selectedPage = id;
      save();
    };
    const pageList = h('div', { class: 'c-pagelist' }, pages.map((p, i) => {
      const btn = (ic, label, fn, disabled) => h('button', { class: 'btn icon', title: label, 'aria-label': label, disabled, onclick: (e) => { e.stopPropagation(); fn(); } }, icon(ic));
      return h('div', { class: 'c-pagerow', 'aria-current': String(p.id === selectedPage), onclick: () => { selectedPage = p.id; selectedItem = null; this.render(main.replaceChildren() || main, data); } },
        h('span', { class: 't' }, p.title), h('span', { class: 'n' }, p.items.length),
        btn('up', 'Move up', () => { [pages[i - 1], pages[i]] = [pages[i], pages[i - 1]]; save(); }, i === 0),
        btn('down', 'Move down', () => { [pages[i + 1], pages[i]] = [pages[i], pages[i + 1]]; save(); }, i === pages.length - 1),
        btn('edit', 'Rename', async () => {
          const t = await promptDialog({ title: 'Rename page', value: p.title });
          if (t) { p.title = t.slice(0, 40); save(); }
        }),
        btn('trash', 'Delete', async () => {
          if (pages.length === 1) { toastError(new Error('The dock needs at least one page.')); return; }
          if (!await confirmDialog({ title: `Delete “${p.title}”?`, message: `Its ${p.items.length} item(s) are removed from the layout. Shortcuts themselves are kept.`, confirm: 'Delete', danger: true })) return;
          pages.splice(i, 1);
          save();
        }));
    }), h('button', { class: 'btn', onclick: addPage }, icon('plus'), 'Add page'));

    main.append(head('Pages', 'The layout of the dock. Changes appear on the dock right away. Drag items in the preview to reorder them.'));

    if (!page) {
      main.append(h('div', { class: 'c-pages' }, pageList, h('div', { class: 'c-empty' }, 'No pages yet.')));
      return;
    }

    // ---- add controls ----
    const addWidget = h('select', null, h('option', { value: '' }, '+ Add widget…'),
      Object.values(WIDGETS).map((w) => h('option', { value: w.type }, w.title)));
    addWidget.onchange = () => {
      const w = WIDGETS[addWidget.value];
      if (!w) return;
      const [ww, hh] = w.sizes?.[0] || [2, 2];
      const id = uid('w');
      page.items.push({ id, kind: 'widget', type: w.type, w: ww, h: hh });
      selectedItem = id;
      save();
    };
    const addShortcut = h('select', null, h('option', { value: '' }, '+ Add shortcut tile…'),
      Object.entries(actions).sort((a, b) => a[1].label.localeCompare(b[1].label)).map(([id, a]) => h('option', { value: id }, `${a.label} · ${TYPES[a.type]?.label || a.type}`)));
    addShortcut.onchange = () => {
      if (!addShortcut.value) return;
      const id = uid('a');
      page.items.push({ id, kind: 'action', action: addShortcut.value });
      selectedItem = id;
      save();
    };

    // ---- mini dock preview ----
    const mini = h('div', { class: 'c-mini' });
    let dragId = null;
    for (const it of page.items) {
      const isW = it.kind === 'widget';
      const def = isW ? WIDGETS[it.type] : null;
      const a = !isW ? actions[it.action] : null;
      const el = h('div', {
        class: 'm', draggable: 'true', 'aria-selected': String(it.id === selectedItem), title: 'Click to edit · drag to reorder',
        style: { '--w': isW ? it.w : 1, '--h': isW ? it.h : 1 },
        onclick: () => { selectedItem = it.id; this.render(main.replaceChildren() || main, data); },
      },
      isW ? icon(def?.icon || 'app') : art(it.action, a || { type: 'exe', label: '?' }, 'mart'),
      h('span', null, isW ? (def?.title || it.type) : (a?.label || 'Missing shortcut')),
      isW && h('span', { class: 'k' }, `${it.w} × ${it.h}`));
      el.style.setProperty('--w', isW ? Math.min(8, it.w) : 1);
      el.style.setProperty('--h', isW ? it.h : 1);
      el.addEventListener('dragstart', (e) => { dragId = it.id; el.classList.add('dragging'); e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('text/plain', it.id); });
      el.addEventListener('dragend', () => el.classList.remove('dragging'));
      el.addEventListener('dragover', (e) => { if (dragId && dragId !== it.id) { e.preventDefault(); el.classList.add('drag-over'); } });
      el.addEventListener('dragleave', () => el.classList.remove('drag-over'));
      el.addEventListener('drop', (e) => {
        e.preventDefault();
        el.classList.remove('drag-over');
        const from = page.items.findIndex((x) => x.id === dragId);
        const to = page.items.findIndex((x) => x.id === it.id);
        if (from < 0 || to < 0 || from === to) return;
        const [moved] = page.items.splice(from, 1);
        page.items.splice(to, 0, moved);
        save();
      });
      mini.append(el);
    }
    if (!page.items.length) mini.append(h('div', { class: 'c-muted', style: { gridColumn: '1 / -1', padding: '30px', textAlign: 'center' } }, 'This page is empty. Add a widget or a shortcut tile.'));

    // ---- inspector for the selected item ----
    const inspector = h('div', { class: 'c-inspector' });
    const sel = page.items.find((x) => x.id === selectedItem);
    if (sel) {
      const idx = page.items.indexOf(sel);
      const isW = sel.kind === 'widget';
      const def = isW ? WIDGETS[sel.type] : null;
      const a = !isW ? actions[sel.action] : null;
      const others = pages.filter((p) => p !== page);
      const move = h('select', null, h('option', { value: '' }, 'Move to page…'), others.map((p) => h('option', { value: p.id }, p.title)));
      move.onchange = () => {
        const dest = pages.find((p) => p.id === move.value);
        if (!dest) return;
        page.items.splice(idx, 1);
        dest.items.push(sel);
        selectedPage = dest.id;
        save();
      };
      inspector.append(h('section', { class: 'c-card' },
        h('h2', null, icon(isW ? def?.icon || 'app' : 'bolt'), isW ? def?.title || sel.type : a?.label || 'Shortcut'),
        isW && def?.sizes?.length > 1 && h('div', { class: 'chips' }, def.sizes.map(([w, hh]) => h('button', {
          class: 'chip', 'aria-pressed': String(sel.w === w && sel.h === hh),
          onclick: () => { sel.w = w; sel.h = hh; save(); },
        }, `${w} × ${hh}`))),
        isW && h('p', { class: 'c-muted', style: { margin: 0 } }, 'Size in columns × rows. The dock grid is 8 columns wide in landscape; smaller windows fit widgets automatically.'),
        h('div', { class: 'c-row' },
          h('button', { class: 'btn', disabled: idx === 0, onclick: () => { page.items.splice(idx - 1, 0, page.items.splice(idx, 1)[0]); save(); } }, icon('left'), 'Earlier'),
          h('button', { class: 'btn', disabled: idx === page.items.length - 1, onclick: () => { page.items.splice(idx + 1, 0, page.items.splice(idx, 1)[0]); save(); } }, 'Later', icon('right')),
          others.length ? move : null,
          !isW && a && h('button', { class: 'btn', onclick: () => openEditor(sel.action) }, icon('edit'), 'Edit shortcut'),
          h('div', { class: 'c-grow' }),
          h('button', { class: 'btn danger', onclick: () => { page.items.splice(idx, 1); selectedItem = null; save(); } }, icon('trash'), 'Remove from page'))));
    }

    main.append(h('div', { class: 'c-pages' },
      pageList,
      h('div', null,
        h('div', { class: 'c-toolbar' }, h('h2', { style: { margin: 0, fontSize: '20px', flex: 1 } }, page.title), addWidget, addShortcut),
        h('div', { class: 'c-ipad' }, mini),
        inspector)));
  },
};
