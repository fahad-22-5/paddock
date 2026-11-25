// PadDock console: manage shortcuts, pages, devices and settings from the PC.
import { h, icon } from '/ui/js/core/dom.js';
import { toastError } from '/ui/js/core/ui.js';
import { api, consoleKey, startPolling, store } from './api.js';
import overview from './sections/overview.js';
import shortcuts from './sections/shortcuts.js';
import pages from './sections/pages.js';
import devices from './sections/devices.js';
import settings from './sections/settings.js';

const SECTIONS = [overview, shortcuts, pages, devices, settings];
const root = document.getElementById('app');

const main = h('main', { class: 'c-main' });
const navButtons = new Map();
const statusLine = h('div', null, h('span', { class: 'dot' }), 'Running');
const statusSub = h('div', { class: 'c-muted' }, '');
const status = h('div', { class: 'c-status' }, statusLine, statusSub);

function current() {
  const id = location.hash.replace(/^#\/?/, '');
  return SECTIONS.find((s) => s.id === id) || SECTIONS[0];
}

export function go(id) {
  location.hash = `/${id}`;
}

function render() {
  const sec = current();
  for (const [id, b] of navButtons) b.setAttribute('aria-current', id === sec.id ? 'page' : 'false');
  if (!store.data) return;
  const scroll = main.scrollTop;
  const sameSection = main.dataset.section === sec.id;
  main.dataset.section = sec.id;
  main.replaceChildren();
  try {
    sec.render(main, store.data, { go, reload: () => store.load() });
  } catch (e) {
    console.error(e);
    main.append(h('div', { class: 'c-empty' }, `Something went wrong: ${e.message}`));
  }
  if (sameSection) main.scrollTop = scroll;
  document.title = `${sec.title} · PadDock Console`;
  updateCounts();
}

function updateCounts() {
  const d = store.data;
  if (!d) return;
  const counts = { shortcuts: Object.keys(d.config.actions || {}).length, pages: (d.config.pages || []).length, devices: d.devices.length };
  for (const [id, b] of navButtons) {
    const c = b.querySelector('.count');
    if (c) c.textContent = counts[id] ?? '';
  }
  document.documentElement.style.setProperty('--accent', d.config.appearance?.accent || '#0a84ff');
}

function noKey(message) {
  root.replaceChildren(h('div', { class: 'pair' }, h('div', { class: 'pair-card' },
    h('img', { src: '/ui/icons/icon-192.png', alt: '' }),
    h('h1', null, 'PadDock Console'),
    h('p', null, message),
    h('p', { class: 'hint' }, 'Right-click the PadDock tray icon and choose “Open PadDock console”, or double-click console.bat in the PadDock folder.'))));
}

async function start() {
  if (!consoleKey) { noKey('This page needs the console key.'); return; }
  try {
    await store.load();
  } catch (e) {
    if (e.status === 401) noKey('The console key is missing or out of date.');
    else noKey(e.message);
    return;
  }

  const nav = SECTIONS.map((s) => {
    const b = h('button', { class: 'c-nav', onclick: () => go(s.id) }, icon(s.icon), s.title, h('span', { class: 'count' }));
    navButtons.set(s.id, b);
    return b;
  });
  root.replaceChildren(h('div', { class: 'c-shell' },
    h('aside', { class: 'c-side' },
      h('div', { class: 'c-brand' }, h('img', { src: '/ui/icons/icon-192.png', alt: '' }),
        h('div', null, h('b', null, 'PadDock'), h('small', null, `Console · ${store.data.host}`))),
      nav, status),
    main));

  store.on(render);
  window.addEventListener('hashchange', render);
  render();

  startPolling((live, err) => {
    status.classList.toggle('down', !!err);
    if (err) { statusLine.lastChild.textContent = 'Not reachable'; statusSub.textContent = err.message; return; }
    statusLine.lastChild.textContent = 'Running';
    const n = live.connected.length;
    statusSub.textContent = n ? `${n} device${n > 1 ? 's' : ''} connected: ${live.connected.map((c) => c.name).join(', ')}` : 'No device connected';
    if (store.data && JSON.stringify(live.connected) !== JSON.stringify(store.data.connected)) {
      store.data.connected = live.connected;
      store.data.pairing_code = live.pairing_code;
      if (['overview', 'devices'].includes(current().id) && !document.querySelector('dialog[open]')) render();
    }
  });
}

window.addEventListener('unhandledrejection', (e) => { toastError(e.reason); });
start();
export { api };
