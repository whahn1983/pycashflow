// sw.js - PyCashFlow Service Worker

const CACHE_VERSION = 'v1';
const STATIC_CACHE = `pycashflow-static-${CACHE_VERSION}`;
const PAGE_CACHE = `pycashflow-pages-${CACHE_VERSION}`;

// Local static assets to pre-cache on install
const STATIC_ASSETS = [
  '/static/css/improved.css',
  '/static/icons/icon_144x144.png',
  '/static/icons/icon_192x192.png',
  '/static/icons/icon_512x512.png',
  '/static/favicon.ico',
  '/static/apple-touch-icon.png',
  '/offline.html',
];

// ── Install: pre-cache static assets ─────────────────────────────────────────
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then(cache => cache.addAll(STATIC_ASSETS))
      .then(() => self.skipWaiting())
  );
});

// ── Activate: remove stale caches ────────────────────────────────────────────
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(
        keys
          .filter(key => key !== STATIC_CACHE && key !== PAGE_CACHE)
          .map(key => caches.delete(key))
      ))
      .then(() => self.clients.claim())
  );
});

// ── Fetch: routing strategies ─────────────────────────────────────────────────
self.addEventListener('fetch', event => {
  const { request } = event;
  const url = new URL(request.url);

  // Only handle GET requests
  if (request.method !== 'GET') return;

  // Never cache: SW itself, manifest, auth/API endpoints
  if (
    url.pathname === '/sw.js' ||
    url.pathname === '/manifest.json' ||
    url.pathname === '/logout' ||
    url.pathname.startsWith('/ai_insights')
  ) {
    event.respondWith(fetch(request));
    return;
  }

  // Cache-first for local static assets
  if (url.origin === self.location.origin && url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.open(STATIC_CACHE).then(cache =>
        cache.match(request).then(cached =>
          cached || fetch(request).then(response => {
            if (response.ok) cache.put(request, response.clone());
            return response;
          })
        )
      )
    );
    return;
  }

  // Stale-while-revalidate for CDN assets (Bootstrap, Font Awesome, Google Fonts)
  if (url.origin !== self.location.origin) {
    event.respondWith(
      caches.open(STATIC_CACHE).then(cache =>
        cache.match(request).then(cached => {
          const networkFetch = fetch(request).then(response => {
            if (response.ok || response.type === 'opaque') {
              cache.put(request, response.clone());
            }
            return response;
          });
          return cached || networkFetch;
        })
      )
    );
    return;
  }

  // Network-first with cache fallback for HTML page navigations
  const acceptsHtml = request.headers.get('Accept') && request.headers.get('Accept').includes('text/html');
  if (request.mode === 'navigate' || acceptsHtml) {
    event.respondWith(
      fetch(request)
        .then(response => {
          // Cache only successful, non-redirect responses (i.e. authenticated pages)
          if (response.ok) {
            caches.open(PAGE_CACHE).then(cache => cache.put(request, response.clone()));
          }
          return response;
        })
        .catch(() =>
          caches.open(PAGE_CACHE).then(cache =>
            cache.match(request).then(cached => cached || caches.match('/offline.html'))
          )
        )
    );
    return;
  }

  // Default: network only
  event.respondWith(fetch(request));
});

// ── Message: clear page cache on logout ──────────────────────────────────────
self.addEventListener('message', event => {
  if (event.data === 'CLEAR_PAGE_CACHE') {
    event.waitUntil(
      caches.keys().then(keys =>
        Promise.all(
          keys
            .filter(key => key.startsWith('pycashflow-pages'))
            .map(key => caches.delete(key))
        )
      )
    );
  }
});
