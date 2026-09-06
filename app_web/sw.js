const CACHE = 'alucarpin-app-v1';
const ARCHIVOS = [
  '/app/login.html',
  '/app/administrador.html',
  '/app/ayudante.html',
  '/app/manifest.json',
  '/app/icon.svg',
  '/app/icon-192.png',
  '/app/icon-512.png',
  '/app/pwa.js'
];

self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(ARCHIVOS)));
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin || !url.pathname.startsWith('/app/')) return;
  event.respondWith(
    fetch(event.request).then(response => {
      const copia = response.clone();
      caches.open(CACHE).then(cache => cache.put(event.request, copia));
      return response;
    }).catch(() => caches.match(event.request))
  );
});
