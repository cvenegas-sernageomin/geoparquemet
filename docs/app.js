'use strict';
/* GeoParquemet · Geo-Ruta 1 — geotour con GPS. App desarrollada por Carlos Venegas. */

const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const store = {
  get(k, d) { try { const v = localStorage.getItem('geoparquemet:' + k); return v == null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem('geoparquemet:' + k, JSON.stringify(v)); } catch { } },
};
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const RADIO_LLEGADA = 35;     // m: distancia para sellar un geositio
const RADIO_CERCA = 120;      // m: aviso de "te acercas"
const PRECISION_MAX = 60;     // m: sobre esto no se sella (GPS poco fiable)

let TOUR, GLOS, GEOL;
const E = {
  modo: store.get('modo', null),          // 'terreno' | 'virtual'
  sellos: store.get('sellos', {}),        // n -> fecha ISO (llegada física)
  vistos: store.get('vistos', {}),        // n -> fecha ISO (ficha abierta)
  ajustes: Object.assign({ auto: true, vibrar: true }, store.get('ajustes', {})),
  pos: null, rumbo: null, rumboFuente: null,
  objetivo: null, avisados: new Set(), fichaN: null,
};

/* ---------- utilidades geo ---------- */
const rad = g => g * Math.PI / 180;
function distancia(a, b, c, d) {
  const R = 6371000, dLa = rad(c - a), dLo = rad(d - b);
  const h = Math.sin(dLa / 2) ** 2 + Math.cos(rad(a)) * Math.cos(rad(c)) * Math.sin(dLo / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}
function rumboHacia(a, b, c, d) {
  const y = Math.sin(rad(d - b)) * Math.cos(rad(c));
  const x = Math.cos(rad(a)) * Math.sin(rad(c)) - Math.sin(rad(a)) * Math.cos(rad(c)) * Math.cos(rad(d - b));
  return (Math.atan2(y, x) * 180 / Math.PI + 360) % 360;
}
const PUNTOS = ['norte', 'noreste', 'este', 'sureste', 'sur', 'suroeste', 'oeste', 'noroeste'];
const cardinal = g => PUNTOS[Math.round(g / 45) % 8];
const fmtDist = m => m < 1000 ? `${Math.round(m / 5) * 5} m` : `${(m / 1000).toFixed(1).replace('.', ',')} km`;
const minutosAPie = m => Math.max(1, Math.round(m / 65));  // ~4 km/h en subida suave

/* ---------- texto con términos de glosario ---------- */
function conTerminos(t) {
  return esc(t).replace(/\[\[([^|\]]+)\|([^\]]+)\]\]/g, (_, slug, txt) =>
    GLOS && GLOS[slug] ? `<button class="term" data-term="${slug}">${txt}</button>` : txt);
}
const planoTxt = t => t.replace(/\[\[[^|\]]+\|([^\]]+)\]\]/g, '$1');
document.addEventListener('click', e => {
  const b = e.target.closest('.term');
  if (b) { e.preventDefault(); verTermino(b.dataset.term); }
});
function verTermino(slug) {
  const g = GLOS[slug]; if (!g) return;
  hoja(`<button class="cerrar" aria-label="Cerrar">✕</button><h3>${esc(g.t)}</h3>${g.d.map(p => `<p>${conTerminos(p)}</p>`).join('')}`);
}

/* ---------- hoja / toast ---------- */
function hoja(html) {
  $('#hoja-in').innerHTML = html; $('#hoja').hidden = false;
  $('#hoja-in').scrollTop = 0;
}
$('#hoja').addEventListener('click', e => { if (e.target.id === 'hoja' || e.target.closest('.cerrar, .cerrar-hoja')) $('#hoja').hidden = true; });
let toastT;
function toast(msg, boton, accion, ms = 6000) {
  const t = $('#toast');
  t.innerHTML = `<span>${msg}</span>` + (boton ? `<button>${boton}</button>` : '');
  t.hidden = false;
  if (boton) t.querySelector('button').onclick = () => { t.hidden = true; accion(); };
  clearTimeout(toastT); toastT = setTimeout(() => t.hidden = true, ms);
}
function vibrar(p) { if (E.ajustes.vibrar && navigator.vibrate) try { navigator.vibrate(p); } catch { } }

/* ---------- navegación ---------- */
const VISTAS = ['inicio', 'mapa', 'pasaporte', 'info'];
let ultimaVista = 'inicio';
function ruta() {
  const h = location.hash.replace(/^#\/?/, '');
  const m = h.match(/^g\/(\d+)/);
  if (m) { abrirFicha(+m[1]); return; }
  cerrarFicha();
  const v = VISTAS.includes(h) ? h : 'inicio';
  ultimaVista = v;
  VISTAS.forEach(x => $('#v-' + x).hidden = x !== v);
  $$('#tabs a').forEach(a => a.classList.toggle('activo', a.dataset.v === v));
  if (v === 'mapa') mostrarMapa();
  if (v === 'pasaporte') pintarPasaporte();
  document.body.classList.toggle('con-guia', v === 'mapa' && !$('#guia').hidden);
}
window.addEventListener('hashchange', ruta);

/* ---------- inicio ---------- */
function pintarInicio() {
  const n = TOUR.sitios.length;
  $('#datos-ruta').innerHTML = `<span>🥾 ${fmtDist(TOUR.largo_m)}</span><span>📍 ${n} geositios</span><span>⛰️ ${Math.min(...TOUR.sitios.map(s => s.elev))}–${Math.max(...TOUR.sitios.map(s => s.elev))} m s.n.m.</span><span>⏱️ ~2 h</span>`;
  $('#intro-txt').innerHTML = TOUR.intro.map(p => `<p>${conTerminos(p)}</p>`).join('') + `<p><b>⚠️ ${esc(TOUR.aviso)}</b></p>`;
  pintarLista();
  $('#modo-terreno').classList.toggle('activo', E.modo === 'terreno');
  $('#modo-virtual').classList.toggle('activo', E.modo === 'virtual');
}
function pintarLista() {
  $('#lista').innerHTML = TOUR.sitios.map(s => {
    const est = E.sellos[s.n] ? '✅' : E.vistos[s.n] ? '👁️' : '';
    const d = E.pos ? ` · a ${fmtDist(distancia(E.pos.lat, E.pos.lon, s.lat, s.lon))}` : '';
    const img = s.fotos[0] ? s.fotos[0].a : s.historicas[0]?.src;
    return `<li><button data-n="${s.n}"><img src="${img}" alt="" loading="lazy"><div><div class="num">Geositio ${s.n}</div><div class="tit">${esc(s.titulo)}</div><div class="meta">${s.elev} m s.n.m.${d}</div></div><span class="estado">${est}</span></button></li>`;
  }).join('');
}
$('#lista').addEventListener('click', e => { const b = e.target.closest('button[data-n]'); if (b) location.hash = '#/g/' + b.dataset.n; });
$('#modo-terreno').onclick = async () => {
  E.modo = 'terreno'; store.set('modo', E.modo);
  pedirBrujula(); pantallaCompleta();
  iniciarGPS(); ofrecerInstalar();
  location.hash = '#/mapa';
};
$('#modo-virtual').onclick = () => {
  E.modo = 'virtual'; store.set('modo', E.modo);
  pantallaCompleta(); ofrecerInstalar();
  location.hash = '#/g/1';
};

/* ---------- mapa ---------- */
let mapa, capaSat, capaCalles, capaGeol, marcadores = {}, yoMarca, yoCirculo, lineaGuia, siguiendo = false;
const COLORES = {
  'Cordón Cerro San Cristóbal': '#e2725b', 'Cerro Blanco': '#f2c14e',
  'Cerro El Carbón 1': '#8e6cc2', 'Cerro El Carbón 2': '#b8a2e0', 'Pórfido andesítico': '#e0489a',
};
function mostrarMapa() {
  if (!mapa) crearMapa(); else setTimeout(() => mapa.invalidateSize(), 50);
  if (E.modo === 'terreno') iniciarGPS();
  actualizarGuia();
}
function crearMapa() {
  mapa = L.map('mapa', { zoomControl: false, attributionControl: true, maxZoom: 20 });
  capaSat = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    { maxNativeZoom: 19, maxZoom: 20, attribution: '© Esri' }).addTo(mapa);
  capaCalles = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    { maxNativeZoom: 19, maxZoom: 20, attribution: '© OpenStreetMap' });
  capaGeol = L.geoJSON(GEOL, {
    style: f => ({ color: COLORES[f.properties.unidad] || '#999', weight: 1.5, fillOpacity: .33 }),
    onEachFeature: (f, l) => {
      const p = f.properties;
      l.bindPopup(`<h4>${esc(p.unidad)}</h4><div><b>${esc(p.nombre)}</b>${p.codigo ? ` (${esc(p.codigo)})` : ''}</div><div>${esc(p.edad)}</div><p>${esc(p.desc)}…</p>${p.termino && GLOS[p.termino] ? `<button class="term" data-term="${p.termino}">Leer más</button>` : ''}`);
    },
  });
  if (store.get('geologia', false)) { capaGeol.addTo(mapa); $('#btn-geol').classList.add('activo'); }
  L.polyline(TOUR.ruta_coords, { color: '#000', weight: 8, opacity: .35 }).addTo(mapa);
  L.polyline(TOUR.ruta_coords, { color: '#ffc766', weight: 4, dashArray: '10 8' }).addTo(mapa);
  TOUR.sitios.forEach(s => {
    const m = L.marker([s.lat, s.lon], { icon: iconoSitio(s.n), zIndexOffset: 100 }).addTo(mapa);
    m.bindTooltip(`${s.n}. ${s.titulo}`, { direction: 'top', offset: [0, -30] });
    m.on('click', () => location.hash = '#/g/' + s.n);
    marcadores[s.n] = m;
  });
  mapa.fitBounds(L.latLngBounds(TOUR.ruta_coords).pad(.12));
  mapa.on('dragstart', () => { siguiendo = false; $('#btn-gps').classList.remove('sigue'); });
  pintarLeyenda();
}
function iconoSitio(n) {
  const c = E.sellos[n] ? 'sellado' : '';
  const o = objetivoActual()?.n === n ? 'objetivo' : '';
  return L.divIcon({ className: '', html: `<div class="marcador ${c} ${o}"><span>${n}</span></div>`, iconSize: [34, 34], iconAnchor: [17, 38] });
}
function refrescarMarcadores() { if (mapa) TOUR.sitios.forEach(s => marcadores[s.n].setIcon(iconoSitio(s.n))); }
function pintarLeyenda() {
  const on = mapa && mapa.hasLayer(capaGeol);
  $('#leyenda').hidden = !on;
  $('#leyenda').innerHTML = '<b>Geología</b>' + Object.entries(COLORES).map(([k, c]) => `<div><i style="background:${c}"></i>${esc(k)}</div>`).join('') + '<div><i style="background:#ffc766;height:4px;border:0"></i>Geo-Ruta 1</div>';
}
$('#btn-capas').onclick = () => {
  if (mapa.hasLayer(capaSat)) { mapa.removeLayer(capaSat); capaCalles.addTo(mapa); toast('Mapa de calles'); }
  else { mapa.removeLayer(capaCalles); capaSat.addTo(mapa); toast('Imagen satelital'); }
  capaCalles.bringToBack(); capaSat.bringToBack();
};
$('#btn-geol').onclick = () => {
  const on = !mapa.hasLayer(capaGeol);
  if (on) capaGeol.addTo(mapa); else mapa.removeLayer(capaGeol);
  $('#btn-geol').classList.toggle('activo', on); store.set('geologia', on); pintarLeyenda();
  if (on) toast('Toca un color para conocer la unidad geológica');
};
$('#btn-gps').onclick = () => {
  if (!E.pos) { iniciarGPS(); toast('Buscando tu ubicación…'); return; }
  siguiendo = true; $('#btn-gps').classList.add('sigue');
  mapa.setView([E.pos.lat, E.pos.lon], Math.max(mapa.getZoom(), 17));
};

/* ---------- GPS y brújula ---------- */
let gpsId = null;
function iniciarGPS() {
  if (gpsId != null || !navigator.geolocation) return;
  const sim = new URLSearchParams(location.search).get('sim');
  if (sim) { const [a, b] = sim.split(',').map(Number); nuevaPos({ lat: a, lon: b, acc: 8 }); return; }
  gpsId = navigator.geolocation.watchPosition(p => nuevaPos({
    lat: p.coords.latitude, lon: p.coords.longitude, acc: p.coords.accuracy,
    rumbo: p.coords.heading, vel: p.coords.speed,
  }), err => {
    gpsId = null;
    if (err.code === 1) toast('Activa el permiso de ubicación para usar la guía GPS. Mientras tanto puedes explorar en modo virtual.', 'Virtual', () => location.hash = '#/g/1', 9000);
    else toast('No se pudo obtener tu ubicación. Revisa que el GPS esté encendido.');
  }, { enableHighAccuracy: true, maximumAge: 4000, timeout: 30000 });
}
window.__simular = (lat, lon, acc = 6) => nuevaPos({ lat, lon, acc });

function nuevaPos(p) {
  const primera = !E.pos;
  E.pos = p;
  if (p.vel > 0.8 && p.rumbo != null && !isNaN(p.rumbo) && E.rumboFuente !== 'brujula') { E.rumbo = p.rumbo; E.rumboFuente = 'gps'; }
  if (mapa) {
    const ll = [p.lat, p.lon];
    if (!yoMarca) {
      yoMarca = L.marker(ll, { icon: L.divIcon({ className: '', html: '<div class="yo"><div class="cono"></div></div>', iconSize: [20, 20], iconAnchor: [10, 10] }), zIndexOffset: 1000, interactive: false }).addTo(mapa);
      yoCirculo = L.circle(ll, { radius: p.acc, color: '#1a73e8', weight: 1, fillOpacity: .1, interactive: false }).addTo(mapa);
    } else { yoMarca.setLatLng(ll); yoCirculo.setLatLng(ll).setRadius(p.acc); }
    if (primera && !$('#v-mapa').hidden) {
      const lejos = distancia(p.lat, p.lon, TOUR.sitios[0].lat, TOUR.sitios[0].lon) > 4000;
      if (lejos) toast('Estás lejos del parque. La guía te indicará cómo llegar al inicio de la ruta (acceso Pío Nono).', null, null, 8000);
      else { siguiendo = true; $('#btn-gps').classList.add('sigue'); mapa.setView(ll, 17); }
    } else if (siguiendo) mapa.panTo(ll, { animate: true });
  }
  revisarLlegadas();
  actualizarGuia();
  if (!$('#v-inicio').hidden) pintarLista();
}

function pedirBrujula() {
  const DOE = window.DeviceOrientationEvent;
  if (DOE && typeof DOE.requestPermission === 'function') {
    DOE.requestPermission().then(r => { if (r === 'granted') escucharBrujula(); }).catch(() => { });
  } else escucharBrujula();
}
let brujulaOn = false;
function escucharBrujula() {
  if (brujulaOn) return; brujulaOn = true;
  const h = e => {
    let r = null;
    if (typeof e.webkitCompassHeading === 'number') r = e.webkitCompassHeading;
    else if (e.absolute && e.alpha != null) r = 360 - e.alpha;
    if (r == null) return;
    const o = (screen.orientation && screen.orientation.angle) || 0;
    E.rumbo = (r + o + 360) % 360; E.rumboFuente = 'brujula';
    pintarFlecha();
  };
  if ('ondeviceorientationabsolute' in window) window.addEventListener('deviceorientationabsolute', h);
  else window.addEventListener('deviceorientation', h);
}

/* ---------- guía hacia el siguiente geositio ---------- */
function objetivoActual() {
  if (E.objetivo && !E.sellos[E.objetivo]) return TOUR.sitios[E.objetivo - 1];
  return TOUR.sitios.find(s => !E.sellos[s.n]) || null;
}
function actualizarGuia() {
  const g = $('#guia');
  const obj = objetivoActual();
  if (E.modo !== 'terreno' || !E.pos || !obj) {
    g.hidden = true; document.body.classList.remove('con-guia');
    if (lineaGuia) { mapa.removeLayer(lineaGuia); lineaGuia = null; }
    if (E.modo === 'terreno' && E.pos && !obj && !$('#v-mapa').hidden) {
      g.hidden = false; $('#guia-txt').innerHTML = '<b>¡Completaste la Geo-Ruta 1! 🎉</b><small>Revisa tu pasaporte</small>';
      $('#guia-abrir').textContent = 'Ver'; $('#guia-abrir').onclick = () => location.hash = '#/pasaporte';
    }
    return;
  }
  const d = distancia(E.pos.lat, E.pos.lon, obj.lat, obj.lon);
  g.hidden = false;
  if (!$('#v-mapa').hidden) document.body.classList.add('con-guia');
  $('#guia-txt').innerHTML = `<small>Siguiente · Geositio ${obj.n}</small><b>${esc(obj.titulo)}</b><span class="dist">${fmtDist(d)}</span> <small>hacia el ${cardinal(rumboHacia(E.pos.lat, E.pos.lon, obj.lat, obj.lon))} · ~${minutosAPie(d)} min</small>`;
  $('#guia-abrir').textContent = 'Ver';
  $('#guia-abrir').onclick = () => location.hash = '#/g/' + obj.n;
  if (mapa) {
    const ll = [[E.pos.lat, E.pos.lon], [obj.lat, obj.lon]];
    if (!lineaGuia) lineaGuia = L.polyline(ll, { color: '#1a73e8', weight: 3, dashArray: '2 8', interactive: false }).addTo(mapa);
    else lineaGuia.setLatLngs(ll);
  }
  pintarFlecha();
}
function pintarFlecha() {
  const obj = objetivoActual(); if (!obj || !E.pos) return;
  const b = rumboHacia(E.pos.lat, E.pos.lon, obj.lat, obj.lon);
  const f = $('#guia-flecha');
  const conRumbo = E.rumbo != null;
  f.style.transform = `rotate(${conRumbo ? b - E.rumbo : b}deg)`;
  f.classList.toggle('sin-brujula', !conRumbo);
  f.title = conRumbo ? 'Apunta hacia el geositio' : 'Dirección respecto al norte (mapa)';
  const yo = document.querySelector('.yo');
  if (yo) {
    yo.classList.toggle('con-rumbo', conRumbo);
    const c = yo.querySelector('.cono'); if (c && conRumbo) c.style.transform = `rotate(${E.rumbo}deg)`;
  }
}

function revisarLlegadas() {
  const p = E.pos; if (!p) return;
  for (const s of TOUR.sitios) {
    const d = distancia(p.lat, p.lon, s.lat, s.lon);
    if (!E.sellos[s.n] && d <= RADIO_LLEGADA && p.acc <= PRECISION_MAX) { llegar(s); break; }
    if (!E.sellos[s.n] && d <= RADIO_CERCA && !E.avisados.has(s.n)) {
      E.avisados.add(s.n); vibrar(120);
      toast(`Te acercas al <b>Geositio ${s.n}</b> · ${esc(s.titulo)} (${fmtDist(d)})`, 'Ver', () => location.hash = '#/g/' + s.n);
    }
  }
}
function llegar(s) {
  E.sellos[s.n] = new Date().toISOString(); store.set('sellos', E.sellos);
  if (E.objetivo === s.n) E.objetivo = null;
  vibrar([180, 80, 180]);
  const a = $('#sello-anim');
  a.innerHTML = `<div><span><b>${s.n}</b>¡Sello obtenido!</span></div>`; a.hidden = false;
  setTimeout(() => a.hidden = true, 1900);
  refrescarMarcadores(); pintarLista();
  const abrir = () => { location.hash = '#/g/' + s.n; setTimeout(() => reproducir(s.n), 400); };
  if (E.ajustes.auto && !E.fichaN) setTimeout(abrir, 1500);
  else toast(`Llegaste al <b>Geositio ${s.n}</b> · ${esc(s.titulo)}`, 'Escuchar', abrir, 10000);
}

/* ---------- ficha ---------- */
function abrirFicha(n) {
  const s = TOUR.sitios[n - 1]; if (!s) { location.hash = '#/'; return; }
  E.fichaN = n;
  if (!E.vistos[n]) { E.vistos[n] = new Date().toISOString(); store.set('vistos', E.vistos); }
  const total = TOUR.sitios.length;
  const d = E.pos ? distancia(E.pos.lat, E.pos.lon, s.lat, s.lon) : null;
  const est = E.sellos[n] ? '✅ Sellado' : E.vistos[n] ? '👁️ Visto' : '';
  const ytimg = id => `https://i.ytimg.com/vi/${id}/hqdefault.jpg`;
  const sv = `https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${s.sv[0]},${s.sv[1]}&heading=${s.sv[2]}&pitch=${s.sv[3]}`;
  const llegar = `https://www.google.com/maps/dir/?api=1&destination=${s.lat},${s.lon}&travelmode=walking`;
  const off = s.texto.length + 1;
  $('#ficha-scroll').innerHTML = `
    <div class="f-cab">
      <button id="f-volver" aria-label="Volver">←</button>
      <span class="f-num">Geositio ${n} de ${total}</span>
      <button id="f-ant" ${n === 1 ? 'disabled style="opacity:.3"' : ''} aria-label="Anterior">‹</button>
      <button id="f-sig" ${n === total ? 'disabled style="opacity:.3"' : ''} aria-label="Siguiente">›</button>
    </div>
    ${comparadores(s)}
    <div class="f-cuerpo">
      <h2>${esc(s.titulo)}</h2>
      <div class="f-meta">${s.elev} m s.n.m. · ${s.lat.toFixed(5)}, ${s.lon.toFixed(5)}${d != null ? ` · a ${fmtDist(d)} de ti` : ''} ${est ? '· ' + est : ''}</div>
      <div class="f-acciones">
        <button class="btn escuchar" id="f-escuchar">▶ Escuchar (${Math.round(s.audio.dur / 60)} min)</button>
        ${E.modo === 'terreno' && !E.sellos[n] ? `<button class="btn" id="f-llevar">🧭 Llevarme aquí</button>` : ''}
        <a class="btn" href="${sv}" target="_blank" rel="noopener">👁️ Street View</a>
      </div>
      <div id="f-texto">${s.texto.map((p, i) => `<p data-i="${i + 1}">${conTerminos(p)}</p>`).join('')}</div>
      ${s.texto_web.length ? `<div class="caja-web"><h3>🔎 Observa en el lugar</h3>${s.texto_web.map((p, i) => `<p data-i="${off + i}">${conTerminos(p)}</p>`).join('')}</div>` : ''}
      ${s.historicas.map(h => `<h3 class="sec">La piscina y su roca en el tiempo</h3><img class="foto-hist" src="${h.src}" alt="Fotografías históricas de la piscina Tupahue" loading="lazy" width="${h.w}" height="${h.h}">`).join('')}
      ${s.sketchfab.length ? `<h3 class="sec">Modelo 3D</h3>` + s.sketchfab.map(id => `<div class="embed" data-src="https://sketchfab.com/models/${id}/embed?autostart=1&ui_infos=0&ui_watermark=0&preload=1"><button class="cargar"><span>🧊 Cargar modelo 3D (requiere internet)</span></button></div>`).join('') : ''}
      ${s.seequent.map(u => `<p><a href="${u}" target="_blank" rel="noopener">🗺️ Ver modelo geológico 3D del parque (Seequent)</a></p>`).join('')}
      ${s.youtube.length ? `<h3 class="sec">Videos</h3>` + s.youtube.map(id => `<div class="embed" data-src="https://www.youtube-nocookie.com/embed/${id}?autoplay=1&rel=0"><button class="cargar" style="background-image:url(${ytimg(id)})"><span>▶ Ver video</span></button></div>`).join('') : ''}
      <p><a class="btn" href="${llegar}" target="_blank" rel="noopener">🚶 Cómo llegar (Google Maps)</a></p>
      <div class="f-acciones">
        ${n > 1 ? `<a class="btn" href="#/g/${n - 1}">‹ Geositio ${n - 1}</a>` : ''}
        ${n < total ? `<a class="btn primario" href="#/g/${n + 1}">Geositio ${n + 1} ›</a>` : `<a class="btn primario" href="#/pasaporte">Ver mi pasaporte</a>`}
      </div>
    </div>`;
  const f = $('#ficha');
  f.hidden = false; document.body.classList.add('ficha-abierta');
  $('#ficha-scroll').scrollTop = 0;
  $('#f-volver').onclick = () => location.hash = ultimaVista === 'inicio' ? '#/' : '#/' + ultimaVista;
  $('#f-ant').onclick = () => location.hash = '#/g/' + (n - 1);
  $('#f-sig').onclick = () => location.hash = '#/g/' + (n + 1);
  $('#f-escuchar').onclick = () => reproducir(n);
  const ll = $('#f-llevar'); if (ll) ll.onclick = () => { E.objetivo = n; refrescarMarcadores(); location.hash = '#/mapa'; };
  $$('#ficha .embed').forEach(el => el.querySelector('.cargar').onclick = () => {
    el.innerHTML = `<iframe src="${el.dataset.src}" allow="autoplay; fullscreen; xr-spatial-tracking; accelerometer; gyroscope" allowfullscreen loading="lazy"></iframe>`;
  });
  activarComparadores();
  resaltarParrafo();
}
function cerrarFicha() {
  if ($('#ficha').hidden) return;
  $('#ficha').hidden = true; E.fichaN = null;
  document.body.classList.remove('ficha-abierta');
  $('#ficha-scroll').innerHTML = '';
  pintarLista();
}

function comparadores(s) {
  if (!s.fotos.length) return '';
  const cap = esc(s.cap);
  const mini = s.fotos.length > 1 ? `<div class="galeria-mini" id="f-mini">${s.fotos.map((f, i) => `<button data-i="${i}" class="${i ? '' : 'activo'}"><img src="${f.b}" alt="Foto ${i + 1}" loading="lazy"></button>`).join('')}</div>` : '';
  const f = s.fotos[0];
  return `<div class="f-cuerpo" style="padding-bottom:0">${compHTML(f)}<p class="pie">↔ Desliza para comparar la foto con su interpretación. ${cap}</p>${mini}</div>`;
}
const compHTML = f => `<div class="comparador" id="f-comp"><img src="${f.a}" alt="Fotografía original" width="${f.w}" height="${f.h}"><div class="capa-b"><img src="${f.b}" alt="Fotografía interpretada"></div><div class="barra"></div><div class="tirador">⇆</div><span class="etq a">Foto</span><span class="etq b">Interpretación</span></div>`;
function activarComparadores() {
  const n = E.fichaN, s = TOUR.sitios[n - 1];
  const montar = () => {
    const c = $('#f-comp'); if (!c) return;
    const poner = x => {
      const r = c.getBoundingClientRect();
      const p = Math.min(98, Math.max(2, (x - r.left) / r.width * 100));
      c.querySelector('.capa-b').style.clipPath = `inset(0 0 0 ${p}%)`;
      c.querySelector('.barra').style.left = p + '%';
      c.querySelector('.tirador').style.left = p + '%';
    };
    let arrastrando = false, x0 = 0, y0 = 0, decidido = false;
    c.addEventListener('pointerdown', e => { arrastrando = true; decidido = e.pointerType === 'mouse'; x0 = e.clientX; y0 = e.clientY; if (decidido) { c.setPointerCapture(e.pointerId); poner(e.clientX); } });
    c.addEventListener('pointermove', e => {
      if (!arrastrando) return;
      if (!decidido) {
        if (Math.abs(e.clientX - x0) > 6 && Math.abs(e.clientX - x0) > Math.abs(e.clientY - y0)) { decidido = true; c.setPointerCapture(e.pointerId); }
        else if (Math.abs(e.clientY - y0) > 8) { arrastrando = false; return; }
        else return;
      }
      poner(e.clientX);
    });
    const fin = () => arrastrando = false;
    c.addEventListener('pointerup', e => { if (!decidido && arrastrando) poner(e.clientX); fin(); });
    c.addEventListener('pointercancel', fin);
  };
  montar();
  const mini = $('#f-mini');
  if (mini) mini.onclick = e => {
    const b = e.target.closest('button[data-i]'); if (!b) return;
    $$('#f-mini button').forEach(x => x.classList.toggle('activo', x === b));
    $('#f-comp').outerHTML = compHTML(s.fotos[+b.dataset.i]);
    montar();
  };
}

/* ---------- audio ---------- */
const audio = $('#audio');
let audioN = null;  // 0 = introducción
function reproducir(n) {
  const info = n === 0 ? TOUR.intro_audio : TOUR.sitios[n - 1].audio;
  if (audioN !== n) {
    audioN = n; audio.src = info.src; audio.currentTime = 0;
    $('#rep-titulo').textContent = n === 0 ? 'Introducción · Geo-Ruta 1' : `Geositio ${n} · ${TOUR.sitios[n - 1].titulo}`;
  }
  $('#reproductor').hidden = false;
  audio.play().catch(() => { });
  if ('mediaSession' in navigator) {
    navigator.mediaSession.metadata = new MediaMetadata({ title: $('#rep-titulo').textContent, artist: 'GeoParquemet · Sernageomin', artwork: [{ src: 'icons/icon-512.png', sizes: '512x512', type: 'image/png' }] });
  }
}
$('#btn-intro').onclick = () => reproducir(0);
$('#rep-play').onclick = () => audio.paused ? audio.play() : audio.pause();
audio.addEventListener('play', () => $('#rep-play').textContent = '❚❚');
audio.addEventListener('pause', () => $('#rep-play').textContent = '▶');
audio.addEventListener('ended', () => { $('#rep-play').textContent = '▶'; $$('.p-activo').forEach(p => p.classList.remove('p-activo')); });
audio.addEventListener('timeupdate', () => {
  if (audio.duration) $('#rep-barra').value = audio.currentTime / audio.duration * 100;
  resaltarParrafo();
});
$('#rep-barra').addEventListener('input', e => { if (audio.duration) audio.currentTime = e.target.value / 100 * audio.duration; });
const VELS = [1, 1.25, 1.5, .85];
$('#rep-vel').onclick = () => {
  const i = (VELS.indexOf(audio.playbackRate) + 1) % VELS.length;
  audio.playbackRate = VELS[i]; $('#rep-vel').textContent = String(VELS[i]).replace('.', ',') + '×';
};
$('#rep-cerrar').onclick = () => { audio.pause(); $('#reproductor').hidden = true; $$('.p-activo').forEach(p => p.classList.remove('p-activo')); };
let pActivo = null;
function resaltarParrafo() {
  if (!audioN || audioN !== E.fichaN || audio.paused && audio.currentTime === 0) return;
  const m = TOUR.sitios[audioN - 1].audio.marcas;
  let i = 0; while (i + 1 < m.length && audio.currentTime >= m[i + 1]) i++;
  if (i === pActivo && document.querySelector('.p-activo')) return;
  pActivo = i;
  $$('.p-activo').forEach(p => p.classList.remove('p-activo'));
  const p = document.querySelector(`#ficha p[data-i="${i}"]`);
  if (p) { p.classList.add('p-activo'); if (!audio.paused) p.scrollIntoView({ block: 'center', behavior: 'smooth' }); }
}

/* ---------- pasaporte ---------- */
function pintarPasaporte() {
  const n = TOUR.sitios.length, hechos = Object.keys(E.sellos).length, vistos = Object.keys(E.vistos).length;
  $('#pas-resumen').textContent = `${hechos} de ${n} sellos en terreno · ${vistos} de ${n} geositios vistos`;
  $('#sellos').innerHTML = TOUR.sitios.map(s => {
    const f = E.sellos[s.n];
    const cls = f ? 'hecho' : E.vistos[s.n] ? 'visto' : '';
    const pie = f ? new Date(f).toLocaleDateString('es-CL', { day: 'numeric', month: 'short', year: 'numeric' }) : E.vistos[s.n] ? 'Visto (virtual)' : 'Pendiente';
    return `<a class="sello ${cls}" href="#/g/${s.n}" style="text-decoration:none;color:inherit"><div class="circ">${f ? '✓' : s.n}</div><b>${esc(s.titulo)}</b><small>${pie}</small></a>`;
  }).join('');
  const fin = $('#pas-final');
  if (hechos === n) { fin.hidden = false; fin.innerHTML = `<h3>🏅 ¡Completaste la Geo-Ruta 1 Pío Nono – Tupahue!</h3><p>Recorriste ${fmtDist(TOUR.largo_m)} y 28 millones de años de historia geológica de Santiago.</p>`; }
  else if (vistos === n) { fin.hidden = false; fin.innerHTML = `<h3>🌎 Recorrido virtual completo</h3><p>Ahora ven al Parque Metropolitano a conseguir los ${n} sellos en terreno.</p>`; }
  else fin.hidden = true;
}

/* ---------- saber más ---------- */
function pintarInfo() {
  const orden = Object.entries(GLOS).sort((a, b) => a[1].t.localeCompare(b[1].t, 'es'));
  const pintar = q => {
    q = (q || '').toLowerCase().normalize('NFD').replace(/\p{M}/gu, '');
    $('#glosario').innerHTML = orden.filter(([, g]) => !q || (g.t + ' ' + g.d.join(' ')).toLowerCase().normalize('NFD').replace(/\p{M}/gu, '').includes(q))
      .map(([k, g]) => `<dt><button class="term" data-term="${k}">${esc(g.t)}</button></dt><dd>${esc(planoTxt(g.d[0] || '')).slice(0, 150)}…</dd>`).join('') || '<p>Sin resultados.</p>';
  };
  pintar(); $('#buscar-glosario').oninput = e => pintar(e.target.value);
  const vistas = new Map();
  GEOL.features.forEach(f => vistas.set(f.properties.unidad, f.properties));
  $('#unidades').innerHTML = [...vistas.values()].map(p => `<div class="unidad"><i style="background:${COLORES[p.unidad] || '#999'}"></i><div><b>${esc(p.unidad)}</b> · ${esc(p.nombre)}<small>${esc(p.edad)}</small>${p.termino && GLOS[p.termino] ? `<button class="term" data-term="${p.termino}">Leer más</button>` : ''}</div></div>`).join('');
  $('#biblio').innerHTML = TOUR.bibliografia.map(b => `<li>${esc(b.t)}${b.url ? ` <a href="${esc(b.url)}" target="_blank" rel="noopener">Enlace</a>` : ''}</li>`).join('');
  $('#aj-auto').checked = E.ajustes.auto; $('#aj-vibrar').checked = E.ajustes.vibrar;
  $('#aj-auto').onchange = e => { E.ajustes.auto = e.target.checked; store.set('ajustes', E.ajustes); };
  $('#aj-vibrar').onchange = e => { E.ajustes.vibrar = e.target.checked; store.set('ajustes', E.ajustes); };
  $('#btn-reset').onclick = () => {
    if (!confirm('¿Borrar tus sellos y geositios vistos?')) return;
    E.sellos = {}; E.vistos = {}; store.set('sellos', {}); store.set('vistos', {}); E.avisados.clear();
    refrescarMarcadores(); pintarLista(); toast('Progreso reiniciado');
  };
}

/* ---------- descarga para usar sin señal ---------- */
function tilesRuta() {
  const lat = TOUR.ruta_coords.map(c => c[0]), lon = TOUR.ruta_coords.map(c => c[1]);
  const m = .004;
  const [s, n, o, e] = [Math.min(...lat) - m, Math.max(...lat) + m, Math.min(...lon) - m, Math.max(...lon) + m];
  const x = (lo, z) => Math.floor((lo + 180) / 360 * 2 ** z);
  const y = (la, z) => Math.floor((1 - Math.log(Math.tan(rad(la)) + 1 / Math.cos(rad(la))) / Math.PI) / 2 * 2 ** z);
  const urls = [];
  for (let z = 14; z <= 18; z++)
    for (let i = x(o, z); i <= x(e, z); i++)
      for (let j = y(n, z); j <= y(s, z); j++) {
        urls.push(`https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/${z}/${j}/${i}`);
        if (z <= 17) urls.push(`https://tile.openstreetmap.org/${z}/${i}/${j}.png`);
      }
  return urls;
}
$('#btn-descargar').onclick = async () => {
  if (!('caches' in window)) { toast('Este navegador no permite guardar para usar sin señal.'); return; }
  const locales = ['img/portada.webp', TOUR.intro_audio.src];
  TOUR.sitios.forEach(s => { locales.push(s.audio.src); s.fotos.forEach(f => locales.push(f.a, f.b)); s.historicas.forEach(h => locales.push(h.src)); });
  const tiles = tilesRuta();
  const total = locales.length + tiles.length;
  const prog = $('#descarga-prog'); prog.hidden = false;
  let hechos = 0, fallos = 0;
  const avanzar = () => { hechos++; prog.firstElementChild.style.width = (hechos / total * 100) + '%'; prog.lastElementChild.textContent = `${hechos} / ${total}`; };
  const cLoc = await caches.open('gpm-medios'), cTil = await caches.open('gpm-teselas');
  const cola = [...locales.map(u => [cLoc, new URL(u, location.href).href, 'same-origin']), ...tiles.map(u => [cTil, u, 'no-cors'])];
  $('#btn-descargar').disabled = true;
  const trabajador = async () => {
    while (cola.length) {
      const [c, u, modo] = cola.shift();
      try {
        if (!(await c.match(u))) { const r = await fetch(u, { mode: modo }); if (r.ok || r.type === 'opaque') await c.put(u, r); else fallos++; }
      } catch { fallos++; }
      avanzar();
    }
  };
  await Promise.all(Array.from({ length: 6 }, trabajador));
  $('#btn-descargar').disabled = false;
  prog.lastElementChild.textContent = fallos ? `Listo (${fallos} sin descargar, reintenta con mejor señal)` : '✓ Listo para usar sin señal';
  store.set('descargado', new Date().toISOString());
};

/* ---------- instalar / pantalla completa ---------- */
// Ningún navegador permite pantalla completa sin un toque: se pide en el primer toque de cada visita.
// iPhone no tiene Fullscreen API → la única forma sin barra es "Agregar a pantalla de inicio" (guía).
const INSTALADA = ['standalone', 'fullscreen'].some(m => matchMedia(`(display-mode: ${m})`).matches) || navigator.standalone === true;
const ES_IOS = /iphone|ipad|ipod/i.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
const PUEDE_FS = !INSTALADA && !!document.fullscreenEnabled;
const CADA_RECORDATORIO = 3 * 864e5;
let pedidoInstalar = null;
function pantallaCompleta() {
  if (!PUEDE_FS || document.fullscreenElement || !store.get('pantalla-completa', true)) return;
  document.documentElement.requestFullscreen({ navigationUI: 'hide' }).catch(() => { });
}
function alternarPantalla() {
  if (document.fullscreenElement) { store.set('pantalla-completa', false); document.exitFullscreen().catch(() => { }); }
  else { store.set('pantalla-completa', true); pantallaCompleta(); }
}
if (PUEDE_FS) {
  const primerToque = e => {
    // los botones de instalar necesitan el gesto para sí (requestFullscreen lo consume)
    if (e.target.closest && e.target.closest('.btn-instalar, #btn-fs, #toast button, #hoja')) return;
    document.removeEventListener('click', primerToque, true);
    pantallaCompleta();
  };
  document.addEventListener('click', primerToque, true);
  document.addEventListener('fullscreenchange', () => $('#btn-fs').classList.toggle('activo', !!document.fullscreenElement));
}
window.addEventListener('beforeinstallprompt', e => {
  e.preventDefault(); pedidoInstalar = e; mostrarInstalar();
  if (store.get('visitado')) setTimeout(recordarInstalar, 5000);
});
window.addEventListener('appinstalled', () => { pedidoInstalar = null; mostrarInstalar(); toast('¡Listo! Ábrela desde el ícono <b>GeoParquemet</b> de tu teléfono', null, null, 8000); });
function mostrarInstalar() {
  const ver = !INSTALADA && !!(pedidoInstalar || ES_IOS);
  $$('.btn-instalar').forEach(b => b.hidden = !ver);
  $('#btn-fs').hidden = !PUEDE_FS;
}
function instalar() {
  if (pedidoInstalar) {
    pedidoInstalar.prompt();
    pedidoInstalar.userChoice.finally(() => { pedidoInstalar = null; mostrarInstalar(); });
  } else if (ES_IOS) guiaIOS(true);
}
$$('.btn-instalar').forEach(b => b.onclick = instalar);
const ICO_COMPARTIR = '<svg class="ico-compartir" viewBox="0 0 24 24" aria-label="Compartir"><path d="M12 3v12M7.5 7.5 12 3l4.5 4.5M8 10H6v11h12V10h-2" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
function guiaIOS(manual) {
  const chrome = /CriOS/.test(navigator.userAgent);
  const ipad = /ipad/i.test(navigator.userAgent) || navigator.platform === 'MacIntel';
  store.set('guia-instalar', { ...store.get('guia-instalar', {}), ts: Date.now() });
  hoja(`<h3>📲 Úsala como app, en pantalla completa</h3><p>Agrega GeoParquemet a tu pantalla de inicio: se abre sin la barra del navegador y funciona sin señal en el cerro.</p>
    <ol class="pasos-ios">
      <li><span>Toca el botón <b>Compartir</b> ${ICO_COMPARTIR} ${chrome ? 'junto a la barra de direcciones' : 'de Safari'}</span></li>
      <li><span>Desliza y elige <b>«Agregar a pantalla de inicio»</b> ➕</span></li>
      <li><span>Abre <b>GeoParquemet</b> desde el nuevo ícono</span></li>
    </ol>
    <div class="fila-botones"><button class="btn primario cerrar-hoja">Entendido</button>${manual ? '' : '<button class="btn peque cerrar-hoja" id="ios-nunca">No volver a mostrar</button>'}</div>
    <div class="flecha-compartir ${ipad || chrome ? 'arriba' : 'abajo'}" aria-hidden="true">${ipad || chrome ? '⬆' : '⬇'}</div>`);
  const nunca = $('#ios-nunca');
  if (nunca) nunca.addEventListener('click', () => store.set('guia-instalar', { nunca: true, ts: Date.now() }));
}
// Primera visita: ofrece instalar apenas la persona elige un modo
function ofrecerInstalar() {
  if (INSTALADA || store.get('guia-instalar', {}).ts) return;
  if (ES_IOS) setTimeout(() => guiaIOS(false), 900);
  else if (pedidoInstalar) {
    store.set('guia-instalar', { ts: Date.now() });
    setTimeout(() => hoja(`<h3>📲 Instala GeoParquemet</h3><p>Queda como una app en tu teléfono: pantalla completa, sin la barra del navegador y funciona sin señal en el cerro.</p>
      <div class="fila-botones"><button class="btn primario cerrar-hoja" id="hoja-instalar">Instalar</button><button class="btn peque cerrar-hoja">Ahora no</button></div>`), 900);
  }
}
document.addEventListener('click', e => { if (e.target.id === 'hoja-instalar') instalar(); });
// Recordatorio discreto en visitas posteriores, como máximo cada 3 días
function recordarInstalar() {
  if (INSTALADA || !$('#hoja').hidden) return;
  const g = store.get('guia-instalar', {});
  if (g.nunca || Date.now() - (g.ts || 0) < CADA_RECORDATORIO) return;
  if (ES_IOS) { store.set('guia-instalar', { ...g, ts: Date.now() }); toast('📲 Úsala sin la barra del navegador', '¿Cómo?', () => guiaIOS(false), 9000); }
  else if (pedidoInstalar) { store.set('guia-instalar', { ...g, ts: Date.now() }); toast('📲 Instálala: pantalla completa y funciona sin señal', 'Instalar', instalar, 9000); }
}
$('#btn-fs').onclick = alternarPantalla;

/* ---------- pantalla encendida durante la guía ---------- */
let wake = null;
async function mantenerPantalla() {
  if (E.modo !== 'terreno' || $('#v-mapa').hidden || !('wakeLock' in navigator) || wake) return;
  try { wake = await navigator.wakeLock.request('screen'); wake.addEventListener('release', () => wake = null); } catch { }
}
document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') mantenerPantalla(); });
window.addEventListener('hashchange', () => { if (location.hash === '#/mapa') mantenerPantalla(); else if (wake) { wake.release(); wake = null; } });

/* ---------- inicio ---------- */
async function iniciar() {
  const [t, g, geo] = await Promise.all(['data/tour.json', 'data/glosario.json', 'data/geologia.geojson'].map(u => fetch(u).then(r => r.json())));
  TOUR = t; GLOS = g; GEOL = geo;
  pintarInicio(); pintarInfo(); mostrarInstalar();
  if (store.get('visitado')) setTimeout(recordarInstalar, 5000);
  store.set('visitado', true);
  if (E.modo === 'terreno') { iniciarGPS(); escucharBrujula(); }
  ruta();
  if ('serviceWorker' in navigator) navigator.serviceWorker.register('sw.js').catch(() => { });
}
iniciar();
