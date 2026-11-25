// Full-screen mode: the page grid takes the whole display and the tab bar hides.
// A small handle at the bottom (with page dots) brings the bar back for a few seconds.
// In a Safari tab it also uses the Fullscreen API to hide Safari's own toolbars.
import { h, icon, onTap, storage } from '../core/dom.js';

const KEY = 'paddock.fullscreen';
const HIDE_AFTER_MS = 5000;
const root = document.documentElement;

const fsElement = () => document.fullscreenElement || document.webkitFullscreenElement;
const standalone = () => matchMedia('(display-mode: standalone)').matches || navigator.standalone === true;

function requestApi() {
  const fn = root.requestFullscreen || root.webkitRequestFullscreen;
  if (!fn || fsElement()) return;
  try { fn.call(root, { navigationUI: 'hide' })?.catch?.(() => {}); } catch {}
}

function exitApi() {
  if (!fsElement()) return;
  const fn = document.exitFullscreen || document.webkitExitFullscreen;
  try { fn?.call(document)?.catch?.(() => {}); } catch {}
}

export class FullScreenMode {
  constructor(shell) {
    this.shell = shell;
    this.on = false;
    this.pinned = false; // bar stays visible (edit mode)
    this.timer = 0;

    this.button = h('button', { class: 'btn icon', 'aria-label': 'Full screen', 'aria-pressed': 'false' }, icon('expand'));
    onTap(this.button, () => this.set(!this.on, { userGesture: true }));

    this.dots = h('span', { class: 'dots' });
    this.handle = h('button', { class: 'fs-handle', 'aria-label': 'Show pages and buttons' }, this.dots, h('span', { class: 'pill' }));
    onTap(this.handle, () => this.reveal());

    // Leaving the browser's full screen (Safari's ✕ button) also leaves our mode.
    const onFsChange = () => { if (this.on && this._usedApi && !fsElement()) this.set(false); };
    document.addEventListener('fullscreenchange', onFsChange);
    document.addEventListener('webkitfullscreenchange', onFsChange);

    if (storage.get(KEY, false)) {
      this.set(true);
      // The Fullscreen API needs a tap, so ask on the first one after launch.
      if (!standalone()) document.addEventListener('pointerup', () => this.on && this._enterApi(), { once: true });
    }
  }

  set(on, { userGesture = false } = {}) {
    this.on = on;
    storage.set(KEY, on);
    this.button.setAttribute('aria-pressed', String(on));
    this.button.setAttribute('aria-label', on ? 'Exit full screen' : 'Full screen');
    this.button.replaceChildren(icon(on ? 'shrink' : 'expand'));
    clearTimeout(this.timer);
    if (on) {
      root.dataset.fullscreen = '';
      delete root.dataset.bar;
      if (userGesture && !standalone()) this._enterApi();
      if (this.pinned) root.dataset.bar = '';
    } else {
      delete root.dataset.fullscreen;
      delete root.dataset.bar;
      this._usedApi = false;
      exitApi();
    }
    this.syncDots();
  }

  _enterApi() {
    requestApi();
    // Only follow fullscreenchange events if the browser actually went full screen.
    setTimeout(() => { this._usedApi = !!fsElement(); }, 600);
  }

  /** Show the tab bar for a few seconds. */
  reveal() {
    if (!this.on) return;
    root.dataset.bar = '';
    this._scheduleHide();
  }

  _scheduleHide() {
    clearTimeout(this.timer);
    if (this.pinned) return;
    this.timer = setTimeout(() => {
      // Keep it open while a sheet or dialog is showing.
      if (document.querySelector('dialog[open]')) { this._scheduleHide(); return; }
      delete root.dataset.bar;
    }, HIDE_AFTER_MS);
  }

  /** Touching the bar keeps it open a little longer. */
  touchedBar() { if (this.on && 'bar' in root.dataset) this._scheduleHide(); }

  /** Edit mode needs the bar (page names, + Page), so pin it while editing. */
  setPinned(pinned) {
    this.pinned = pinned;
    if (!this.on) return;
    if (pinned) { clearTimeout(this.timer); root.dataset.bar = ''; }
    else this._scheduleHide();
  }

  syncDots() {
    const n = this.shell.pages.length || 1;
    this.dots.replaceChildren(...(n > 1 ? Array.from({ length: n }, (_, i) => h('i', { class: i === this.shell.current ? 'on' : '' })) : []));
  }
}
