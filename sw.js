const BASE = self.location.pathname.replace(/\/sw\.js$/, '');
const CACHE = 'pilot-v8';
const STATIC = [BASE + '/', BASE + '/index.html', BASE + '/manifest.json', BASE + '/icon.svg', BASE + '/icon-180.png', BASE + '/icon-192.png', BASE + '/icon-512.png'];
const DATA = [BASE + '/data/briefing.json', BASE + '/data/portfolio.json', BASE + '/data/logistics.json', BASE + '/data/cognition.json'];

// Install: pre-cache static assets
self.addEventListener('install', function(e) {
  e.waitUntil(
    caches.open(CACHE).then(function(c) {
      return c.addAll(STATIC).catch(function() {
        // If any asset fails, continue with what we have
      });
    })
  );
  self.skipWaiting();
});

// Fetch: network-first for data, stale-while-revalidate for static
self.addEventListener('fetch', function(e) {
  var url = new URL(e.request.url);

  // Data files: network-first with fallback to cache
  if (url.pathname.indexOf(BASE + '/data/') === 0) {
    e.respondWith(
      fetch(e.request).then(function(res) {
        if (res.ok) {
          var clone = res.clone();
          caches.open(CACHE).then(function(c) { c.put(e.request, clone); });
        }
        return res;
      }).catch(function() {
        return caches.match(e.request).then(function(cached) {
          return cached || new Response('{"error":"offline"}', {status: 503, headers:{'Content-Type':'application/json'}});
        });
      })
    );
    return;
  }

  // Static assets: stale-while-revalidate, NEVER reject
  e.respondWith(
    caches.match(e.request).then(function(cached) {
      var fetched = fetch(e.request).then(function(res) {
        if (res.ok) {
          var clone = res.clone();
          caches.open(CACHE).then(function(c) { c.put(e.request, clone); });
        }
        return res;
      }).catch(function() {
        // fetch failed - if we have cached, return it; otherwise return a minimal response
        if (cached) return cached;
        // For navigation requests, try to return index.html from cache
        if (e.request.mode === 'navigate') {
          return caches.match(BASE + '/index.html').then(function(idx) {
            return idx || new Response('<!DOCTYPE html><html><head><meta charset=utf-8><title>Raymond工作台</title><meta name=viewport content="width=device-width"><style>body{font-family:-apple-system,BlinkMacSystemFont,sans-serif;text-align:center;padding:40px;color:#666}</style></head><body><h2>离线模式</h2><p>请检查网络连接后刷新</p></body></html>', {status: 200, headers:{'Content-Type':'text/html'}});
          });
        }
        return new Response('', {status: 503});
      });
      return cached || fetched;
    })
  );
});

// Activate: clean old caches
self.addEventListener('activate', function(e) {
  e.waitUntil(
    caches.keys().then(function(keys) {
      return Promise.all(
        keys.filter(function(k) { return k !== CACHE; }).map(function(k) { return caches.delete(k); })
      );
    })
  );
  self.clients.claim();
});
