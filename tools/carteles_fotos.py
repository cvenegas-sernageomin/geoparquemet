"""Ubica los carteles de divulgación en geositios sin modelo 3D (G2, G3, G6) → objetivos.json pares[].carteles.

Cada punto se marca a mano en la foto interpretada publicada (x, y de 0 a 1 sobre su color en la capa) y se
traspasa a las fotos hermanas (pares con 'origen', tools/capas_ar_fotos.py) con una homografía SIFT.
Uso: python tools/carteles_fotos.py   (después de capas_ar.py / capas_ar_fotos.py, que reescriben objetivos.json)
"""
import json, re
import numpy as np
import cv2
from capas_ar import SALIDA

# geositio → foto publicada k → cartel → (x, y)
PUNTOS = {
    2: {1: {'dique': (0.45, 0.42), 'volcanica': (0.2, 0.14), 'contacto': (0.28, 0.36)},
        2: {'dique': (0.78, 0.5), 'volcanica': (0.3, 0.28)}},
    3: {1: {'suelo': (0.4, 0.15), 'roca': (0.3, 0.72), 'fracturas': (0.18, 0.55), 'raices': (0.55, 0.55), 'relleno': (0.33, 0.455)},
        2: {'roca': (0.2, 0.62), 'fracturas': (0.2, 0.19), 'raices': (0.63, 0.85), 'relleno': (0.46, 0.45)}},
    6: {1: {'volcanica': (0.3, 0.25), 'intrusiva': (0.55, 0.72), 'contacto': (0.5, 0.54)},
        2: {'volcanica': (0.35, 0.3), 'intrusiva': (0.62, 0.7), 'contacto': (0.55, 0.52)},
        3: {'volcanica': (0.3, 0.25), 'intrusiva': (0.6, 0.62), 'contacto': (0.4, 0.43)}},
}


def main():
    todo = json.loads((SALIDA / 'objetivos.json').read_text(encoding='utf-8'))
    sift = cv2.SIFT_create(6000); bf = cv2.BFMatcher()
    for n, fotos in PUNTOS.items():
        pares = todo[str(n)]['pares']
        for p in pares:
            if p['k'] in fotos and 'origen' not in p:
                p['carteles'] = {i: list(xy) for i, xy in fotos[p['k']].items()}
        for p in pares:
            m = re.search(r'desde foto (\d+)', p.get('origen', ''))
            if not m: continue
            k = int(m.group(1))
            a = cv2.imread(str(SALIDA / f'g{n}_{k}_obj.jpg'), 0); b = cv2.imread(str(SALIDA / f"g{n}_{p['k']}_obj.jpg"), 0)
            ka, da = sift.detectAndCompute(a, None); kb, db = sift.detectAndCompute(b, None)
            mm = [x for x, y in bf.knnMatch(da, db, k=2) if x.distance < .75 * y.distance]
            H, _ = cv2.findHomography(np.float32([ka[x.queryIdx].pt for x in mm]), np.float32([kb[x.trainIdx].pt for x in mm]), cv2.RANSAC, 4)
            pos = {}
            for i, (x, y) in fotos.get(k, {}).items():
                q = H @ [x * a.shape[1], y * a.shape[0], 1]
                pos[i] = [round(float(q[0] / q[2] / b.shape[1]), 4), round(float(q[1] / q[2] / b.shape[0]), 4)]
            p['carteles'] = pos
        for p in pares: print(f"g{n}_{p['k']}", p.get('carteles'))
    (SALIDA / 'objetivos.json').write_text(json.dumps(todo, ensure_ascii=False, indent=1), encoding='utf-8')


if __name__ == '__main__':
    main()
