"""Ubica las fotos nuevas del Geositio 1 (Fotos Terreno 30-09-26) dentro del modelo 3D de 2019 (Pix4D + Leapfrog).

Para cada foto nueva:
  1. SIFT contra las 22 fotos de Fotos_modelo (marco de Pix4D); cada punto antiguo recibe su 3D con la profundidad de la malla.
  2. PnP con RANSAC + foco estimado (EXIF: 26 mm equivalentes) → cámara en el marco del modelo.
  3. Guarda tools/_ra3d/nuevas.json (cámara + inliers + error) para que capas_ar_nuevas.py proyecte las trazas de Leapfrog.
Uso: python tools/ubicar_fotos_nuevas.py
"""
import json, sys
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
import ra3d

NUEVAS = ra3d.RAIZ / 'Fotos y modelos' / 'Fotos Terreno 30-09-26'
SALIDA = ra3d.CACHE / 'nuevas.json'
L = 1800                      # lado largo para SIFT
ESC_Z = 0.25                  # resolución del z-buffer de las fotos antiguas (respecto a la foto completa)


def sift_foto(gris):
    cl = cv2.createCLAHE(3, (8, 8))
    return cv2.SIFT_create(12000, contrastThreshold=0.01).detectAndCompute(cl.apply(gris), None)


def reducir(arr):
    s = L / max(arr.shape[:2])
    return cv2.resize(arr, None, fx=s, fy=s, interpolation=cv2.INTER_AREA), s


def punto3d(c, u, v, z):
    """Pixel (marco de Pix4D, sin distorsión: la distorsión es pequeña) + profundidad → punto del modelo."""
    K = c['K']
    x, y = (u - K[0, 2]) / K[0, 0], (v - K[1, 2]) / K[1, 1]
    return c['t'] + (np.c_[x * z, y * z, z]) @ c['R']


def main():
    V, F, UV, UVF, tex = ra3d.malla()
    cams = ra3d.camaras()
    viejas = []
    for n, c in cams.items():
        if not (ra3d.FOTOS / n).exists(): continue
        foto, _ = ra3d.foto_derecha(n, c, V, F, UV, UVF, tex)   # solo para tener el marco de Pix4D
        g, s = reducir(cv2.cvtColor(np.asarray(foto), cv2.COLOR_RGB2GRAY))
        k, d = sift_foto(g)
        w4, h4 = round(c['w'] * ESC_Z), round(c['h'] * ESC_Z)
        zb = ra3d.zbuffer(c, V, F, w4, h4, ESC_Z)
        P = np.float32([kp.pt for kp in k]) / s                  # a píxeles de la cámara
        zi = zb[(P[:, 1] * ESC_Z).astype(int).clip(0, h4 - 1), (P[:, 0] * ESC_Z).astype(int).clip(0, w4 - 1)]
        ok = np.isfinite(zi) & (zi > 0)
        X = np.full((len(k), 3), np.nan)
        X[ok] = punto3d(c, P[ok, 0], P[ok, 1], zi[ok])
        viejas.append((n, d, X))
        print('antigua', n, ok.sum(), 'puntos con 3D', flush=True)

    bf = cv2.BFMatcher()
    res, guardados = {}, {}
    for f in sorted(NUEVAS.glob('*.jpg')):
        im = cv2.imread(str(f))               # cv2 aplica la orientación EXIF
        H0, W0 = im.shape[:2]
        g, s = reducir(cv2.cvtColor(im, cv2.COLOR_BGR2GRAY))
        k, d = sift_foto(g)
        Pn = np.float32([kp.pt for kp in k]) / s
        pts2, pts3 = [], []
        for n, dv, X in viejas:
            m = [a for a, b in bf.knnMatch(d, dv, k=2) if a.distance < .8 * b.distance]
            for a in m:
                if np.isfinite(X[a.trainIdx, 0]): pts2.append(Pn[a.queryIdx]); pts3.append(X[a.trainIdx])
        pts2, pts3 = np.float64(pts2), np.float64(pts3)
        if len(pts2) < 12:
            print(f.name, 'pocos puntos', len(pts2)); continue
        f0 = max(W0, H0) * 26 / 36            # 26 mm equivalentes
        mejor = None
        for fac in (0.8, 0.9, 1.0, 1.1, 1.25):
            K = np.array([[f0 * fac, 0, W0 / 2], [0, f0 * fac, H0 / 2], [0, 0, 1]])
            ok, rv, tv, inl = cv2.solvePnPRansac(pts3, pts2, K, None, iterationsCount=5000, reprojectionError=12, confidence=.999, flags=cv2.SOLVEPNP_EPNP)
            if ok and inl is not None and (mejor is None or len(inl) > len(mejor[3])): mejor = (fac, rv, tv, inl)
        if mejor is None:
            print(f.name, 'sin solucion'); continue
        fac, rv, tv, inl = mejor
        inl = inl[:, 0]
        a, b = pts3[inl], pts2[inl]

        def ajuste(ff, rv0, tv0):
            K = np.array([[ff, 0, W0 / 2], [0, ff, H0 / 2], [0, 0, 1]])
            rv1, tv1 = cv2.solvePnPRefineLM(a, b, K, None, rv0.copy(), tv0.copy())
            pr, _ = cv2.projectPoints(a, rv1, tv1, K, None)
            e = np.hypot(*(pr[:, 0] - b).T)
            return float(np.median(np.minimum(e, 12))), rv1, tv1, e
        ff0 = f0 * fac; rv1, tv1 = rv, tv
        best = None
        for fx in np.linspace(0.75, 1.3, 23):
            sc, rvx, tvx, e = ajuste(ff0 * fx, rv, tv)
            if best is None or sc < best[0]: best = (sc, ff0 * fx, rvx, tvx, e)
        sc, ff, rv1, tv1, e = best
        n_ok = int((e < 8).sum())
        r = type('R', (), {'x': np.r_[rv1.ravel(), tv1.ravel(), ff]})
        R, _ = cv2.Rodrigues(r.x[:3]); t = -R.T @ r.x[3:6]
        guardados[f.name] = (a, b, r.x[:3].copy(), r.x[3:6].copy())
        res[f.name] = dict(w=W0, h=H0, f=float(r.x[6]), R=R.tolist(), t=t.tolist(), inliers=n_ok, total=len(pts2), err_med=float(np.median(e[e < 8])) if n_ok else 99)
        print(f.name, f'f={r.x[6]:.0f} ({r.x[6]/f0:.2f}x) inliers {n_ok}/{len(pts2)} err_med {res[f.name]["err_med"]:.1f}px', flush=True)
    # foco común (mediana de las fotos bien ubicadas) y reajuste de las poses con él
    buenas = [n for n, r in res.items() if r['inliers'] >= 50]
    fc = float(np.median([res[n]['f'] for n in buenas]))
    print('foco común', round(fc), 'de', len(buenas), 'fotos')
    for n in buenas:
        a, b, rv, tv = guardados[n]; W0, H0 = res[n]['w'], res[n]['h']
        K = np.array([[fc, 0, W0 / 2], [0, fc, H0 / 2], [0, 0, 1]])
        rv, tv = cv2.solvePnPRefineLM(a, b, K, None, rv.reshape(3, 1), tv.reshape(3, 1))
        pr, _ = cv2.projectPoints(a, rv, tv, K, None); e = np.hypot(*(pr[:, 0] - b).T)
        R, _ = cv2.Rodrigues(rv)
        res[n].update(f=fc, R=R.tolist(), t=(-R.T @ tv).ravel().tolist(), inliers=int((e < 8).sum()), err_med=float(np.median(e[e < 8])))
        print(n, res[n]['inliers'], round(res[n]['err_med'], 1))
    SALIDA.write_text(json.dumps({n: res[n] for n in buenas}, indent=1))


if __name__ == '__main__':
    main()
