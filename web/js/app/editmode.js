// Edit mode: add / remove / resize / reorder items, manage pages, create shortcuts.
// Every change edits shell.pages and calls shell.layoutChanged(), which re-renders and
// saves the layout to config.json on the PC.
import { h, icon, onTap, uid } from '../core/dom.js';
import { confirmDialog, promptDialog, sheet, toastError } from '../core/ui.js';
import { WIDGETS } from '../widgets/index.js';
import { actionArt } from '../widgets/action-tile.js';

function find(shell, id) {
  for (const page of shell.pages) {
    const index = page.items.findIndex((it) => it.id === id);
    if (index >= 0) return { page, index, item: page.items[index] };
  }
  return null;
}

// ---- per-item chrome ---------------------------------------------------
export function addItemChrome(shell, el) {
  const btn = (cls, ic, label) => h('button', { class: `edit-btn ${cls}`, 'aria-label': label }, h('span', null, icon(ic)));
  const remove = btn('edit-remove', 'close', 'Remove');
  const more = btn('edit-more', 'more', 'Options');
  const grip = btn('edit-grip', 'grip', 'Drag to reorder');
  onTap(remove, () => removeItem(shell, el.dataset.id));
  onTap(more, () => openItemSheet(shell, el.dataset.id));
  enableDrag(shell, el, grip);
  el.append(remove, grip, more);
}

function removeItem(shell, id) {
  const f = find(shell, id);
  if (!f) return;
  f.page.items.splice(f.index, 1);
  shell.layoutChanged();
}

// ---- drag to reorder (pointer events: touch, Pencil, mouse) -------------
function enableDrag(shell, el, grip) {
  let drag = null;
  grip.addEventListener('pointerdown', (e) => {
    if (e.button !== 0 || !shell.editing) return;
    e.preventDefault();
    try { grip.setPointerCapture(e.pointerId); } catch {}
    const r = el.getBoundingClientRect();
    drag = { id: e.pointerId, sx: e.clientX, sy: e.clientY, left: r.left, top: r.top, lastSwap: 0 };
    el.classList.add('dragging');
  });
  grip.addEventListener('pointermove', (e) => {
    if (!drag || e.pointerId !== drag.id) return;
    position(e);
    const now = performance.now();
    if (now - drag.lastSwap < 120) return;
    const target = document.elementsFromPoint(e.clientX, e.clientY)
      .map((n) => n.closest?.('.item')).find((n) => n && n !== el && n.parentElement === el.parentElement);
    if (!target) return;
    drag.lastSwap = now;
    const grid = el.parentElement;
    const kids = [...grid.children];
    const before = new Map(kids.map((k) => [k, k.getBoundingClientRect()]));
    const from = kids.indexOf(el), to = kids.indexOf(target);
    // Move the *other* items around the dragged one: moving the dragged element itself
    // would detach it for a moment and the browser would drop our pointer capture.
    if (from < to) for (const k of kids.slice(from + 1, to + 1)) grid.insertBefore(k, el);
    else for (const k of kids.slice(to, from).reverse()) grid.insertBefore(k, el.nextSibling);
    for (const k of kids) {
      if (k === el) continue;
      const a = before.get(k), b = k.getBoundingClientRect();
      if (a.left !== b.left || a.top !== b.top) {
        k.animate([{ translate: `${a.left - b.left}px ${a.top - b.top}px` }, { translate: '0 0' }], { duration: 220, easing: 'cubic-bezier(.2,.8,.2,1)' });
      }
    }
    position(e);
  });
  const end = (e) => {
    if (!drag || e.pointerId !== drag.id) return;
    drag = null;
    el.classList.remove('dragging');
    const from = el.getBoundingClientRect();
    el.style.translate = '';
    const to = el.getBoundingClientRect();
    el.animate([{ translate: `${from.left - to.left}px ${from.top - to.top}px` }, { translate: '0 0' }], { duration: 240, easing: 'cubic-bezier(.2,.8,.2,1)' });
    // Read the new order back from the DOM.
    const f = find(shell, el.dataset.id);
    if (!f) return;
    const order = [...el.parentElement.querySelectorAll(':scope > .item')].map((n) => n.dataset.id);
    f.page.items.sort((a, b) => order.indexOf(a.id) - order.indexOf(b.id));
    shell.layoutChanged({ animate: false });
  };
  grip.addEventListener('pointerup', end);
  grip.addEventListener('pointercancel', end);

  function position(e) {
    // Where the item sits in the layout right now, without our translate.
    el.style.translate = '';
    const r = el.getBoundingClientRect();
    const x = drag.left + (e.clientX - drag.sx) - r.left;
    const y = drag.top + (e.clientY - drag.sy) - r.top;
    el.style.translate = `${x}px ${y}px`;
  }
}

// ---- item options --------------------------------------------------------
export function openItemSheet(shell, id) {
  const f = find(shell, id);
  if (!f) return;
  const { item } = f;
  const def = item.kind === 'widget' ? WIDGETS[item.type] : null;
  const action = item.kind === 'action' ? shell.config.actions[item.action] : null;
  const title = def?.title || action?.label || 'Item';

  sheet(title, (body, close) => {
    if (def?.sizes?.length > 1) {
      const chips = h('div', { class: 'chips' });
      const draw = () => chips.replaceChildren(...def.sizes.map(([w, hh]) => {
        const c = h('button', { class: 'chip', 'aria-pressed': String(item.w === w && item.h === hh) }, `${w} × ${hh}`);
        onTap(c, () => { item.w = w; item.h = hh; draw(); shell.layoutChanged(); });
        return c;
      }));
      draw();
      body.append(h('div', { class: 'section-label' }, 'Size (columns × rows)'), chips);
    }

    const others = shell.pages.filter((p) => p !== f.page);
    if (others.length) {
      body.append(h('div', { class: 'section-label' }, 'Move to page'),
        h('div', { class: 'list' }, others.map((p) => {
          const row = h('button', { class: 'list-row' }, icon('page'), h('div', { class: 'grow' }, p.title), icon('right'));
          onTap(row, () => {
            const cur = find(shell, id);
            cur.page.items.splice(cur.index, 1);
            p.items.push(item);
            close();
            shell.layoutChanged();
          });
          return row;
        })));
    }

    const actions = h('div', { class: 'list' });
    if (action?.origin === 'ipad') {
      const editRow = h('button', { class: 'list-row' }, icon('edit'), h('div', { class: 'grow' }, 'Edit shortcut'));
      onTap(editRow, () => { close(); openActionForm(shell, null, item.action); });
      const delRow = h('button', { class: 'list-row', style: { color: 'var(--danger)' } }, icon('trash'),
        h('div', { class: 'grow' }, 'Delete shortcut everywhere'));
      onTap(delRow, async () => {
        if (!await confirmDialog({ title: `Delete “${action.label}”?`, message: 'Removes the shortcut and every tile that uses it.', confirm: 'Delete', danger: true })) return;
        try { await shell.conn.call('actions', 'delete', { id: item.action }); close(); } catch (e) { toastError(e); }
      });
      actions.append(editRow, delRow);
    }
    const rm = h('button', { class: 'list-row', style: { color: 'var(--danger)' } }, icon('close'), h('div', { class: 'grow' }, 'Remove from page'));
    onTap(rm, () => { close(); removeItem(shell, id); });
    actions.append(rm);
    body.append(actions);
  });
}

// ---- adding --------------------------------------------------------------
export function openAddSheet(shell, pageId) {
  const page = shell.pages.find((p) => p.id === pageId) || shell.currentPage();
  if (!page) return;
  const add = (item) => { page.items.push(item); shell.layoutChanged(); };

  sheet(`Add to “${page.title}”`, (body, close) => {
    body.append(h('div', { class: 'section-label' }, 'Widgets'),
      h('div', { class: 'list' }, Object.values(WIDGETS).map((w) => {
        const row = h('button', { class: 'list-row' },
          h('span', { class: 'ico' }, icon(w.icon || 'app')),
          h('div', { class: 'grow' }, w.title, h('small', null, w.description || '')),
          icon('plus'));
        onTap(row, () => {
          const [ww, hh] = w.sizes?.[0] || [2, 2];
          add({ id: uid('w'), kind: 'widget', type: w.type, w: ww, h: hh });
          close();
        });
        return row;
      })));

    const actions = Object.entries(shell.config.actions || {});
    const onPage = new Set(page.items.filter((i) => i.kind === 'action').map((i) => i.action));
    body.append(h('div', { class: 'section-label' }, 'Shortcuts'));
    const newRow = h('button', { class: 'list-row' }, h('span', { class: 'ico' }, icon('plus')),
      h('div', { class: 'grow' }, 'New shortcut…', h('small', null, 'Keyboard shortcut, text snippet or web link')));
    onTap(newRow, () => { close(); openActionForm(shell, page.id); });
    body.append(h('div', { class: 'list' }, newRow, actions.map(([id, a]) => {
      const row = h('button', { class: 'list-row' }, h('span', { class: 'ico' }, actionArt(shell, id, a, true)),
        h('div', { class: 'grow' }, a.label, h('small', null, describe(a) + (onPage.has(id) ? ' · already on this page' : ''))),
        icon('plus'));
      onTap(row, () => { add({ id: uid('a'), kind: 'action', action: id }); close(); });
      return row;
    })));
    body.append(h('p', { class: 'muted', style: { fontSize: '14px', margin: 0 } },
      'Programs, folders and commands are added in config.json on the PC, so nothing can run on your PC that you didn’t set up there.'));
  });
}

export function describe(a) {
  return ({ exe: 'Program', app: 'App', url: a.url || 'Web link', folder: 'Folder', shell: 'Command', keys: a.keys ? `Keys · ${a.keys}` : 'Keyboard shortcut',
    text: 'Text snippet', steps: 'Macro' })[a.type] || a.type;
}

// ---- shortcuts created from the device ---------------------------------------
const KEY_EXAMPLES = ['ctrl+shift+m', 'win+shift+s', 'ctrl+c', 'alt+tab', 'win+d', 'media_play_pause', 'ctrl+alt+delete'];

export function openActionForm(shell, pageId, editId = null) {
  const existing = editId ? shell.config.actions[editId] : null;
  let type = existing?.type || 'keys';
  const label = h('input', { class: 'field', placeholder: 'Label, e.g. Mute Teams', value: existing?.label || '', maxlength: 40 });
  const value = h('textarea', { class: 'field', rows: 3 });
  const emoji = h('input', { class: 'field', placeholder: 'Icon: an emoji (optional)', value: existing?.icon || '', maxlength: 8, style: { width: '100%' } });
  const hint = h('p', { class: 'muted', style: { margin: 0, fontSize: '14px' } });
  const examples = h('div', { class: 'chips' });
  const typeChips = h('div', { class: 'chips' });
  const types = [['keys', 'Keyboard shortcut'], ['text', 'Text snippet'], ['url', 'Web link']];
  const values = { keys: existing?.keys || '', text: existing?.text || '', url: existing?.url || '' };

  const draw = () => {
    typeChips.replaceChildren(...types.map(([t, l]) => {
      const c = h('button', { class: 'chip', 'aria-pressed': String(t === type), disabled: !!existing && t !== type }, l);
      onTap(c, () => { values[type] = value.value; type = t; draw(); });
      return c;
    }));
    value.value = values[type];
    value.rows = type === 'text' ? 5 : 1;
    value.placeholder = { keys: 'ctrl+shift+m', text: 'Text to type on the PC', url: 'https://…' }[type];
    hint.textContent = {
      keys: 'Join keys with +. Modifiers: ctrl, shift, alt, win. Also f1–f24, enter, esc, tab, space, arrows, media keys. Several combos in a row: separate with a space.',
      text: 'Typed into whatever window has focus on the PC.',
      url: 'Opens in your default browser on the PC. Only http and https links.',
    }[type];
    examples.replaceChildren(...(type === 'keys' ? KEY_EXAMPLES.map((k) => {
      const c = h('button', { class: 'chip' }, k);
      onTap(c, () => { value.value = k; });
      return c;
    }) : []));
  };
  draw();

  sheet(existing ? 'Edit shortcut' : 'New shortcut', (body, close) => {
    const save = h('button', { class: 'btn primary' }, existing ? 'Save' : 'Create');
    onTap(save, async () => {
      const spec = { type, label: label.value.trim(), icon: emoji.value.trim(), [type]: value.value.trim() };
      if (!spec.label) { label.focus(); return; }
      save.disabled = true;
      try {
        if (existing) {
          await shell.conn.call('actions', 'update', { id: editId, ...spec });
        } else {
          const id = await shell.conn.call('actions', 'create', spec);
          const page = shell.pages.find((p) => p.id === pageId) || shell.currentPage();
          // The new action arrives with the next config update; add its tile once it exists.
          const addTile = () => { page.items.push({ id: uid('a'), kind: 'action', action: id }); shell.layoutChanged(); };
          if (shell.config.actions[id]) addTile();
          else {
            const off = shell.conn.subscribe('config', (cfg) => { if (cfg.actions[id]) { off(); queueMicrotask(addTile); } });
          }
        }
        close();
      } catch (e) { toastError(e); save.disabled = false; }
    });
    body.append(typeChips, label, value, examples, hint, emoji, save);
  });
}

// ---- pages -------------------------------------------------------------------
export async function addPage(shell) {
  const title = await promptDialog({ title: 'New page', placeholder: 'Page name', confirm: 'Add' });
  if (!title) return;
  shell.pages.push({ id: uid('p'), title: title.slice(0, 40), items: [] });
  shell.layoutChanged();
  requestAnimationFrame(() => shell.goTo(shell.pages.length - 1));
}

export function openPageSheet(shell, pageId) {
  const idx = shell.pages.findIndex((p) => p.id === pageId);
  const page = shell.pages[idx];
  if (!page) return;
  sheet(page.title, (body, close) => {
    const row = (ic, text, fn, danger) => {
      const b = h('button', { class: 'list-row', style: danger ? { color: 'var(--danger)' } : null }, icon(ic), h('div', { class: 'grow' }, text));
      onTap(b, fn);
      return b;
    };
    const move = (d) => {
      const j = idx + d;
      if (j < 0 || j >= shell.pages.length) return;
      [shell.pages[idx], shell.pages[j]] = [shell.pages[j], shell.pages[idx]];
      close();
      shell.layoutChanged();
      requestAnimationFrame(() => shell.goTo(j));
    };
    body.append(h('div', { class: 'list' },
      row('edit', 'Rename', async () => {
        close();
        const t = await promptDialog({ title: 'Rename page', value: page.title });
        if (t) { page.title = t.slice(0, 40); shell.layoutChanged(); }
      }),
      idx > 0 && row('left', 'Move left', () => move(-1)),
      idx < shell.pages.length - 1 && row('right', 'Move right', () => move(1)),
      shell.pages.length > 1 && row('trash', 'Delete page', async () => {
        close();
        if (!await confirmDialog({ title: `Delete “${page.title}”?`, message: `Its ${page.items.length} item(s) will be removed from the layout.`, confirm: 'Delete', danger: true })) return;
        shell.pages.splice(shell.pages.indexOf(page), 1);
        shell.current = Math.max(0, shell.current - 1);
        shell.layoutChanged();
      }, true)));
  });
}
