// Opius Network - Service Worker
// Minimal caching so the app shell loads even on a flaky connection, and so the app
// qualifies as an installable PWA (required by Android/Chrome and by PWABuilder).
// Live data (balances, chain, transactions) always goes to the network -- only the
// static shell is cached.

const CACHE_NAME = 'opius-shell-v1';
const SHELL_FILES = [
  '/',
  '/manifest.json',
  '/icons/icon-192.png',
  '/icons/icon-512.png',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL_FILES))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((names) =>
      Promise.all(names.filter((n) => n !== CACHE_NAME).map((n) => caches.delete(n)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Never cache API calls -- balances, chain data, and transactions must always be fresh
  const isApiCall = ['/balance/', '/earn', '/transfer', '/redeem', '/chain', '/stats', '/wallet/new']
    .some((p) => url.pathname.startsWith(p));
  if (isApiCall) {
    event.respondWith(fetch(event.request));
    return;
  }

  // Shell files: cache-first, falling back to network
  event.respondWith(
    caches.match(event.request).then((cached) => cached || fetch(event.request))
  );
});
