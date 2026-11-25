// PadDock entry point.
import { Connection } from './core/conn.js';
import { initWakeLock } from './core/wakelock.js';
import { getToken, rememberDeviceName, setToken, showPairing } from './app/pairing.js';
import { Shell } from './app/shell.js';

const root = document.getElementById('app');

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js').catch((e) => console.warn('Service worker not registered:', e));
}
// Block pinch-zoom and double-tap zoom: this is an app, not a page.
document.addEventListener('gesturestart', (e) => e.preventDefault());
document.addEventListener('dblclick', (e) => e.preventDefault(), { passive: false });

initWakeLock();

async function start(reason = '') {
  let token = getToken();
  if (!token) token = await showPairing(root, { reason });
  const conn = new Connection(token);
  const shell = new Shell(root, conn);
  shell.onUnauthorized = () => {
    setToken(null);
    location.replace(location.pathname + '#unpaired');
    location.reload();
  };
  conn.addEventListener('hello', (e) => rememberDeviceName(e.detail.device?.name || 'Dock'));
  conn.connect();
  window.paddock = { conn, shell }; // handy for debugging in Web Inspector
}

start(location.hash === '#unpaired' ? 'This device is no longer paired. Enter a new code from the PC.' : '');
