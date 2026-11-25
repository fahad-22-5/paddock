// Action tiles: launcher shortcuts (programs, links, folders, commands) and macros
// (keyboard shortcuts, text snippets). Tapping one asks the PC to run the action by id;
// the PC only runs actions defined in its config.json.
import { h, icon, onTap } from '../core/dom.js';

const TYPE_ICON = { exe: 'app', app: 'app', url: 'globe', folder: 'folder', shell: 'terminal', keys: 'keyboard', text: 'text', steps: 'bolt' };
const iconCache = new Map(); // `${id}:${sig}` -> Promise<objectURL|null>

function loadIcon(token, id, a) {
  const key = `${id}:${a.type}:${a.label}`;
  if (!iconCache.has(key)) {
    iconCache.set(key, fetch(`/api/actions/icon/${encodeURIComponent(id)}`, { headers: { authorization: `Bearer ${token}` } })
      .then((r) => (r.ok ? r.blob() : null))
      .then((b) => (b ? URL.createObjectURL(b) : null))
      .catch(() => { iconCache.delete(key); return null; }));
  }
  return iconCache.get(key);
}

/** The square artwork for an action: emoji, the program's own icon, or a type glyph. */
export function actionArt(shellOrCtx, id, a, small = false) {
  const art = h('span', { class: small ? '' : 'art' });
  if (a.color) art.style.setProperty('--tile-color', a.color);
  if (a.icon) {
    art.textContent = a.icon;
  } else {
    art.append(icon(TYPE_ICON[a.type] || 'app'));
    if (a.has_icon) {
      loadIcon(shellOrCtx.conn.token, id, a).then((url) => {
        if (!url) return;
        art.replaceChildren(h('img', { src: url, alt: '' }));
        art.classList.add('has-img');
      });
    }
  }
  return art;
}

export function mountActionTile(el, item, ctx) {
  const id = item.action;
  const a = ctx.config.actions?.[id];
  if (!a) {
    el.append(h('div', { class: 'tile' }, h('span', { class: 'label muted' }, 'Missing action'), h('span', { class: 'sub' }, id)));
    return null;
  }
  const sub = a.type === 'keys' ? a.keys : a.type === 'url' ? (safeHost(a.url) || '') : '';
  const tile = h('button', { class: 'tile', 'aria-label': a.label },
    actionArt(ctx, id, a), h('span', { class: 'label' }, a.label), sub && h('span', { class: 'sub' }, sub));
  el.append(tile);

  let busy = false;
  onTap(tile, async () => {
    if (busy) return;
    busy = true;
    tile.classList.remove('ok', 'fail');
    try {
      await ctx.call('actions', 'run', { id });
      void tile.offsetWidth;
      tile.classList.add('ok');
    } catch (e) {
      void tile.offsetWidth;
      tile.classList.add('fail');
      ctx.toastError(e);
    } finally {
      busy = false;
    }
  });
  return null;
}

function safeHost(u) { try { return new URL(u).host; } catch { return ''; } }
