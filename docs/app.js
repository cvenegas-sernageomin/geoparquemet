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

/* ---------- idioma ---------- */
const IDIOMAS = ['es', 'en', 'pt'];
function idiomaInicial() {
  const g = store.get('idioma', null);
  if (IDIOMAS.includes(g)) return g;
  const n = (navigator.languages || [navigator.language || 'es']).map(l => l.slice(0, 2).toLowerCase());
  return n.find(l => IDIOMAS.includes(l)) || 'es';
}
let LANG = idiomaInicial();
const t = (k, v) => {
  let s = (TXT[LANG] && TXT[LANG][k]) ?? TXT.es[k] ?? k;
  if (v && typeof s === 'string') s = s.replace(/\{(\w+)\}/g, (_, x) => v[x] ?? '');
  return s;
};

// BASE = contenidos en español; TOUR/GLOS/QUIZ = contenidos en el idioma activo
const BASE = {}; const LDATA = {};
let TOUR, GLOS, GEOL, QUIZ, GEO_L = {}, RA = {};  // RA: geositios con realidad aumentada (ar/objetivos.json)
const E = {
  modo: store.get('modo', null),          // 'terreno' | 'virtual'
  sellos: store.get('sellos', {}),        // n -> fecha ISO (llegada física)
  vistos: store.get('vistos', {}),        // n -> fecha ISO (ficha abierta)
  quiz: store.get('quiz', {}),            // n -> true (acertó) | false (falló)
  ajustes: Object.assign({ auto: true, vibrar: true }, store.get('ajustes', {})),
  pos: null, rumbo: null, rumboFuente: null,
  objetivo: null, avisados: new Set(), fichaN: null,
};

function componerDatos() {
  const L = LANG === 'es' ? null : LDATA[LANG];
  TOUR = JSON.parse(JSON.stringify(BASE.tour));
  GLOS = BASE.glos; QUIZ = BASE.quiz; GEO_L = {};
  if (!L) return;
  Object.assign(TOUR, { intro: L.intro, aviso: L.aviso, ruta: L.ruta });
  if (L.intro_audio) TOUR.intro_audio = L.intro_audio;
  TOUR.sitios.forEach(s => {
    const x = L.sitios[s.n]; if (!x) return;
    Object.assign(s, { titulo: x.titulo, cap: x.cap, texto: x.texto, texto_web: x.texto_web });
    if (x.audio) s.audio = x.audio;
  });
  GLOS = Object.assign({}, BASE.glos, L.glosario);
  QUIZ = Object.assign({}, BASE.quiz, L.quiz);
  GEO_L = L.geologia || {};
}
async function cargarIdioma(l) {
  if (l !== 'es' && !LDATA[l]) LDATA[l] = await fetch(`data/lang_${l}.json`).then(r => r.json());
}
async function cambiarIdioma(l) {
  if (!IDIOMAS.includes(l)) return;
  try { await cargarIdioma(l); } catch { toast('Sin conexión / No connection'); return; }
  const sonaba = audioN != null && !audio.paused;
  LANG = l; store.set('idioma', l);
  componerDatos();
  traducirHTML(); pintarInicio(); pintarInfo(); refrescarMapa(); actualizarGuia();
  if (!$('#v-pasaporte').hidden) pintarPasaporte();
  if (audioN != null) { const n = audioN; audioN = null; audio.pause(); if (sonaba) reproducir(n); else $('#reproductor').hidden = true; }
  if (E.fichaN) abrirFicha(E.fichaN);
}
function traducirHTML() {
  document.documentElement.lang = LANG;
  $$('[data-t]').forEach(el => el.textContent = t(el.dataset.t));
  $$('[data-th]').forEach(el => el.innerHTML = t(el.dataset.th));
  $$('[data-t-ph]').forEach(el => el.placeholder = t(el.dataset.tPh));
  $$('[data-t-aria]').forEach(el => el.setAttribute('aria-label', t(el.dataset.tAria)));
  $$('.banderas button').forEach(b => b.classList.toggle('activo', b.dataset.lang === LANG));
}
document.addEventListener('click', e => { const b = e.target.closest('.banderas button'); if (b) cambiarIdioma(b.dataset.lang); });

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
const cardinal = g => t('puntos')[Math.round(g / 45) % 8];
const fmtDist = m => m < 1000 ? `${Math.round(m / 5) * 5} m` : `${(m / 1000).toFixed(1).replace('.', LANG === 'en' ? '.' : ',')} km`;
const minutosAPie = m => Math.max(1, Math.round(m / 65));  // ~4 km/h en subida suave

/* ---------- texto con términos de glosario ---------- */
function conTerminos(s) {
  return esc(s).replace(/\[\[([^|\]]+)\|([^\]]+)\]\]/g, (_, slug, txt) =>
    GLOS && GLOS[slug] ? `<button class="term" data-term="${slug}">${txt}</button>` : txt);
}
const planoTxt = s => s.replace(/\[\[[^|\]]+\|([^\]]+)\]\]/g, '$1');
document.addEventListener('click', e => {
  const b = e.target.closest('.term');
  if (b) { e.preventDefault(); verTermino(b.dataset.term); }
});
function verTermino(slug) {
  const g = GLOS[slug]; if (!g) return;
  hoja(`<button class="cerrar" aria-label="✕">✕</button><h3>${esc(g.t)}</h3>${g.d.map(p => `<p>${conTerminos(p)}</p>`).join('')}`);
}
// Textos de la capa geológica (los de ArcGIS vienen cortados a 254 caracteres: se corta en la última oración completa)
function geoTxt(p) {
  const L = GEO_L[p.unidad];
  if (L) return L;
  const d = p.desc || '', i = d.lastIndexOf('.');
  return { unidad: p.unidad, nombre: p.nombre, edad: p.edad, desc: i > 40 ? d.slice(0, i + 1) : d };
}

/* ---------- hoja / toast ---------- */
function hoja(html) {
  $('#hoja-in').innerHTML = html; $('#hoja').hidden = false;
  $('#hoja-in').scrollTop = 0;
}
$('#hoja').addEventListener('click', e => { if (e.target.id === 'hoja' || e.target.closest('.cerrar, .cerrar-hoja')) $('#hoja').hidden = true; });
let toastT;
function toast(msg, boton, accion, ms = 6000) {
  const el = $('#toast');
  el.innerHTML = `<span>${msg}</span>` + (boton ? `<button>${boton}</button>` : '');
  el.hidden = false;
  if (boton) el.querySelector('button').onclick = () => { el.hidden = true; accion(); };
  clearTimeout(toastT); toastT = setTimeout(() => el.hidden = true, ms);
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
  $('#datos-ruta').innerHTML = `<span>🥾 ${fmtDist(TOUR.largo_m)}</span><span>📍 ${n} ${t('geositios')}</span><span>⛰️ ${Math.min(...TOUR.sitios.map(s => s.elev))}–${Math.max(...TOUR.sitios.map(s => s.elev))} ${t('msnm')}</span><span>⏱️ ~2 h</span>`;
  $('#intro-txt').innerHTML = TOUR.intro.map(p => `<p>${conTerminos(p)}</p>`).join('') + `<p><b>⚠️ ${esc(TOUR.aviso)}</b></p>`;
  pintarLista();
  $('#modo-terreno').classList.toggle('activo', E.modo === 'terreno');
  $('#modo-virtual').classList.toggle('activo', E.modo === 'virtual');
}
function pintarLista() {
  $('#lista').innerHTML = TOUR.sitios.map(s => {
    const est = E.sellos[s.n] ? '✅' : E.vistos[s.n] ? '👁️' : '';
    const d = E.pos ? ` · ${t('a_d', { d: fmtDist(distancia(E.pos.lat, E.pos.lon, s.lat, s.lon)) })}` : '';
    const img = s.fotos[0] ? s.fotos[0].a : s.historicas[0]?.src;
    return `<li><button data-n="${s.n}"><img src="${img}" alt="" loading="lazy"><div><div class="num">${t('geositio')} ${s.n}</div><div class="tit">${esc(s.titulo)}</div><div class="meta">${s.elev} ${t('msnm')}${d}</div></div><span class="estado">${est}</span></button></li>`;
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
let encuadrado = false;  // true después del primer encuadre con posición GPS
function mostrarMapa() {
  if (!mapa) crearMapa();
  else setTimeout(() => { mapa.invalidateSize(); if (!encuadrado && E.pos) encuadrarInicio(); }, 50);
  if (E.modo === 'terreno') iniciarGPS();
  actualizarGuia();
}
function popupGeol(p) {
  const g = geoTxt(p);
  return `<h4>${esc(g.unidad)}</h4><div><b>${esc(g.nombre)}</b>${p.codigo ? ` (${esc(p.codigo)})` : ''}</div><div>${esc(g.edad)}</div><p>${esc(g.desc)}</p>${p.termino && GLOS[p.termino] ? `<button class="term" data-term="${p.termino}">${t('leer_mas')}</button>` : ''}`;
}
function crearMapa() {
  mapa = L.map('mapa', { zoomControl: false, attributionControl: true, maxZoom: 20 });
  // la vista se fija ANTES de agregar capas: si la capa de geología se agrega a un mapa sin vista, Leaflet falla al dibujarla
  // y ya no dibuja la ruta ni los geositios
  encuadrarRuta(false);
  capaSat = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    { maxNativeZoom: 19, maxZoom: 20, attribution: '© Esri' }).addTo(mapa);
  capaCalles = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    { maxNativeZoom: 19, maxZoom: 20, attribution: '© OpenStreetMap' });
  capaGeol = L.geoJSON(GEOL, {
    style: f => ({ color: COLORES[f.properties.unidad] || '#999', weight: 1.5, fillOpacity: .33 }),
    // margen para que el popup no quede bajo los botones de la derecha ni bajo el panel de guía
    onEachFeature: (f, l) => l.bindPopup(() => popupGeol(f.properties), { maxWidth: Math.min(280, innerWidth - 120), minWidth: Math.min(200, innerWidth - 120), autoPanPaddingTopLeft: [12, 12], autoPanPaddingBottomRight: [70, 110] }),
  });
  // Leaflet dibuja los popups dentro de su propia capa (z-index 400), bajo la leyenda: se oculta la leyenda mientras hay uno abierto
  mapa.on('popupopen', () => $('#leyenda').classList.add('oculta'));
  mapa.on('popupclose', () => $('#leyenda').classList.remove('oculta'));
  if (store.get('geologia', false)) { capaGeol.addTo(mapa); $('#btn-geol').classList.add('activo'); }
  L.polyline(TOUR.ruta_coords, { color: '#000', weight: 8, opacity: .35 }).addTo(mapa);
  L.polyline(TOUR.ruta_coords, { color: '#ffc766', weight: 4, dashArray: '10 8' }).addTo(mapa);
  TOUR.sitios.forEach(s => {
    const m = L.marker([s.lat, s.lon], { icon: iconoSitio(s.n), zIndexOffset: 100 }).addTo(mapa);
    m.bindTooltip(() => `${s.n}. ${TOUR.sitios[s.n - 1].titulo}`, { direction: 'top', offset: [0, -30] });
    m.on('click', () => location.hash = '#/g/' + s.n);
    marcadores[s.n] = m;
  });
  // la posición pudo llegar antes de crear el mapa; se dibuja cuando Leaflet terminó de preparar sus capas
  mapa.whenReady(() => setTimeout(() => { if (E.pos) { nuevaPos(E.pos); encuadrarInicio(); } }, 0));
  mapa.on('dragstart', () => { siguiendo = false; $('#btn-gps').classList.remove('sigue'); });
  pintarLeyenda();
}
// Encuadre al tener la primera posición: solo se sigue a la persona si ya está sobre la ruta;
// si no, se muestra la Geo-Ruta completa junto con su posición (así nunca queda la ruta fuera de pantalla)
function distanciaARuta(p) {
  return Math.min(...TOUR.ruta_coords.map(c => distancia(p.lat, p.lon, c[0], c[1])), ...TOUR.sitios.map(s => distancia(p.lat, p.lon, s.lat, s.lon)));
}
function encuadrarRuta(conPosicion) {
  const b = L.latLngBounds(TOUR.ruta_coords);
  if (conPosicion && E.pos) b.extend([E.pos.lat, E.pos.lon]);
  mapa.fitBounds(b, { paddingTopLeft: [20, 20], paddingBottomRight: [70, E.modo === 'terreno' ? 110 : 30], maxZoom: 17 });
}
function encuadrarInicio() {
  if (!mapa || !E.pos) return;
  encuadrado = true;
  const d = distanciaARuta(E.pos);
  if (d < 250) { siguiendo = true; $('#btn-gps').classList.add('sigue'); mapa.setView([E.pos.lat, E.pos.lon], 17); return; }
  siguiendo = false; $('#btn-gps').classList.remove('sigue');
  if (d > 4000) { encuadrarRuta(false); toast(t('lejos'), null, null, 8000); }
  else encuadrarRuta(true);
}
$('#btn-ruta').onclick = () => { siguiendo = false; $('#btn-gps').classList.remove('sigue'); encuadrarRuta(!!E.pos && distanciaARuta(E.pos) < 4000); };
function refrescarMapa() { if (mapa) { mapa.closePopup(); pintarLeyenda(); } }
function iconoSitio(n) {
  const c = E.sellos[n] ? 'sellado' : '';
  const o = objetivoActual()?.n === n ? 'objetivo' : '';
  return L.divIcon({ className: '', html: `<div class="marcador ${c} ${o}"><span>${n}</span></div>`, iconSize: [34, 34], iconAnchor: [17, 38] });
}
function refrescarMarcadores() { if (mapa) TOUR.sitios.forEach(s => marcadores[s.n].setIcon(iconoSitio(s.n))); }
function pintarLeyenda() {
  const on = mapa && mapa.hasLayer(capaGeol);
  $('#leyenda').hidden = !on;
  $('#leyenda').innerHTML = `<b>${t('a_geol')}</b>` + Object.entries(COLORES).map(([k, c]) => `<div><i style="background:${c}"></i>${esc(geoTxt({ unidad: k }).unidad)}</div>`).join('') + `<div><i style="background:#ffc766;height:4px;border:0"></i>${t('ruta_corta')}</div>`;
}
$('#btn-capas').onclick = () => {
  if (mapa.hasLayer(capaSat)) { mapa.removeLayer(capaSat); capaCalles.addTo(mapa); toast(t('mapa_calles')); }
  else { mapa.removeLayer(capaCalles); capaSat.addTo(mapa); toast(t('mapa_sat')); }
  capaCalles.bringToBack(); capaSat.bringToBack();
};
$('#btn-geol').onclick = () => {
  const on = !mapa.hasLayer(capaGeol);
  if (on) capaGeol.addTo(mapa); else mapa.removeLayer(capaGeol);
  $('#btn-geol').classList.toggle('activo', on); store.set('geologia', on); pintarLeyenda();
  if (on) toast(t('toca_color'));
};
$('#btn-gps').onclick = () => {
  if (!E.pos) { iniciarGPS(); toast(t('buscando')); return; }
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
    if (err.code === 1) toast(t('gps_perm'), t('virtual'), () => location.hash = '#/g/1', 9000);
    else toast(t('gps_err'));
  }, { enableHighAccuracy: true, maximumAge: 4000, timeout: 30000 });
}
window.__simular = (lat, lon, acc = 6) => nuevaPos({ lat, lon, acc });

function nuevaPos(p) {
  E.pos = p;
  if (p.vel > 0.8 && p.rumbo != null && !isNaN(p.rumbo) && E.rumboFuente !== 'brujula') { E.rumbo = p.rumbo; E.rumboFuente = 'gps'; }
  if (mapa) {
    const ll = [p.lat, p.lon];
    if (!yoMarca) {
      yoMarca = L.marker(ll, { icon: L.divIcon({ className: '', html: '<div class="yo"><div class="cono"></div></div>', iconSize: [20, 20], iconAnchor: [10, 10] }), zIndexOffset: 1000, interactive: false }).addTo(mapa);
      yoCirculo = L.circle(ll, { radius: p.acc, color: '#1a73e8', weight: 1, fillOpacity: .1, interactive: false }).addTo(mapa);
    } else { yoMarca.setLatLng(ll); yoCirculo.setLatLng(ll).setRadius(p.acc); }
    if (!encuadrado && !$('#v-mapa').hidden) encuadrarInicio();
    else if (siguiendo) mapa.panTo(ll, { animate: true });
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
      g.hidden = false; $('#guia-txt').innerHTML = `<b>${t('ruta_ok')}</b><small>${t('revisa_pas')}</small>`;
      $('#guia-abrir').textContent = t('ver'); $('#guia-abrir').onclick = () => location.hash = '#/pasaporte';
    }
    return;
  }
  const d = distancia(E.pos.lat, E.pos.lon, obj.lat, obj.lon);
  g.hidden = false;
  if (!$('#v-mapa').hidden) document.body.classList.add('con-guia');
  $('#guia-txt').innerHTML = `<small>${t('siguiente', { n: obj.n })}</small><b>${esc(obj.titulo)}</b><span class="dist">${fmtDist(d)}</span> <small>${t('hacia', { c: cardinal(rumboHacia(E.pos.lat, E.pos.lon, obj.lat, obj.lon)) })} · ~${minutosAPie(d)} min</small>`;
  $('#guia-abrir').textContent = t('ver');
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
  f.title = conRumbo ? t('apunta') : t('dir_norte');
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
      toast(t('acercas', { n: s.n, t: esc(s.titulo), d: fmtDist(d) }), t('ver'), () => location.hash = '#/g/' + s.n);
    }
  }
}
function llegar(s) {
  E.sellos[s.n] = new Date().toISOString(); store.set('sellos', E.sellos);
  if (E.objetivo === s.n) E.objetivo = null;
  vibrar([180, 80, 180]);
  const a = $('#sello-anim');
  a.innerHTML = `<div><span><b>${s.n}</b>${t('sello_ok')}</span></div>`; a.hidden = false;
  setTimeout(() => a.hidden = true, 1900);
  refrescarMarcadores(); pintarLista();
  const abrir = () => { location.hash = '#/g/' + s.n; setTimeout(() => reproducir(s.n), 400); };
  if (E.ajustes.auto && !E.fichaN) setTimeout(abrir, 1500);
  else toast(t('llegaste', { n: s.n, t: esc(s.titulo) }), t('escuchar'), abrir, 10000);
}

/* ---------- ficha ---------- */
function abrirFicha(n) {
  const s = TOUR.sitios[n - 1]; if (!s) { location.hash = '#/'; return; }
  const misma = E.fichaN === n, scroll = misma ? $('#ficha-scroll').scrollTop : 0;
  E.fichaN = n;
  if (!E.vistos[n]) { E.vistos[n] = new Date().toISOString(); store.set('vistos', E.vistos); }
  const total = TOUR.sitios.length;
  const d = E.pos ? distancia(E.pos.lat, E.pos.lon, s.lat, s.lon) : null;
  const est = E.sellos[n] ? t('sellado') : E.vistos[n] ? t('visto') : '';
  const ytimg = id => `https://i.ytimg.com/vi/${id}/hqdefault.jpg`;
  const sv = `https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${s.sv[0]},${s.sv[1]}&heading=${s.sv[2]}&pitch=${s.sv[3]}`;
  const comoLlegar = `https://www.google.com/maps/dir/?api=1&destination=${s.lat},${s.lon}&travelmode=walking`;
  const off = s.texto.length + 1;
  $('#ficha-scroll').innerHTML = `
    <div class="f-cab">
      <button id="f-volver" aria-label="${t('volver')}">←</button>
      <span class="f-num">${t('n_de', { n, t: total })}</span>
      <button id="f-ant" ${n === 1 ? 'disabled style="opacity:.3"' : ''} aria-label="${t('anterior')}">‹</button>
      <button id="f-sig" ${n === total ? 'disabled style="opacity:.3"' : ''} aria-label="${t('sig')}">›</button>
    </div>
    ${comparadores(s)}
    <div class="f-cuerpo">
      <h2>${esc(s.titulo)}</h2>
      <div class="f-meta">${s.elev} ${t('msnm')} · ${s.lat.toFixed(5)}, ${s.lon.toFixed(5)}${d != null ? ` · ${t('de_ti', { d: fmtDist(d) })}` : ''} ${est ? '· ' + est : ''}</div>
      <div class="banderas chica" role="group" aria-label="${t('idioma')}">${BANDERAS}</div>
      <div class="f-acciones">
        <button class="btn escuchar" id="f-escuchar">${t('escuchar_min', { m: Math.max(1, Math.round(s.audio.dur / 60)) })}</button>
        ${E.modo === 'terreno' && !E.sellos[n] ? `<button class="btn" id="f-llevar">${t('llevarme')}</button>` : ''}
        <a class="btn" href="${sv}" target="_blank" rel="noopener">👁️ Street View</a>
      </div>
      ${RA[n] ? `<a class="btn primario btn-ra" href="ar.html?g=${n}">${t('ra_btn')}</a>` : ''}
      <div id="f-texto">${s.texto.map((p, i) => `<p data-i="${i + 1}">${conTerminos(p)}</p>`).join('')}</div>
      ${s.texto_web.length ? `<div class="caja-web"><h3>${t('observa')}</h3>${s.texto_web.map((p, i) => `<p data-i="${off + i}">${conTerminos(p)}</p>`).join('')}</div>` : ''}
      ${s.historicas.map(h => `<h3 class="sec">${t('piscina_t')}</h3><img class="foto-hist" src="${h.src}" alt="${t('piscina_alt')}" loading="lazy" width="${h.w}" height="${h.h}">`).join('')}
      ${s.sketchfab.length ? `<h3 class="sec">${t('modelo3d')}</h3>` + s.sketchfab.map(id => `<div class="embed" data-src="https://sketchfab.com/models/${id}/embed?autostart=1&ui_infos=0&ui_watermark=0&preload=1"><button class="cargar"><span>${t('cargar3d')}</span></button></div>`).join('') : ''}
      ${s.seequent.map(u => `<p><a href="${u}" target="_blank" rel="noopener">${t('seequent')}</a></p>`).join('')}
      ${s.youtube.length ? `<h3 class="sec">${t('videos')}</h3>` + s.youtube.map(id => `<div class="embed" data-src="https://www.youtube-nocookie.com/embed/${id}?autoplay=1&rel=0"><button class="cargar" style="background-image:url(${ytimg(id)})"><span>${t('ver_video')}</span></button></div>`).join('') : ''}
      ${quizHTML(n)}
      <p><a class="btn" href="${comoLlegar}" target="_blank" rel="noopener">${t('como_llegar')}</a></p>
      <div class="f-acciones">
        ${n > 1 ? `<a class="btn" href="#/g/${n - 1}">‹ ${t('geositio')} ${n - 1}</a>` : ''}
        ${n < total ? `<a class="btn primario" href="#/g/${n + 1}">${t('geositio')} ${n + 1} ›</a>` : `<a class="btn primario" href="#/pasaporte">${t('ver_pas')}</a>`}
      </div>
    </div>`;
  traducirHTML();
  const f = $('#ficha');
  f.hidden = false; document.body.classList.add('ficha-abierta');
  $('#ficha-scroll').scrollTop = scroll;
  $('#f-volver').onclick = () => location.hash = ultimaVista === 'inicio' ? '#/' : '#/' + ultimaVista;
  $('#f-ant').onclick = () => location.hash = '#/g/' + (n - 1);
  $('#f-sig').onclick = () => location.hash = '#/g/' + (n + 1);
  $('#f-escuchar').onclick = () => reproducir(n);
  const ll = $('#f-llevar'); if (ll) ll.onclick = () => { E.objetivo = n; refrescarMarcadores(); location.hash = '#/mapa'; };
  $$('#ficha .embed').forEach(el => el.querySelector('.cargar').onclick = () => {
    el.innerHTML = `<iframe src="${el.dataset.src}" allow="autoplay; fullscreen; xr-spatial-tracking; accelerometer; gyroscope" allowfullscreen loading="lazy"></iframe>`;
  });
  activarComparadores();
  activarQuiz(n);
  pActivo = null; resaltarParrafo();
}
function cerrarFicha() {
  if ($('#ficha').hidden) return;
  $('#ficha').hidden = true; E.fichaN = null;
  document.body.classList.remove('ficha-abierta');
  $('#ficha-scroll').innerHTML = '';
  pintarLista();
}

/* ---------- quiz: una pregunta por geositio ---------- */
function quizHTML(n) {
  const q = QUIZ[n]; if (!q) return '';
  // orden de alternativas fijo por geositio pero no siempre la correcta primero
  const orden = q.r.map((x, i) => ({ x, i })).sort((a, b) => ((a.i * 7 + n * 3) % 5) - ((b.i * 7 + n * 3) % 5));
  const hecho = n in E.quiz;
  return `<div class="quiz" id="quiz"><h3>${t('pregunta')}</h3><p class="preg">${esc(q.p)}</p>
    <div class="ops">${orden.map(o => `<button data-i="${o.i}" ${hecho ? 'disabled' : ''} class="${hecho && o.i === 0 ? 'ok' : ''}">${esc(o.x)}</button>`).join('')}</div>
    <p class="expl" ${hecho ? '' : 'hidden'}>${hecho ? (E.quiz[n] ? t('correcto') : '📘 ') : ''}${esc(q.e)}</p></div>`;
}
function activarQuiz(n) {
  const c = $('#quiz'); if (!c || n in E.quiz) return;
  c.querySelector('.ops').onclick = e => {
    const b = e.target.closest('button[data-i]'); if (!b) return;
    const bien = b.dataset.i === '0';
    E.quiz[n] = bien; store.set('quiz', E.quiz);
    c.querySelectorAll('.ops button').forEach(x => { x.disabled = true; if (x.dataset.i === '0') x.classList.add('ok'); });
    if (!bien) b.classList.add('mal');
    const ex = c.querySelector('.expl');
    ex.textContent = (bien ? t('correcto') : t('no_era')) + QUIZ[n].e; ex.hidden = false;
    vibrar(bien ? [60, 40, 60] : 200);
  };
}

function comparadores(s) {
  if (!s.fotos.length) return '';
  const mini = s.fotos.length > 1 ? `<div class="galeria-mini" id="f-mini">${s.fotos.map((f, i) => `<button data-i="${i}" class="${i ? '' : 'activo'}"><img src="${f.b}" alt="${i + 1}" loading="lazy"></button>`).join('')}</div>` : '';
  return `<div class="f-cuerpo" style="padding-bottom:0">${compHTML(s.fotos[0])}<p class="pie">${t('desliza')} ${esc(s.cap)}</p>${mini}</div>`;
}
const compHTML = f => `<div class="comparador" id="f-comp"><img src="${f.a}" alt="${t('foto')}" width="${f.w}" height="${f.h}"><div class="capa-b"><img src="${f.b}" alt="${t('interp')}"></div><div class="barra"></div><div class="tirador">⇆</div><span class="etq a">${t('foto')}</span><span class="etq b">${t('interp')}</span></div>`;
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
  if (audioN !== n || !audio.src.endsWith(info.src)) {
    audioN = n; audio.src = info.src; audio.currentTime = 0;
    $('#rep-titulo').textContent = n === 0 ? t('intro_tit') : `${t('geositio')} ${n} · ${TOUR.sitios[n - 1].titulo}`;
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
  audio.playbackRate = VELS[i]; $('#rep-vel').textContent = String(VELS[i]).replace('.', LANG === 'en' ? '.' : ',') + '×';
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
  const aciertos = Object.values(E.quiz).filter(Boolean).length;
  $('#pas-resumen').textContent = t('pas_res', { s: hechos, n, v: vistos, q: aciertos });
  $('#sellos').innerHTML = TOUR.sitios.map(s => {
    const f = E.sellos[s.n];
    const cls = f ? 'hecho' : E.vistos[s.n] ? 'visto' : '';
    const pie = f ? new Date(f).toLocaleDateString(LOCALE[LANG], { day: 'numeric', month: 'short', year: 'numeric' }) : E.vistos[s.n] ? t('visto_v') : t('pendiente');
    return `<a class="sello ${cls}" href="#/g/${s.n}" style="text-decoration:none;color:inherit">${s.n in E.quiz ? `<span class="q" title="${t('respondida')}">${E.quiz[s.n] ? '🧠' : '📘'}</span>` : ''}<div class="circ">${f ? '✓' : s.n}</div><b>${esc(s.titulo)}</b><small>${pie}</small></a>`;
  }).join('');
  const fin = $('#pas-final');
  if (hechos === n) { fin.hidden = false; fin.innerHTML = `<h3>${t('fin_t')}</h3><p>${t('fin_p', { d: fmtDist(TOUR.largo_m) })}</p>`; }
  else if (vistos === n) { fin.hidden = false; fin.innerHTML = `<h3>${t('finv_t')}</h3><p>${t('finv_p', { n })}</p>`; }
  else fin.hidden = true;
}

/* ---------- saber más ---------- */
const sinTildes = s => s.toLowerCase().normalize('NFD').replace(/\p{M}/gu, '');
function pintarGlosario(q) {
  const orden = Object.entries(GLOS).sort((a, b) => a[1].t.localeCompare(b[1].t, LANG));
  q = sinTildes(q || '');
  $('#glosario').innerHTML = orden.filter(([, g]) => !q || sinTildes(g.t + ' ' + g.d.join(' ')).includes(q))
    .map(([k, g]) => `<dt><button class="term" data-term="${k}">${esc(g.t)}</button></dt><dd>${esc(planoTxt(g.d[0] || '')).slice(0, 150)}…</dd>`).join('') || `<p>${t('sin_res')}</p>`;
}
function pintarInfo() {
  pintarGlosario($('#buscar-glosario').value);
  $('#buscar-glosario').oninput = e => pintarGlosario(e.target.value);
  const unidades = new Map();
  GEOL.features.forEach(f => unidades.set(f.properties.unidad, f.properties));
  $('#unidades').innerHTML = [...unidades.values()].map(p => { const g = geoTxt(p); return `<div class="unidad"><i style="background:${COLORES[p.unidad] || '#999'}"></i><div><b>${esc(g.unidad)}</b> · ${esc(g.nombre)}<small>${esc(g.edad)}</small>${p.termino && GLOS[p.termino] ? `<button class="term" data-term="${p.termino}">${t('leer_mas')}</button>` : ''}</div></div>`; }).join('');
  $('#biblio').innerHTML = TOUR.bibliografia.map(b => `<li>${esc(b.t)}${b.url ? ` <a href="${esc(b.url)}" target="_blank" rel="noopener">${t('enlace')}</a>` : ''}</li>`).join('');
  $('#aj-auto').checked = E.ajustes.auto; $('#aj-vibrar').checked = E.ajustes.vibrar;
  $('#aj-auto').onchange = e => { E.ajustes.auto = e.target.checked; store.set('ajustes', E.ajustes); };
  $('#aj-vibrar').onchange = e => { E.ajustes.vibrar = e.target.checked; store.set('ajustes', E.ajustes); };
  $('#btn-reset').onclick = () => {
    if (!confirm(t('confirmar'))) return;
    E.sellos = {}; E.vistos = {}; E.quiz = {}; store.set('sellos', {}); store.set('vistos', {}); store.set('quiz', {}); E.avisados.clear();
    refrescarMarcadores(); pintarLista(); toast(t('reiniciado'));
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
  if (!('caches' in window)) { toast(t('no_cache')); return; }
  // se descarga la narración del idioma activo
  const locales = ['img/portada.webp', TOUR.intro_audio.src, `data/lang_${LANG}.json`].filter(u => !u.endsWith('lang_es.json'));
  TOUR.sitios.forEach(s => { locales.push(s.audio.src); s.fotos.forEach(f => locales.push(f.a, f.b)); s.historicas.forEach(h => locales.push(h.src)); });
  if (Object.keys(RA).length) {
    locales.push('ar.html', 'ar/objetivos.json', 'vendor/three/three.module.min.js', 'vendor/three/addons/renderers/CSS3DRenderer.js',
      'vendor/mindar/mindar-image-three.prod.js', 'vendor/mindar/controller-mGt1s8dJ.js', 'vendor/mindar/ui-fBadYuor.js');
    Object.values(RA).forEach(o => { locales.push(o.mind); o.pares.forEach(p => locales.push(p.obj, p.capa)); });
  }
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
        // la RA la guarda el service worker en su propia caché versionada: basta con pedirla
        if (u.includes('/ar/')) { const r = await fetch(u); if (!r.ok) fallos++; }
        else if (!(await c.match(u))) { const r = await fetch(u, { mode: modo }); if (r.ok || r.type === 'opaque') await c.put(u, r); else fallos++; }
      } catch { fallos++; }
      avanzar();
    }
  };
  await Promise.all(Array.from({ length: 6 }, trabajador));
  $('#btn-descargar').disabled = false;
  prog.lastElementChild.textContent = fallos ? t('listo_f', { f: fallos }) : t('listo');
  store.set('descargado', new Date().toISOString());
};

/* ---------- instalar / pantalla completa ---------- */
// Ningún navegador permite pantalla completa sin un toque: se pide en el primer toque de cada visita.
// iPhone no tiene Fullscreen API → la única forma sin barra es "Agregar a pantalla de inicio" (guía).
const INSTALADA = ['standalone', 'fullscreen'].some(m => matchMedia(`(display-mode: ${m})`).matches) || navigator.standalone === true;
const ES_IOS = /iphone|ipad|ipod/i.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
const PUEDE_FS = !INSTALADA && !!document.fullscreenEnabled;
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
    // los botones de instalar y de idioma no piden pantalla completa (requestFullscreen consume el gesto)
    if (e.target.closest && e.target.closest('.btn-instalar, #aviso-instalar, #btn-fs, #toast button, #hoja, .banderas')) return;
    document.removeEventListener('click', primerToque, true);
    pantallaCompleta();
  };
  document.addEventListener('click', primerToque, true);
  document.addEventListener('fullscreenchange', () => $('#btn-fs').classList.toggle('activo', !!document.fullscreenElement));
}
window.addEventListener('beforeinstallprompt', e => { e.preventDefault(); pedidoInstalar = e; mostrarInstalar(); });
window.addEventListener('appinstalled', () => { pedidoInstalar = null; instaladaAhora = true; mostrarInstalar(); toast(t('instalada'), null, null, 8000); });
let instaladaAhora = false;
// La invitación a instalar queda SIEMPRE visible mientras la app no esté instalada:
// si el navegador no ofrece su diálogo (iPhone, o Chrome tras un rechazo previo) se muestran los pasos manuales.
function mostrarInstalar() {
  const ver = !INSTALADA && !instaladaAhora;
  $$('.btn-instalar').forEach(b => b.hidden = !ver);
  $('#aviso-instalar').hidden = !ver;
  document.body.classList.toggle('con-aviso', ver);
  $('#btn-fs').hidden = !PUEDE_FS;
}
function instalar() {
  if (pedidoInstalar) {
    pedidoInstalar.prompt();
    pedidoInstalar.userChoice.then(r => { if (r.outcome === 'accepted') instaladaAhora = true; }).finally(() => { pedidoInstalar = null; mostrarInstalar(); });
  } else if (ES_IOS) guiaIOS();
  else guiaAndroid();
}
$$('.btn-instalar').forEach(b => b.onclick = instalar);
const ICO_COMPARTIR = '<svg class="ico-compartir" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v12M7.5 7.5 12 3l4.5 4.5M8 10H6v11h12V10h-2" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
function guiaIOS() {
  const chrome = /CriOS/.test(navigator.userAgent);
  const ipad = /ipad/i.test(navigator.userAgent) || navigator.platform === 'MacIntel';
  hoja(`${t('cab_inst')}
    <ol class="pasos-ios">
      <li><span>${t(chrome ? 'ios1c' : 'ios1', { ico: ICO_COMPARTIR })}</span></li>
      <li><span>${t('ios2')}</span></li>
      <li><span>${t('abre')}</span></li>
    </ol>
    <div class="fila-botones"><button class="btn primario cerrar-hoja">${t('entendido')}</button></div>
    <div class="flecha-compartir ${ipad || chrome ? 'arriba' : 'abajo'}" aria-hidden="true">${ipad || chrome ? '⬆' : '⬇'}</div>`);
}
function guiaAndroid() {
  const ua = navigator.userAgent;
  const samsung = /SamsungBrowser/.test(ua), firefox = /Firefox/.test(ua), movil = /Android/.test(ua);
  const pasos = samsung ? ['sam1', 'sam2', 'abre'] : firefox ? ['ff1', 'ff2', 'abre'] : movil ? ['ch1', 'ch2', 'ch3'] : ['pc1', 'pc2', 'pc3'];
  hoja(`${t('cab_inst')}<ol class="pasos-ios">${pasos.map(p => `<li><span>${t(p)}</span></li>`).join('')}</ol>
    <div class="fila-botones"><button class="btn primario cerrar-hoja">${t('entendido')}</button></div>
    ${movil && !samsung ? '<div class="flecha-compartir arriba derecha" aria-hidden="true">⬆</div>' : ''}${samsung ? '<div class="flecha-compartir abajo derecha" aria-hidden="true">⬇</div>' : ''}`);
}
// En cada visita (una vez por sesión) se ofrece instalar apenas la persona elige un modo
function ofrecerInstalar() {
  if (INSTALADA || instaladaAhora) return;
  try { if (sessionStorage.getItem('gpm-ofrecido')) return; sessionStorage.setItem('gpm-ofrecido', '1'); } catch { }
  setTimeout(() => {
    if (!$('#hoja').hidden) return;
    if (pedidoInstalar) hoja(`${t('cab_inst')}<div class="fila-botones"><button class="btn primario cerrar-hoja" id="hoja-instalar">${t('instalar_ya')}</button><button class="btn peque cerrar-hoja">${t('ahora_no')}</button></div>`);
    else instalar();
  }, 900);
}
document.addEventListener('click', e => { if (e.target.id === 'hoja-instalar') instalar(); });
$('#btn-fs').onclick = alternarPantalla;

/* ---------- pantalla encendida durante la guía ---------- */
let wake = null;
async function mantenerPantalla() {
  if (E.modo !== 'terreno' || $('#v-mapa').hidden || !('wakeLock' in navigator) || wake) return;
  try { wake = await navigator.wakeLock.request('screen'); wake.addEventListener('release', () => wake = null); } catch { }
}
document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') mantenerPantalla(); });
window.addEventListener('hashchange', () => { if (location.hash === '#/mapa') mantenerPantalla(); else if (wake) { wake.release(); wake = null; } });

/* ---------- banderas de idioma ---------- */
const BANDERAS = `
  <button data-lang="es" aria-label="Español"><svg viewBox="0 0 30 20"><rect width="30" height="20" fill="#d52b1e"/><rect width="30" height="10" fill="#fff"/><rect width="10" height="10" fill="#0039a6"/><path fill="#fff" d="M5 2.2l.73 2.25h2.37l-1.92 1.39.74 2.25L5 6.7 3.08 8.09l.74-2.25L1.9 4.45h2.37z"/></svg><span>ES</span></button>
  <button data-lang="en" aria-label="English"><svg viewBox="0 0 60 30"><clipPath id="gbc"><path d="M0 0v30h60V0z"/></clipPath><clipPath id="gbt"><path d="M30 15h30v15zv15H0zH0V0zV0h30z"/></clipPath><g clip-path="url(#gbc)"><path d="M0 0v30h60V0z" fill="#012169"/><path d="M0 0l60 30m0-30L0 30" stroke="#fff" stroke-width="6"/><path d="M0 0l60 30m0-30L0 30" clip-path="url(#gbt)" stroke="#C8102E" stroke-width="4"/><path d="M30 0v30M0 15h60" stroke="#fff" stroke-width="10"/><path d="M30 0v30M0 15h60" stroke="#C8102E" stroke-width="6"/></g></svg><span>EN</span></button>
  <button data-lang="pt" aria-label="Português"><svg viewBox="0 0 28 20"><rect width="28" height="20" fill="#009c3b"/><path d="M14 2.2 25.6 10 14 17.8 2.4 10z" fill="#ffdf00"/><circle cx="14" cy="10" r="4.6" fill="#002776"/><path d="M9.6 9.1c3-.6 6.2-.2 8.8 1.3" stroke="#fff" stroke-width=".8" fill="none"/></svg><span>PT</span></button>`;
$$('.banderas').forEach(b => b.innerHTML = BANDERAS);

/* ---------- arranque ---------- */
async function iniciar() {
  const [tour, g, geo, q] = await Promise.all(['data/tour.json', 'data/glosario.json', 'data/geologia.geojson', 'data/quiz.json'].map(u => fetch(u).then(r => r.json())));
  BASE.tour = tour; BASE.glos = g; BASE.quiz = q; GEOL = geo;
  RA = await fetch('ar/objetivos.json').then(r => r.json()).catch(() => ({}));
  try { await cargarIdioma(LANG); } catch { LANG = 'es'; }
  componerDatos();
  traducirHTML(); pintarInicio(); pintarInfo(); mostrarInstalar();
  store.set('visitado', true);
  if (E.modo === 'terreno') { iniciarGPS(); escucharBrujula(); }
  ruta();
  if ('serviceWorker' in navigator) navigator.serviceWorker.register('sw.js').catch(() => { });
}
iniciar();
