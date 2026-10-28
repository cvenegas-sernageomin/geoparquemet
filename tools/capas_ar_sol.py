"""Objetivos RA del Geositio 1 con luz de sol (fotos de terreno de 2026-10-27, RA/GS1/).

Los 11 objetivos de capas_ar_nuevas.py son de un día nublado y MindAR no reconoce la roca con sol directo ni con sombras
de tarde. Aquí no se usa el modelo 3D (está en el otro PC): cada foto nueva se liga con SIFT a la foto objetivo nublada
que más se le parece y la capa de interpretación y los carteles de esa foto se trasladan con la homografía.
La roca no es plana, así que la capa es aproximada; por eso se eligen fotos de encuadre parecido a algún objetivo.

Se agregan al final de los pares del G1 en docs/ar/objetivos.json (marcados con "fuente"), sin tocar los 11 existentes;
volver a correrlo los reemplaza. Correr DESPUÉS de capas_ar_nuevas.py y luego recompilar g1.mind.
Uso: python tools/capas_ar_sol.py [carpeta de fotos]      (por defecto RA/GS1)
"""
import json, sys
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageOps

RAIZ = Path(__file__).resolve().parent.parent
SALIDA = RAIZ / 'docs' / 'ar'
OBJETIVOS = SALIDA / 'objetivos.json'
FUENTE = 'sol 2026-10-27'
LADO_OBJ, LADO_CAPA = 1000, 1400          # igual que capas_ar.py
L = 1000                                  # lado largo para SIFT
# mediodía (13:38) y tarde (18:24); las de 14:02 están a contraluz y no calzan con nada
FOTOS = ['20261027_133843.jpg', '20261027_133849.jpg', '20261027_133855.jpg', '20261027_140219.jpg',
         '20261027_182430.jpg', '20261027_182441.jpg', '20261027_182452.jpg', '20261027_182458.jpg']
MIN_INLIERS = 70

sift = cv2.SIFT_create(6000, contrastThreshold=0.01)
clahe = cv2.createCLAHE(3, (8, 8))


def rasgos(im):
    g = np.asarray(im.convert('L'))
    s = L / max(g.shape)
    g = cv2.resize(g, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    k, d = sift.detectAndCompute(clahe.apply(g), None)
    return np.float32([p.pt for p in k]) / s, d          # en píxeles de la imagen original


def homografia(a, b):
    """H que lleva píxeles de la foto a → foto b, con inliers y error mediano (px de b)."""
    (pa, da), (pb, db) = a, b
    m = [x for x, y in cv2.BFMatcher().knnMatch(da, db, k=2) if x.distance < .75 * y.distance]
    if len(m) < 8:
        return None, 0, None
    A, B = pa[[x.queryIdx for x in m]], pb[[x.trainIdx for x in m]]
    H, msk = cv2.findHomography(A, B, cv2.RANSAC, 6 * max(1, LADO_OBJ / L))
    if H is None:
        return None, 0, None
    ok = msk.ravel() == 1
    err = np.linalg.norm(cv2.perspectiveTransform(A[ok][None], H)[0] - B[ok], axis=1)
    return H, int(ok.sum()), float(np.median(err))


def main(carpeta):
    obj = json.loads(OBJETIVOS.read_text(encoding='utf-8'))
    pares = [p for p in obj['1']['pares'] if p.get('fuente') != FUENTE]
    for p in obj['1']['pares']:
        if p.get('fuente') == FUENTE:
            for c in ('obj', 'capa'):
                (RAIZ / 'docs' / p[c]).unlink(missing_ok=True)
    refs = [(p, rasgos(Image.open(RAIZ / 'docs' / p['obj']))) for p in pares]
    k = max(p['k'] for p in pares)
    for nombre in FOTOS:
        foto = ImageOps.exif_transpose(Image.open(Path(carpeta) / nombre)).convert('RGB')
        foto.thumbnail((LADO_OBJ, LADO_OBJ), Image.LANCZOS)
        r = rasgos(foto)
        mejor = max(((homografia(r, f), p) for p, f in refs), key=lambda x: x[0][1])
        (H, n, err), ref = mejor
        if n < MIN_INLIERS:
            print(f'{nombre}: sin calce suficiente ({n} puntos), se omite'); continue
        k += 1
        # capa de la referencia (LADO_CAPA) → foto nueva (LADO_CAPA): H está en píxeles de obj
        sr, sn = LADO_CAPA / max(ref['w'], ref['h']), LADO_CAPA / max(foto.size)
        Hc = np.diag([sn, sn, 1]) @ np.linalg.inv(H) @ np.diag([1 / sr, 1 / sr, 1])
        capa_ref = np.asarray(Image.open(RAIZ / 'docs' / ref['capa']).convert('RGBA'))
        wc, hc = round(foto.width * sn), round(foto.height * sn)
        capa = cv2.warpPerspective(capa_ref, Hc, (wc, hc), flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0, 0))
        foto.save(SALIDA / f'g1_{k}_obj.jpg', quality=88)
        Image.fromarray(capa, 'RGBA').save(SALIDA / f'g1_{k}_capa.webp', 'WEBP', quality=85, method=6)
        carteles = {}
        for cid, (x, y) in (ref.get('carteles') or {}).items():
            q = cv2.perspectiveTransform(np.float32([[[x * ref['w'], y * ref['h']]]]), np.linalg.inv(H))[0, 0]
            u, v = q[0] / foto.width, q[1] / foto.height
            if .03 < u < .97 and .03 < v < .97:
                carteles[cid] = [round(float(u), 4), round(float(v), 4)]
        cob = float((capa[..., 3] > 40).mean())
        pares.append({'k': k, 'obj': f'ar/g1_{k}_obj.jpg', 'capa': f'ar/g1_{k}_capa.webp', 'w': foto.width, 'h': foto.height,
                      'cobertura': round(cob, 3), 'carteles': carteles, 'fuente': FUENTE, 'foto': nombre, 'ref': ref['k']})
        print(f'g1_{k}: {nombre} desde g1_{ref["k"]} ({n} puntos, error {err:.1f} px), dibujo en {cob:.0%}, {len(carteles)} carteles')
    obj['1']['pares'] = pares
    OBJETIVOS.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding='utf-8')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else RAIZ / 'RA' / 'GS1')
