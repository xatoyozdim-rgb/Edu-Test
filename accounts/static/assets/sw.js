const CACHE_NAME = 'edutest-v1';
const urlsToCache = [
  '/',
  '/static/assets/logo4-BS7ymqtK.png'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(urlsToCache))
  );
});

self.addEventListener('fetch', event => {
  event.respondWith(
    fetch(event.request).catch(() => caches.match(event.request))
  );
});