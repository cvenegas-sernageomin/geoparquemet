/* Service worker GeoParquemet: app offline, medios y teselas del mapa en caché. */
const VERSION = 'gpm-v25';
const RA = 'gpm-ra-9';   // objetivos de realidad aumentada: subir al regenerarlos (se guardan aparte de los medios, que nunca expiran)
const LIBS = 'gpm-libs-1';   // MindAR y three.js (3 MB): no cambian con la app; subir solo si se reemplazan en vendor/
const APP = ['./', 'index.html', 'styles.css', 'i18n.js', 'app.js', 'ar.html', 'estabilizador.js', 'manifest.webmanifest', 'vendor/leaflet.js', 'vendor/leaflet.css',
  'data/tour.json', 'data/glosario.json', 'data/geologia.geojson', 'data/quiz.json', 'data/lang_en.json', 'data/lang_pt.json', 'img/portada.webp',
  'img/logos/sernageomin.webp', 'img/logos/parquemet.webp',
  'icons/icon-192.png', 'icons/icon-512.png', 'icons/maskable-512.png', 'icons/favicon.png', 'icons/apple-touch-icon.png'];

self.addEventListener('install', e => {
  // cache 'reload': sin esto addAll puede tomar de la caché HTTP de Pages (10 min) una versión anterior
  e.waitUntil(caches.open(VERSION).then(c => c.addAll(APP.map(u => new Request(u, { cache: 'reload' })))).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => (k.startsWith('gpm-v') && k !== VERSION) || (k.startsWith('gpm-ra-') && k !== RA) || (k.startsWith('gpm-libs-') && k !== LIBS)).map(k => caches.delete(k))))
    // de gpm-medios (que nunca expira) se borran la RA de versiones previas y las imágenes de la app (portada, logos):
    // antes se guardaban ahí y el teléfono seguía mostrando la portada antigua aunque se publicara una nueva.
    // También el código de la RA que dejaba ahí el botón «Descargar»: sin señal le ganaba a la versión nueva
    .then(() => caches.open('gpm-medios')).then(c => c.keys().then(rs => Promise.all(rs.filter(r => /\/ar\/|\/vendor\/|\/(ar\.html|estabilizador\.js)$/.test(new URL(r.url).pathname) || esDeLaApp(new URL(r.url).pathname)).map(r => c.delete(r)))))
    .then(() => self.clients.claim()));
});

// imágenes que son parte de la app (portada, logos, íconos): van con la app (red primero), no a los medios que nunca expiran
const esDeLaApp = ruta => APP.some(a => a.includes('/') && ruta.endsWith('/' + a));

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
  const medio = /\/(img|audio|ar)\//.test(url.pathname) && !esDeLaApp(url.pathname);
  const libreria = /\/vendor\/(mindar|three)\//.test(url.pathname);
  if (medio || libreria) {
    e.respondWith(caches.open(libreria ? LIBS : /\/ar\//.test(url.pathname) ? RA : 'gpm-medios').then(async c => {
      const clave = url.origin + url.pathname;
      let hit = await c.match(clave);
      if (!hit) {
        try {
          const r = await fetch(clave, { cache: 'no-cache' });   // revalida: la caché HTTP de Pages puede tener una versión anterior
          if (r.ok) { await c.put(clave, r.clone()); hit = r; } else return r;
        } catch { return new Response('', { status: 504 }); }
      }
      return conRango(req, hit);
    }));
    return;
  }
  // App y datos: red primero (para recibir actualizaciones), caché si no hay señal
  // no-cache: revalida siempre, así llegan las versiones nuevas. Una navegación no acepta opciones en fetch(req, …)
  // (lanza TypeError y antes caía siempre al index.html guardado): se pide por URL
  const red = fetch(req.mode === 'navigate' ? req.url : req, { cache: 'no-cache' }).then(r => {
    if (r.ok) { const cp = r.clone(); caches.open(VERSION).then(c => c.put(req, cp)); }
    return r;
  });
  red.catch(() => { });
  const guardado = () => caches.match(req, { ignoreSearch: true }).then(r => r || (req.mode === 'navigate' ? caches.match('index.html') : undefined));
  // con señal débil (en el cerro) la red puede tardar minutos sin fallar: a los 4 s se responde con lo guardado
  // y la descarga sigue por detrás para dejar la caché al día
  e.respondWith(Promise.race([red, new Promise(ok => setTimeout(ok, 4000))])
    .then(r => r || guardado().then(g => g || red), () => guardado().then(g => g || Response.error())));
});
