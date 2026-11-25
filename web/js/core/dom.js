// Small DOM helpers. No framework: modern Safari has everything we need.
import { ICONS } from './icons.js';

/** h('div', {class: 'x', onclick: fn, dataset: {a: 1}, style: {...}}, ...children) */
export function h(tag, props, ...children) {
  const el = document.createElement(tag);
  if (props) {
    for (const [k, v] of Object.entries(props)) {
      if (v == null || v === false) continue;
      if (k === 'class') el.className = v;
      else if (k === 'style' && typeof v === 'object') Object.assign(el.style, v);
      else if (k === 'dataset') Object.assign(el.dataset, v);
      else if (k === 'html') el.innerHTML = v;
      else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
      else if (k in el && typeof v !== 'string') el[k] = v;
      else el.setAttribute(k, v === true ? '' : v);
    }
  }
  append(el, children);
  return el;
}

function append(el, children) {
  for (const c of children.flat(Infinity)) {
    if (c == null || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
}

/** An inline SVG icon element. */
export function icon(name, cls = '') {
  const tpl = document.createElement('template');
  const def = ICONS[name] || ICONS.app;
  const fill = def.startsWith('F:');
  tpl.innerHTML = `<svg class="i ${fill ? 'fill' : ''} ${cls}" viewBox="0 0 24 24" aria-hidden="true">${fill ? def.slice(2) : def}</svg>`;
  return tpl.content.firstChild;
}

/** Adopt a component stylesheet once. */
const adopted = new Set();
export function css(text) {
  if (adopted.has(text)) return;
  adopted.add(text);
  const sheet = new CSSStyleSheet();
  sheet.replaceSync(text);
  document.adoptedStyleSheets = [...document.adoptedStyleSheets, sheet];
}

/** Touch-friendly tap with pressed feedback. Fires on pointerup inside the element. */
export function onTap(el, fn) {
  let active = null;
  el.addEventListener('pointerdown', (e) => {
    if (e.button !== 0) return;
    active = e.pointerId;
    el.classList.add('pressed');
  });
  const end = () => { active = null; el.classList.remove('pressed'); };
  el.addEventListener('pointerleave', end);
  el.addEventListener('pointercancel', end);
  el.addEventListener('pointerup', (e) => {
    if (active !== e.pointerId) return;
    end();
    fn(e);
  });
  // Keyboard users (hardware keyboard on the device).
  el.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fn(e); } });
}

/** Run a DOM update inside a View Transition when supported and not too frequent. */
export function transition(update) {
  if (!document.startViewTransition || document.hidden) { update(); return Promise.resolve(); }
  const vt = document.startViewTransition(update);
  // A newer transition skips this one; that's expected, not an error.
  vt.ready.catch(() => {});
  vt.updateCallbackDone.catch((e) => console.error(e));
  return vt.finished.catch(() => {});
}

export const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

export function fmtBytes(n, digits = 1) {
  if (n == null || isNaN(n)) return '–';
  const u = ['B', 'KB', 'MB', 'GB', 'TB'];
  let i = 0;
  while (n >= 1000 && i < u.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(n < 10 && i ? digits : 0)} ${u[i]}`;
}

export function fmtRate(bps) {
  if (bps == null) return '–';
  const bits = bps * 8;
  if (bits < 1e3) return `${bits.toFixed(0)} b/s`;
  if (bits < 1e6) return `${(bits / 1e3).toFixed(0)} Kb/s`;
  if (bits < 1e9) return `${(bits / 1e6).toFixed(bits < 1e7 ? 1 : 0)} Mb/s`;
  return `${(bits / 1e9).toFixed(2)} Gb/s`;
}

export function fmtTime(sec) {
  if (sec == null || !isFinite(sec)) return '0:00';
  sec = Math.max(0, Math.floor(sec));
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
  return h ? `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}` : `${m}:${String(s).padStart(2, '0')}`;
}

export const uid = (p = 'i') => `${p}-${Math.random().toString(36).slice(2, 8)}${Date.now().toString(36).slice(-3)}`;

export function debounce(fn, ms) {
  let t;
  const d = (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
  d.flush = (...a) => { clearTimeout(t); fn(...a); };
  d.cancel = () => clearTimeout(t);
  return d;
}

export const storage = {
  get(k, d = null) { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} },
  del(k) { try { localStorage.removeItem(k); } catch {} },
};
