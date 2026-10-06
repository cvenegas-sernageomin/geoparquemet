// Prueba del estabilizador de la RA (docs/estabilizador.js) con un pulso de mano simulado, sin navegador:
//   node tools/probar_estabilizador.mjs
// Pantalla de 400×800; el objetivo ocupa casi toda la pantalla. El video muestra la roca donde está AHORA;
// el tracker entrega la pose con 50 ms de retraso, a 15 Hz y con ±1,5 px de ruido (parecido a MindAR en un teléfono).
import { crearGimbal, aplicar, I3 } from '../docs/estabilizador.js';

const W = 400, H = 800, caja = { l: -22, t: 0, w: 444, h: 800 };   // video "cover" como lo deja MindAR
const base = [[40, 120], [360, 120], [360, 547], [40, 547]];
let semilla = 7; const azar = () => ((semilla = (semilla * 16807) % 2147483647) / 2147483647 - .5) * 2;

// pose verdadera en pantalla: base + pulso (2-5 Hz, ±8 px ≈ 2 % y ±0,8°) + desplazamiento brusco opcional
function verdad(t, salto) {
  const P = 2 * Math.PI, dx = 8 * (Math.sin(P * 1.7 * t) + .6 * Math.sin(P * 3.9 * t + 1)) + (t > 3 ? salto : 0);
  const dy = 8 * (Math.cos(P * 2.1 * t) + .5 * Math.sin(P * 4.7 * t + 2)), r = .8 * Math.PI / 180 * Math.sin(P * 2.3 * t);
  return base.map(([x, y]) => { const u = x - 200, v = y - 333; return [200 + u * Math.cos(r) - v * Math.sin(r) + dx, 333 + u * Math.sin(r) + v * Math.cos(r) + dy]; });
}
const centro = q => [q.reduce((s, p) => s + p[0], 0) / q.length, q.reduce((s, p) => s + p[1], 0) / q.length];
const sd = a => { const m = a.reduce((s, x) => s + x, 0) / a.length; return Math.sqrt(a.reduce((s, x) => s + (x - m) ** 2, 0) / a.length); };

// sincronizado: la pantalla muestra el mismo cuadro que analizó el tracker (como hace ar.html), no el video en vivo
function correr(conGimbal, sincronizado, salto = 0, dur = 6) {
  const g = crearGimbal({ zoom: 1.08 }), fps = 60, dt = 1 / fps;
  let R = null, tCuadro = 0, tUlt = -1, sinVideo = 0;
  const roca = [], capa = [], desfase = [], llegada = [];
  for (let i = 0; i < dur * fps; i++) {
    const t = i * dt;
    if (t - tUlt >= 1 / 15) { tUlt = t; tCuadro = t - .05; R = verdad(tCuadro, salto).map(([x, y]) => [x + 1.5 * azar(), y + 1.5 * azar()]); }
    const M = conGimbal ? g.paso(R, dt, W, H, caja) : I3;
    if (conGimbal) {   // ¿se ve borde sin video?
      const Mi = invertir(M);
      if ([[0, 0], [W, 0], [W, H], [0, H]].some(([x, y]) => { const [u, v] = aplicar(Mi, x, y); return u < caja.l - 1 || u > caja.l + caja.w + 1 || v < caja.t - 1 || v > caja.t + caja.h + 1; })) sinVideo++;
    }
    const T = verdad(sincronizado ? tCuadro : t, salto), cr = centro(T.map(([x, y]) => aplicar(M, x, y))), cc = centro(R.map(([x, y]) => aplicar(M, x, y)));
    if (t > 1 && t < 3) { roca.push(cr); capa.push(cc); desfase.push(Math.hypot(cc[0] - cr[0], cc[1] - cr[1])); }
    if (t > 3) llegada.push([t - 3, cr]);
  }
  const res = { roca_px: Math.hypot(sd(roca.map(p => p[0])), sd(roca.map(p => p[1]))), capa_px: Math.hypot(sd(capa.map(p => p[0])), sd(capa.map(p => p[1]))),
    desfase_px: desfase.reduce((s, x) => s + x, 0) / desfase.length, cuadros_con_borde: sinVideo };
  if (salto) {   // tiempo hasta que la imagen llega a su nuevo lugar (±20 px, el pulso sigue presente) tras girar el teléfono de golpe
    const fin = centro(llegada.slice(-60).map(r => r[1]));
    const k = llegada.findIndex((r, j) => llegada.slice(j, j + 30).every(q => Math.hypot(q[1][0] - fin[0], q[1][1] - fin[1]) < 20));
    res.sigue_en_ms = k < 0 ? Infinity : Math.round(llegada[k][0] * 1000);
  }
  return res;
}
function invertir(m) {
  const [a, b, c, d, e, f, g, h, i] = m, A = e * i - f * h, B = f * g - d * i, C = d * h - e * g, det = a * A + b * B + c * C;
  return [A, c * h - b * i, b * f - c * e, B, a * i - c * g, c * d - a * f, C, b * g - a * h, a * e - b * d].map(v => v / det);
}
const f = o => Object.fromEntries(Object.entries(o).map(([k, v]) => [k, Math.round(v * 10) / 10]));
const casos = { 'antes (video en vivo, sin gimbal)': [false, false], 'video sincronizado, sin gimbal': [false, true], 'video sincronizado + gimbal': [true, true] };
const r = {};
for (const [nombre, [gb, sc]] of Object.entries(casos)) { r[nombre] = correr(gb, sc); r[nombre].sigue_en_ms = correr(gb, sc, 120).sigue_en_ms; console.log(nombre.padEnd(36), f(r[nombre])); }
const a = r['antes (video en vivo, sin gimbal)'], c = r['video sincronizado + gimbal'];
// criterios: la roca y la capa se mueven 3 veces menos que antes, la capa queda calzada (desfase ≈ ruido del tracker),
// nunca se ve borde sin video y tras un giro brusco la imagen llega en menos de 0,4 s
const ok = c.roca_px * 3 <= a.roca_px && c.capa_px * 3 <= a.capa_px && c.desfase_px < 3 && c.cuadros_con_borde === 0 && c.sigue_en_ms <= 400;
console.log(ok ? 'OK' : 'FALLA');
process.exit(ok ? 0 : 1);
