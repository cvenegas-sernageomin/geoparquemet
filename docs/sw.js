/* Service worker GeoParquemet: app offline, medios y teselas del mapa en caché. */
const VERSION = 'gpm-v15';
const RA = 'gpm-ra-5';   // objetivos de realidad aumentada: subir al regenerarlos (se guardan aparte de los medios, que nunca expiran)
const APP = ['./', 'index.html', 'styles.css', 'i18n.js', 'app.js', 'manifest.webmanifest', 'vendor/leaflet.js', 'vendor/leaflet.css',
  'data/tour.json', 'data/glosario.json', 'data/geologia.geojson', 'data/quiz.json', 'data/lang_en.json', 'data/lang_pt.json', 'img/portada.webp',
  'img/logos/sernageomin.webp', 'img/logos/parquemet.webp',
  'icons/icon-192.png', 'icons/icon-512.png', 'icons/maskable-512.png', 'icons/favicon.png', 'icons/apple-touch-icon.png'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(VERSION).then(c => c.addAll(APP)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => (k.startsWith('gpm-v') && k !== VERSION) || (k.startsWith('gpm-ra-') && k !== RA)).map(k => caches.delete(k))))
    .then(() => caches.open('gpm-medios')).then(c => c.keys().then(rs => Promise.all(rs.filter(r => /\/ar\//.test(r.url)).map(r => c.delete(r)))))  // RA de versiones previas
    .then(() => self.clients.claim()));
});

// Responde un Range con 206 a partir de la respuesta completa en caché (el seek del audio lo necesita)
async function conRango(req, resp) {
  const rango = req.headers.get('range');
  if (!rango || !resp || resp.status !== 200) return resp;
  const buf = await resp.arrayBuffer();
  const m = /bytes=(\d*)-(\d*)/.exec(rango);
  const ini = m[1] ? +m[1] : 0, fin = m[2] ? Math.min(+m[2], buf.byteLength - 1) : buf.byteLength - 1;
  return new Response(buf.slice(ini, fin + 1), {
    status: 206, statusText: 'Partial Content',
    headers: { 'Content-Type': resp.headers.get('Content-Type') || 'audio/mpeg', 'Content-Range': `bytes ${ini}-${fin}/${buf.byteLength}`, 'Content-Length': fin - ini + 1, 'Accept-Ranges': 'bytes' },
  });
}

self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  const teselas = /arcgisonline\.com|tile\.openstreetmap\.org/.test(url.host);
  if (teselas) {
    e.respondWith(caches.open('gpm-teselas').then(async c => {
      const hit = await c.match(req.url);
      if (hit) return hit;
      try { const r = await fetch(req); if (r.ok || r.type === 'opaque') c.put(req.url, r.clone()); return r; }
      catch { return new Response('', { status: 504 }); }
    }));
    return;
  }
  if (url.origin !== location.origin) return;
  const medio = /\/(img|audio|ar)\//.test(url.pathname);
  if (medio) {
    e.respondWith(caches.open(/\/ar\//.test(url.pathname) ? RA : 'gpm-medios').then(async c => {
      const clave = url.origin + url.pathname;
      let hit = await c.match(clave);
      if (!hit) {
        try {
          const r = await fetch(clave);
          if (r.ok) { await c.put(clave, r.clone()); hit = r; } else return r;
        } catch { return new Response('', { status: 504 }); }
      }
      return conRango(req, hit);
    }));
    return;
  }
  // App y datos: red primero (para recibir actualizaciones), caché si no hay señal
  e.respondWith(fetch(req, { cache: 'no-cache' }).then(r => {  // no-cache: revalida siempre, así llegan las versiones nuevas
    if (r.ok) { const cp = r.clone(); caches.open(VERSION).then(c => c.put(req, cp)); }
    return r;
  }).catch(() => caches.match(req, { ignoreSearch: true }).then(r => r || caches.match('index.html'))));
});
