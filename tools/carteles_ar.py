"""Ubica los carteles de divulgación de la RA del Geositio 1 en cada objetivo (docs/ar/objetivos.json → pares[].carteles).

Los textos están en docs/ar/carteles.json. Aquí solo se calcula DÓNDE apunta cada cartel en cada foto objetivo:
  - puntos de la roca (una grieta, la punta de la cuña, roca sin pintar, pie de la pared): se marcan una vez en la
    foto de referencia (DSC_0030), se llevan a 3D con la malla y se proyectan con la cámara de cada foto;
  - superficies pintadas (amarilla): centro de su mancha en la capa de cada objetivo.
La foto publicada (g1_1) es un recorte de DSC_0030: sus puntos se traspasan con una homografía.
Uso: python tools/carteles_ar.py   (después de tools/capas_ar_3d.py)
"""
import json
import numpy as np
from PIL import Image
import cv2
import ra3d
from capas_ar import TINTES, SALIDA
from capas_ar_3d import FOTOS, SU_ORIGINAL, BANDA

REF = 'DSC_0030.JPG'
# (x, y) normalizados en la foto de referencia derecha; 'traza' = se engancha a la grieta dibujada más cercana
PUNTOS = {'grietas': ((0.56, 0.45), 'traza'), 'cuna': ((0.40, 0.60), 'roca'), 'caida': ((0.45, 0.8), 'roca')}
# 'roca' apunta a roca sin pintar: en cada objetivo, el punto de esta franja central más lejos de todo dibujo
FRANJA_ROCA = (0.3, 0.7, 0.58, 0.7)
MANCHAS = {'amarillo': TINTES['amarillo']}


def a_derecha(u, v, w, h, giro):
    """Píxel del marco de Pix4D → coordenadas normalizadas de la foto girada 'giro' grados (antihorario, como PIL)."""
    if giro == 90: x, y, W, H = v, w - u, h, w
    elif giro == 270: x, y, W, H = h - v, u, h, w
    elif giro == 180: x, y, W, H = w - u, h - v, w, h
    else: x, y, W, H = u, v, w, h
    return x / W, y / H


def desde_derecha(x, y, w, h, giro):
    if giro == 90: return w - y * w, x * h
    if giro == 270: return y * w, h - x * h
    if giro == 180: return w - x * w, h - y * h
    return x * w, y * h


def main():
    V, F, UV, UVF, tex = ra3d.malla()
    cams = ra3d.camaras()
    trazas, _ = ra3d.interpretacion()
    giros = {n: ra3d.foto_derecha(n, cams[n], V, F, UV, UVF, tex)[1] for n in set(FOTOS) | {REF}}
    # 1) puntos de referencia → 3D
    c = cams[REF]; esc = 0.25; w, h = round(c['w'] * esc), round(c['h'] * esc)
    uV, vV, zV = ra3d.proyectar(c, V, esc)
    pts = np.vstack([ra3d.densificar(t, 0.25) for tr in trazas.values() for t in tr])
    uT, vT, zT = ra3d.proyectar(c, pts, esc)
    zb = ra3d.zbuffer(c, V, F, w, h, esc)
    visT = (zT > 0) & (uT >= 0) & (uT < w) & (vT >= 0) & (vT < h)
    visT[visT] &= zT[visT] <= zb[vT[visT].astype(int), uT[visT].astype(int)] + 2 * BANDA
    p3d = {}
    for nombre, ((x, y), modo) in PUNTOS.items():
        u, v = desde_derecha(x, y, c['w'] * esc, c['h'] * esc, giros[REF])
        if modo == 'traza':
            d = np.hypot(uT - u, vT - v); d[~visT] = np.inf; p3d[nombre] = pts[np.argmin(d)]
        else:
            cerca = (np.hypot(uV - u, vV - v) < 3) & (zV > 0)
            i = np.flatnonzero(cerca)[np.argmin(zV[cerca])]
            p3d[nombre] = V[i]
    # 2) proyectar en cada objetivo
    todo = json.loads((SALIDA / 'objetivos.json').read_text(encoding='utf-8'))
    pares = todo['1']['pares']
    origen = {p['k']: FOTOS[p['k'] - 2] for p in pares if p['k'] >= 2}
    for p in pares:
        pos = {}
        if p['k'] in origen:
            n = origen[p['k']]; c = cams[n]
            for nombre, X in p3d.items():
                u, v, z = ra3d.proyectar(c, X[None])
                pos[nombre] = a_derecha(u[0], v[0], c['w'], c['h'], giros[n])
        cp = np.asarray(Image.open(SALIDA / f"g1_{p['k']}_capa.webp").convert('RGBA'))
        for nombre, col in MANCHAS.items():
            m = (cp[..., 3] > 60) & (np.abs(cp[..., :3].astype(int) - col).sum(2) < 60)
            if m.sum() > 200:
                ys, xs = np.nonzero(m)
                i = np.argmin(np.hypot(xs - xs.mean(), ys - ys.mean()))       # punto de la mancha más cerca de su centro
                pos[nombre] = (xs[i] / cp.shape[1], ys[i] / cp.shape[0])
        from scipy.ndimage import distance_transform_edt
        libre = distance_transform_edt(cp[..., 3] < 30)
        x0, x1, y0, y1 = FRANJA_ROCA; H_, W_ = libre.shape
        sub = libre[int(y0 * H_):int(y1 * H_), int(x0 * W_):int(x1 * W_)]
        yy, xx = np.unravel_index(np.argmax(sub), sub.shape)
        pos['roca'] = ((xx + x0 * W_) / W_, (yy + y0 * H_) / H_)
        p['carteles'] = {k: [round(float(a), 4), round(float(b), 4)] for k, (a, b) in pos.items()}
    # 3) foto publicada: homografía desde su original
    k_orig = next(k for k, n in origen.items() if n == SU_ORIGINAL)
    po, pp = next(p for p in pares if p['k'] == k_orig), next(p for p in pares if p['k'] == 1)
    a = cv2.imread(str(SALIDA / f'g1_{k_orig}_obj.jpg'), 0); b = cv2.imread(str(SALIDA / 'g1_1_obj.jpg'), 0)
    sift = cv2.SIFT_create(4000); ka, da = sift.detectAndCompute(a, None); kb, db = sift.detectAndCompute(b, None)
    m = [x for x, y in cv2.BFMatcher().knnMatch(da, db, k=2) if x.distance < .7 * y.distance]
    H, _ = cv2.findHomography(np.float32([ka[x.queryIdx].pt for x in m]), np.float32([kb[x.trainIdx].pt for x in m]), cv2.RANSAC, 3)
    for nombre, (x, y) in po['carteles'].items():
        if nombre in pp['carteles'] or nombre == 'roca': continue
        q = H @ [x * a.shape[1], y * a.shape[0], 1]
        pp['carteles'][nombre] = [round(float(q[0] / q[2] / b.shape[1]), 4), round(float(q[1] / q[2] / b.shape[0]), 4)]
    for p in pares: print(f"g1_{p['k']}", p['carteles'])
    (SALIDA / 'objetivos.json').write_text(json.dumps(todo, ensure_ascii=False, indent=1), encoding='utf-8')


if __name__ == '__main__':
    main()
