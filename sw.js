/* CaseFlow Studio — Service Worker
 *
 * PRIVACY-CRITICAL: this app handles dental/medical case images. The Service
 * Worker caches ONLY the static app shell (HTML / manifest / icons). It never
 * caches:
 *   - anything under /api/ (our backend, incl. /api/stripe/*)
 *   - Supabase / Stripe / any cross-origin request (auth, storage, AI APIs)
 *   - request.destination === 'image' (patient / generated / uploaded images)
 *   - any non-GET request (POST/PUT/PATCH/DELETE)
 *   - blob: / data: resources
 *
 * Strategy is an ALLOWLIST, not a blocklist: only the handful of known shell
 * paths are ever written to Cache Storage. Everything else falls through to the
 * network untouched. HTML documents are network-first (never stale), so the app
 * never gets "stuck" on an old build and no API/data response is ever served
 * from cache.
 */

var VERSION = 'cfsw-v7-fast-result-shell';
var SHELL_CACHE = 'caseflow-shell-' + VERSION;

/* App shell only. No patient data, no API responses, no user images. */
var SHELL_ASSETS = [
  '/caseflow_studio_v96.html',
  '/manifest.webmanifest',
  '/icons/icon-192-v2.png',
  '/icons/icon-512-v2.png',
  '/icons/maskable-512-v2.png',
  '/icons/icon-180-v2.png'
];

/* Same-origin static shell assets that may be served from cache. The main HTML
 * document is handled separately (network-first), NOT via this list. */
function isShellAsset(pathname) {
  return pathname === '/manifest.webmanifest' || pathname.indexOf('/icons/') === 0;
}

self.addEventListener('install', function (event) {
  event.waitUntil(
    caches.open(SHELL_CACHE).then(function (cache) {
      // Use individual, failure-tolerant adds so a single missing asset can't
      // abort the whole install.
      return Promise.all(SHELL_ASSETS.map(function (url) {
        return cache.add(new Request(url, { cache: 'reload' })).catch(function () {});
      }));
    }).then(function () { return self.skipWaiting(); })
  );
});

self.addEventListener('activate', function (event) {
  event.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(keys.map(function (k) {
        // Delete every cache that isn't the current shell cache (removes old
        // versions and any legacy caches).
        if (k !== SHELL_CACHE) return caches.delete(k);
      }));
    }).then(function () { return self.clients.claim(); })
  );
});

function networkFirstDoc(request) {
  return fetch(request).then(function (resp) {
    // Cache a copy of the shell document for offline fallback only. Never blocks
    // the response; failures are ignored.
    if (resp && resp.ok && resp.type === 'basic') {
      var copy = resp.clone();
      caches.open(SHELL_CACHE).then(function (cache) { cache.put(request, copy).catch(function () {}); });
    }
    return resp;
  }).catch(function () {
    return caches.match(request).then(function (hit) {
      return hit || caches.match('/caseflow_studio_v96.html');
    });
  });
}

function staleWhileRevalidate(request) {
  return caches.open(SHELL_CACHE).then(function (cache) {
    return cache.match(request).then(function (cached) {
      var network = fetch(request).then(function (resp) {
        if (resp && resp.ok && resp.type === 'basic') cache.put(request, resp.clone()).catch(function () {});
        return resp;
      }).catch(function () { return cached; });
      return cached || network;
    });
  });
}

self.addEventListener('fetch', function (event) {
  var req = event.request;

  // Never touch non-GET (POST/PUT/PATCH/DELETE are never cached).
  if (req.method !== 'GET') return;

  var url;
  try { url = new URL(req.url); } catch (e) { return; }

  // Only same-origin. Cross-origin (Supabase, Stripe, AI APIs, fonts, CDNs)
  // is left entirely to the network — never intercepted, never cached.
  if (url.origin !== self.location.origin) return;

  // Never cache API / auth / storage responses.
  if (url.pathname.indexOf('/api/') === 0 ||
      url.pathname.indexOf('/auth/') === 0 ||
      url.pathname.indexOf('/storage/') === 0) return;

  // Never cache images from the app (patient / generated / uploaded), EXCEPT the
  // known static launcher icons under /icons/ (part of the shell).
  if (req.destination === 'image' && url.pathname.indexOf('/icons/') !== 0) return;

  // HTML navigations / documents → network-first (always fresh, offline fallback).
  if (req.mode === 'navigate' || req.destination === 'document') {
    event.respondWith(networkFirstDoc(req));
    return;
  }

  // Known static shell assets (manifest, icons) → stale-while-revalidate.
  if (isShellAsset(url.pathname)) {
    event.respondWith(staleWhileRevalidate(req));
    return;
  }

  // Everything else same-origin (blobs, data, misc) → network-only (fall through).
});
