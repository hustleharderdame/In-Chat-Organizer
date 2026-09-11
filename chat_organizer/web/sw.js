/* Service worker for the Chat Root Organizer PWA.
 *
 * Shell: cache-first, so the app opens instantly and still opens when the
 * Termux Flask server is stopped (it then shows its own "server down" panel
 * rather than a browser error page).
 * API:   network-only. Graph data is the one thing that must never be stale —
 *        a cached /nodes response would quietly lie about what was filed.
 */
const VERSION = "cos-v1";
const SHELL = [
  "./",
  "./manifest.webmanifest",
  "./icons/icon-192.png",
  "./icons/icon-512.png",
  "./icons/icon-maskable-512.png",
];

self.addEventListener("install", event => {
  event.waitUntil(
    caches.open(VERSION).then(cache => cache.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== VERSION).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", event => {
  const request = event.request;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  const isApi = /\/(nodes|healthz|ingest)(\/|$|\?)/.test(url.pathname);
  if (isApi) return;   // network-only: never serve stale graph data

  event.respondWith(
    caches.match(request).then(hit => hit || fetch(request).then(response => {
      if (response.ok) {
        const copy = response.clone();
        caches.open(VERSION).then(cache => cache.put(request, copy));
      }
      return response;
    }))
  );
});
