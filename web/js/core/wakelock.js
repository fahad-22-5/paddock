// Keep the device's screen on with the Screen Wake Lock API. The browser releases the lock
// whenever the app is hidden, so we ask again each time it becomes visible.
import { storage } from './dom.js';

const KEY = 'paddock.keepAwake';
let sentinel = null;
let wanted = storage.get(KEY, true);
const listeners = new Set();

export const wakeLockSupported = () => 'wakeLock' in navigator;
export const wakeLockWanted = () => wanted;
export const wakeLockActive = () => !!sentinel && !sentinel.released;
export const onWakeLockChange = (fn) => { listeners.add(fn); return () => listeners.delete(fn); };
const emit = () => listeners.forEach((fn) => fn());

async function acquire() {
  if (!wanted || !wakeLockSupported() || document.visibilityState !== 'visible' || wakeLockActive()) return;
  try {
    sentinel = await navigator.wakeLock.request('screen');
    sentinel.addEventListener('release', () => { sentinel = null; emit(); });
  } catch (e) {
    console.warn('Wake lock refused:', e);
  }
  emit();
}

export function setKeepAwake(on) {
  wanted = on;
  storage.set(KEY, on);
  if (on) acquire();
  else sentinel?.release().catch(() => {});
  emit();
}

export function initWakeLock() {
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') acquire(); });
  // Safari may refuse the first request until the user has interacted with the page.
  const onFirstTouch = () => { acquire(); };
  document.addEventListener('pointerup', onFirstTouch, { passive: true });
  acquire();
}
