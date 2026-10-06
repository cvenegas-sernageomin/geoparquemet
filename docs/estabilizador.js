/* Estabilizador de la RA (gimbal virtual).
   El objetivo es plano: pasar de la pose cruda del tracker a una pose suavizada equivale a una homografía de pantalla.
   Se suavizan las 4 esquinas del objetivo en pantalla (temblor chico → se amortigua fuerte; movimiento grande → se sigue
   de inmediato) y la homografía cruda→suave se aplica con CSS al contenedor del video y del canvas 3D: la roca y las
   líneas se mueven juntas, así que quedan quietas y calzadas. El zoom deja margen (como el recorte del estabilizador
   de un celular) para que al compensar no aparezcan bordes sin video. Sin DOM: se prueba con tools/probar_estabilizador.mjs. */

export const I3 = [1, 0, 0, 0, 1, 0, 0, 0, 1];
export const mul3 = (a, b) => [0, 1, 2].flatMap(r => [0, 1, 2].map(c => a[r * 3] * b[c] + a[r * 3 + 1] * b[3 + c] + a[r * 3 + 2] * b[6 + c]));
export function inv3(m) {
  const [a, b, c, d, e, f, g, h, i] = m, A = e * i - f * h, B = f * g - d * i, C = d * h - e * g, det = a * A + b * B + c * C;
  return [A, c * h - b * i, b * f - c * e, B, a * i - c * g, c * d - a * f, C, b * g - a * h, a * e - b * d].map(v => v / det);
}
export function aplicar(m, x, y) { const w = m[6] * x + m[7] * y + m[8]; return [(m[0] * x + m[1] * y + m[2]) / w, (m[3] * x + m[4] * y + m[5]) / w]; }
export function homografia(src, dst) {   // 4 pares de puntos → 3×3 (h33 = 1), eliminación de Gauss
  const A = [];
  src.forEach(([x, y], k) => {
    const [u, v] = dst[k];
    A.push([x, y, 1, 0, 0, 0, -u * x, -u * y, u], [0, 0, 0, x, y, 1, -v * x, -v * y, v]);
  });
  for (let c = 0; c < 8; c++) {
    let p = c; for (let r = c + 1; r < 8; r++) if (Math.abs(A[r][c]) > Math.abs(A[p][c])) p = r;
    [A[c], A[p]] = [A[p], A[c]];
    if (Math.abs(A[c][c]) < 1e-12) return null;
    for (let r = 0; r < 8; r++) if (r !== c) { const f = A[r][c] / A[c][c]; for (let k = c; k < 9; k++) A[r][k] -= f * A[c][k]; }
  }
  return [...A.map((r, k) => r[8] / r[k]), 1];
}
// 3×3 → CSS matrix3d (por columnas), con transform-origin 0 0
export const css = M => M === I3 ? '' : `matrix3d(${M[0]},${M[3]},0,${M[6]},${M[1]},${M[4]},0,${M[7]},0,0,1,0,${M[2]},${M[5]},0,${M[8]})`;

export function crearGimbal({ zoom = 1.08, tau = .6, umbral = .05, rapido = .14 } = {}) {
  const g = { S: null, M: I3 };
  const zoomM = (W, H) => [zoom, 0, W / 2 * (1 - zoom), 0, zoom, H / 2 * (1 - zoom), 0, 0, 1];
  // ¿las 4 esquinas de la pantalla siguen mostrando video? v = caja del video {l, t, w, h} en coordenadas del contenedor
  const cubre = (M, W, H, v) => {
    const Mi = inv3(M);
    return [[0, 0], [W, 0], [W, H], [0, H]].every(([x, y]) => {
      const [a, b] = aplicar(Mi, x, y); return a >= v.l - 1 && a <= v.l + v.w + 1 && b >= v.t - 1 && b <= v.t + v.h + 1;
    });
  };
  g.reiniciar = () => { g.S = null; };
  // sin objetivo: solo el zoom, para que la imagen no salte al encontrarlo
  g.libre = (W, H) => (g.S = null, g.M = zoomM(W, H));
  // R = 4 esquinas del objetivo en pantalla con la pose cruda; dt en segundos → matriz 3×3 a aplicar al contenedor
  g.paso = (R, dt, W, H, v) => {
    if (!g.S) g.S = R.map(q => q.slice());
    const S = g.S, dim = Math.min(W, H);
    const d = Math.max(...R.map((q, k) => Math.hypot(q[0] - S[k][0], q[1] - S[k][1])));
    const u = Math.min(1, Math.max(0, (d - umbral * dim) / ((rapido - umbral) * dim))), base = 1 - Math.exp(-dt / tau);
    const a = base + u * u * (3 - 2 * u) * (1 - base);
    S.forEach((q, k) => { q[0] += a * (R[k][0] - q[0]); q[1] += a * (R[k][1] - q[1]); });
    // si la compensación se sale del margen, se acerca lo justo a la pose cruda (búsqueda binaria)
    const Z = zoomM(W, H);
    const con = f => { const Hm = homografia(R, S.map((q, k) => [q[0] + f * (R[k][0] - q[0]), q[1] + f * (R[k][1] - q[1])])); return Hm && mul3(Z, Hm); };
    let M = con(0);
    if (!M || !cubre(M, W, H, v)) {
      let lo = 0, hi = 1; M = Z;
      for (let it = 0; it < 7; it++) { const f = (lo + hi) / 2, m = con(f); if (m && cubre(m, W, H, v)) { hi = f; M = m; } else lo = f; }
      S.forEach((q, k) => { q[0] += hi * (R[k][0] - q[0]); q[1] += hi * (R[k][1] - q[1]); });
    }
    return g.M = M;
  };
  return g;
}
