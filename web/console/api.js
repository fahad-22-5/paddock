// Console API client. Every call carries the console key (from data/console.key, handed
// over in the URL fragment by console.bat / console.sh or the tray / menu bar icon).
const KEY_STORE = 'paddock.consoleKey';

function readKey() {
  const m = location.hash.match(/key=([\w-]+)/);
  if (m) {
    try { localStorage.setItem(KEY_STORE, m[1]); } catch {}
    history.replaceState(null, '', location.pathname); // keep the key out of the address bar
    return m[1];
  }
  try { return localStorage.getItem(KEY_STORE); } catch { return null; }
}

export const consoleKey = readKey();

export class ApiError extends Error {
  constructor(message, status) { super(message); this.status = status; }
}

export async function api(method, path, body) {
  let res;
  try {
    res = await fetch(`/console/api${path}`, {
      method,
      headers: { 'x-paddock-key': consoleKey || '', ...(body !== undefined ? { 'content-type': 'application/json' } : {}) },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError('PadDock isn’t running. Start the PadDock app (or start.bat / ./start.sh).', 0);
  }
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(data?.detail || `Request failed (${res.status})`, res.status);
  return data;
}

const blobCache = new Map();
/** Fetch an image from the console API (needs the key header) as an object URL. */
export function apiImage(path) {
  if (!blobCache.has(path)) {
    blobCache.set(path, fetch(`/console/api${path}`, { headers: { 'x-paddock-key': consoleKey || '' } })
      .then((r) => (r.ok ? r.blob() : null))
      .then((b) => (b ? URL.createObjectURL(b) : null))
      .catch(() => null));
  }
  return blobCache.get(path);
}
export const forgetImages = (prefix) => { for (const k of blobCache.keys()) if (k.startsWith(prefix)) blobCache.delete(k); };

/** Shared state: the latest /state snapshot, refreshed whenever config.json changes. */
export const store = {
  data: null,
  listeners: new Set(),
  async load() {
    this.data = await api('GET', '/state');
    this.listeners.forEach((fn) => fn(this.data));
    return this.data;
  },
  on(fn) { this.listeners.add(fn); return () => this.listeners.delete(fn); },
};

/** Watch for changes (the dock edits the layout, config.json edited by hand, devices connect). */
export function startPolling(onLive) {
  let busy = false;
  setInterval(async () => {
    if (busy || document.hidden) return;
    busy = true;
    try {
      const r = await api('GET', '/rev');
      onLive?.(r, null);
      const editing = document.querySelector('dialog[open]');
      if (store.data && (r.rev !== store.data.rev || r.devices !== store.data.devices.length) && !editing) await store.load();
    } catch (e) {
      onLive?.(null, e);
    } finally {
      busy = false;
    }
  }, 2000);
}

/** Save the layout (pages) and refresh. */
export async function savePages(pages) {
  await api('PUT', '/pages', { pages });
  await store.load();
}
