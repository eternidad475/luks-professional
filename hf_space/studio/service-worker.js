const CACHE_NAME='smile-morph-studio-webapp-v1';
const ASSETS=['/studio/','/studio/manifest.json','/studio/icons/icon-192.png','/studio/icons/icon-512.png'];
self.addEventListener('install',e=>e.waitUntil(caches.open(CACHE_NAME).then(c=>c.addAll(ASSETS))));
self.addEventListener('fetch',e=>e.respondWith(caches.match(e.request).then(r=>r||fetch(e.request))));
