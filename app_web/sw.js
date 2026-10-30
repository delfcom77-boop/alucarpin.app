const CACHE = 'alucarpin-app-v17-carpetas-almacen';
const ARCHIVOS = [
  '/app/login.html',
  '/app/administrador.html',
  '/app/jornadas.js',
  '/app/catalogo.js',
  '/app/inicio.html',
  '/app/mi_control.html',
  '/app/agenda.html',
  '/app/tareas.html',
  '/app/tareas.css',
  '/app/tareas.js',
  '/app/diario.js?v=1',
  '/app/diario.css?v=1',
  '/app/panel.js?v=privado-2',
  '/app/resumen.html',
  '/app/resumen_privado.js?v=privado-2',
  '/app/economia.js?v=privado-2',
  '/app/obra.html',
  '/app/obra.js',
  '/app/exportar.js',
  '/app/ayudante.html',
  '/app/inicio_ayudante.html',
  '/app/almacen.html',
  '/app/almacen.css',
  '/app/almacen.js',
  '/app/manifest.json',
  '/app/icon.svg',
  '/app/icon-192.png',
  '/app/icon-512.png',
  '/app/pwa.js'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE).then(cache => cache.addAll(ARCHIVOS))
  );
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys
          .filter(key => key !== CACHE)
          .map(key => caches.delete(key))
      )
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin || !url.pathname.startsWith('/app/')) return;
  if (event.request.method !== 'GET') return;

  event.respondWith(
    fetch(event.request, { cache: 'reload' })
      .then(response => {
        if (response && response.status === 200) {
          const copia = response.clone();
          caches.open(CACHE).then(cache => cache.put(event.request, copia));
        }
        return response;
      })
      .catch(() => caches.match(event.request))
  );
});
