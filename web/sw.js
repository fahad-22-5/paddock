// Service worker: lets the Home Screen app open (and show "Disconnected") even when the
// PC is asleep. Network-first, so updates on the PC show up on the next launch; the cache
// is only a fallback. API calls and the WebSocket are never cached.
const CACHE = 'paddock-shell-v1';
const TIMEOUT_MS = 3500;

self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(['/', '/css/app.css', '/js/main.js', '/manifest.webmanifest', '/icons/icon-192.png']))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  const url = new URL(req.url);
  if (req.method !== 'GET' || url.origin !== location.origin || url.pathname.startsWith('/api/') || url.pathname === '/ws') return;

  e.respondWith((async () => {
    const cache = await caches.open(CACHE);
    try {
      const ctrl = new AbortController();
      const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
      const res = await fetch(req, { signal: ctrl.signal, cache: 'no-cache' });
      clearTimeout(timer);
      if (res.ok) cache.put(req, res.clone());
      return res;
    } catch {
      const hit = await cache.match(req, { ignoreSearch: true }) || (req.mode === 'navigate' && await cache.match('/'));
      return hit || new Response('Offline', { status: 503, headers: { 'content-type': 'text/plain' } });
    }
  })());
});
