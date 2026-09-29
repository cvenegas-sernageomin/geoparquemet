"""Más objetivos de RA para geositios sin modelo 3D, con fotos hermanas de la salida a terreno del 28-08-2019.

Algunas fotos interpretadas publicadas salen de esa salida; las fotos tomadas segundos antes o después, desde
otro punto, muestran el mismo afloramiento. La capa de la foto publicada (tools/capas_ar.py) se traspasa a cada
hermana con una homografía (SIFT + RANSAC) y la hermana se recorta alrededor de la zona interpretada.
Solo se usan hermanas con calce seguro (medido: ≥ 40 puntos en común y homografía coherente).

Uso: python tools/capas_ar_fotos.py   → después compilar g2.mind y g3.mind (tools/servidor_ar.py) y subir RA en sw.js
"""
import json
import numpy as np
import cv2
from PIL import Image, ImageOps
from capas_ar import DOCS, SALIDA, LADO_OBJ, LADO_CAPA, main as capas_publicadas

TERRENO = DOCS.parent / 'Fotos y modelos' / 'Fotos_Terreno-20260929T191513Z-1-004' / 'Fotos_Terreno' / 'Terreno_28082019'
# (geositio, nº de foto publicada) → fotos de terreno que la contienen
HERMANAS = {(2, 1): ['DSC_0080.JPG', 'DSC_0079.JPG'],
            (3, 2): ['DSC_0114.JPG', 'DSC_0110.JPG', 'DSC_0115.JPG', 'DSC_0112.JPG']}
MIN_PUNTOS = 40
MARGEN = 1.7       # la hermana se recorta a 1,7 veces la zona de la foto publicada (deja ver entorno para reconocer)


def main():
    capas_publicadas(sorted({n for n, _ in HERMANAS}))
    todo = json.loads((SALIDA / 'objetivos.json').read_text(encoding='utf-8'))
    tour = json.loads((DOCS / 'data' / 'tour.json').read_text(encoding='utf-8'))
    sift = cv2.SIFT_create(8000); bf = cv2.BFMatcher()
    for (n, k), lista in HERMANAS.items():
        pares = todo[str(n)]['pares']
        f = tour['sitios'][n - 1]['fotos'][k - 1]
        pub = Image.open(DOCS / f['a']).convert('RGB')
        capa = Image.open(SALIDA / f'g{n}_{k}_capa.webp').convert('RGBA').resize(pub.size, Image.LANCZOS)
        ka, da = sift.detectAndCompute(np.asarray(pub.convert('L')), None)
        for nombre in lista:
            im = Image.open(TERRENO / nombre); im.draft('RGB', (3200, 3200))
            im = ImageOps.exif_transpose(im).convert('RGB'); im.thumbnail((1600, 1600), Image.LANCZOS)
            kb, db = sift.detectAndCompute(np.asarray(im.convert('L')), None)
            m = [x for x, y in bf.knnMatch(da, db, k=2) if x.distance < .75 * y.distance]
            H, msk = cv2.findHomography(np.float32([ka[x.queryIdx].pt for x in m]), np.float32([kb[x.trainIdx].pt for x in m]), cv2.RANSAC, 5)
            puntos = int(msk.sum()) if msk is not None else 0
            if puntos < MIN_PUNTOS:
                print(f'  {nombre}: {puntos} puntos, se descarta'); continue
            esq = cv2.perspectiveTransform(np.float32([[0, 0], [pub.width, 0], [pub.width, pub.height], [0, pub.height]])[None], H)[0]
            (x0, y0), (x1, y1) = esq.min(0), esq.max(0)
            cx, cy, w, h = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) * MARGEN, (y1 - y0) * MARGEN
            caja = [int(max(cx - w / 2, 0)), int(max(cy - h / 2, 0)), int(min(cx + w / 2, im.width)), int(min(cy + h / 2, im.height))]
            obj = im.crop(caja); obj.thumbnail((LADO_OBJ, LADO_OBJ), Image.LANCZOS)
            # capa publicada → marco del recorte, a la resolución de capa
            esc = LADO_CAPA / max(obj.size); cw, ch = round(obj.width * esc), round(obj.height * esc)
            s = cw / (caja[2] - caja[0])
            A = np.array([[s, 0, -caja[0] * s], [0, s, -caja[1] * s], [0, 0, 1]]) @ H
            cp = cv2.warpPerspective(np.asarray(capa), A, (cw, ch), flags=cv2.INTER_LINEAR)
            # fuera de la foto publicada no hay interpretación: el borde se difumina para que no parezca un recorte
            zona = cv2.warpPerspective(np.full((pub.height, pub.width), 255, np.uint8), A, (cw, ch), flags=cv2.INTER_NEAREST)
            rampa = np.clip(cv2.distanceTransform((zona > 0).astype(np.uint8), cv2.DIST_L2, 5) / (0.06 * max(cw, ch)), 0, 1)
            cp[..., 3] = (cp[..., 3] * rampa).astype(np.uint8)
            kk = max(p['k'] for p in pares) + 1
            obj.save(SALIDA / f'g{n}_{kk}_obj.jpg', quality=88)
            Image.fromarray(cp, 'RGBA').save(SALIDA / f'g{n}_{kk}_capa.webp', 'WEBP', quality=85, method=6)
            cob = float((cp[..., 3] > 40).mean())
            pares.append({'k': kk, 'obj': f'ar/g{n}_{kk}_obj.jpg', 'capa': f'ar/g{n}_{kk}_capa.webp', 'w': obj.width, 'h': obj.height,
                          'cobertura': round(cob, 3), 'origen': f'{nombre} (desde foto {k})'})
            print(f'g{n}_{kk}: {nombre} {puntos} puntos, {obj.size}, dibujo en {cob:.0%}')
    (SALIDA / 'objetivos.json').write_text(json.dumps(todo, ensure_ascii=False, indent=1), encoding='utf-8')


if __name__ == '__main__':
    main()
