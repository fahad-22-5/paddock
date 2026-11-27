// Helpers shared by the console sections.
import { h, icon } from '/ui/js/core/dom.js';
import { apiImage, store } from '../api.js';

/** The computer runs macOS (console wording and examples adapt). */
export const isMac = () => store.data?.platform === 'macos';
export const trayWord = () => (isMac() ? 'menu bar icon' : 'tray icon');

export const TYPES = {
  exe: { label: 'Program or file', icon: 'app', group: 'apps' },
  app: { label: 'Installed app', icon: 'app', group: 'apps' },
  folder: { label: 'Folder', icon: 'folder', group: 'folders' },
  url: { label: 'Link', icon: 'globe', group: 'links' },
  shell: { label: 'Command', icon: 'terminal', group: 'commands' },
  keys: { label: 'Keyboard shortcut', icon: 'keyboard', group: 'keys' },
  text: { label: 'Text snippet', icon: 'text', group: 'keys' },
  steps: { label: 'Macro', icon: 'bolt', group: 'keys' },
};

export const isIconPath = (s) => typeof s === 'string' && /\.(ico|png|jpe?g|exe|dll)$/i.test(s);

export function detail(a) {
  switch (a.type) {
    case 'exe': return [a.path, a.args].filter(Boolean).join(' ');
    case 'app': return a.appid;
    case 'folder': return a.path;
    case 'url': return a.url;
    case 'shell': return a.command;
    case 'keys': return a.keys;
    case 'text': return (a.text || '').split('\n')[0];
    case 'steps': return `${a.steps?.length || 0} steps`;
    default: return '';
  }
}

/** Icon art for a shortcut: emoji, the program's own icon, or a type glyph. */
export function art(id, a, cls = 'c-art', { unsaved = false } = {}) {
  const el = h('div', { class: cls });
  if (a.color) el.style.setProperty('--tile-color', a.color);
  if (a.icon && !isIconPath(a.icon)) {
    el.textContent = a.icon;
    return el;
  }
  el.append(icon(TYPES[a.type]?.icon || 'app'));
  let src = null;
  if (unsaved || !id) {
    const p = isIconPath(a.icon) ? a.icon : ['exe', 'folder'].includes(a.type) ? a.path : null;
    if (p) src = `/icon?path=${encodeURIComponent(p)}`;
  } else if (isIconPath(a.icon) || ['exe', 'folder', 'shell'].includes(a.type)) {
    src = `/action-icon/${encodeURIComponent(id)}?v=${encodeURIComponent(a.icon || a.path || a.command || '')}`;
  }
  if (src) apiImage(src).then((url) => { if (url) { el.replaceChildren(h('img', { src: url, alt: '' })); el.classList.add('img'); } });
  return el;
}

/** action id -> page titles it appears on */
export function usage(config) {
  const map = {};
  for (const p of config.pages || []) {
    for (const it of p.items) if (it.kind === 'action') (map[it.action] ||= []).push(p.title);
  }
  return map;
}

export const head = (title, sub, ...actions) =>
  h('div', { class: 'c-head' }, h('h1', null, title), ...actions, sub && h('p', { class: 'sub' }, sub));

export const card = (title, ic, ...children) =>
  h('section', { class: 'c-card' }, h('h2', null, ic && icon(ic), title), ...children);

export function copyButton(text) {
  const b = h('button', { class: 'btn icon', title: 'Copy', 'aria-label': 'Copy' }, icon('copy'));
  b.onclick = async () => {
    try { await navigator.clipboard.writeText(text); b.replaceChildren(icon('check')); setTimeout(() => b.replaceChildren(icon('copy')), 1200); } catch {}
  };
  return b;
}

export function timeAgo(ts) {
  if (!ts) return '–';
  const s = Date.now() / 1000 - ts;
  if (s < 90) return 'just now';
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return new Date(ts * 1000).toLocaleDateString();
}
