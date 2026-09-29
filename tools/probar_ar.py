"""Prepara la prueba de reconocimiento de la RA del Geositio 1 (tools/probar_ar.html).

Usa fotos del afloramiento que NO son objetivos (vistas nuevas para MindAR) y las degrada como lo haría un
teléfono: más lejos, más cerca, girado, en perspectiva, con poca luz y desenfocado. Agrega fotos de otros
lugares que no deben reconocerse. Todo queda en tools/_ra3d/prueba/ (ignorado por git) con un índice JSON.
Uso: python tools/probar_ar.py [ruta del .mind anterior para comparar]
"""
import json, shutil, sys
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
import cv2
import ra3d
from capas_ar_3d import FOTOS as OBJETIVOS

SAL = ra3d.CACHE / 'prueba'
W, H = 480, 640                      # cuadro vertical de cámara de teléfono


def cuadro(im, zoom=1.0):
    """Llena un cuadro 3:4 como la cámara; zoom < 1 deja ver el entorno (se simula con bordes reflejados)."""
    a = np.asarray(im)
    if zoom < 1:
        pad = int(max(a.shape[:2]) * (1 / zoom - 1) / 2)
        a = cv2.copyMakeBorder(a, pad, pad, pad, pad, cv2.BORDER_REFLECT)
        a = cv2.GaussianBlur(a, (0, 0), 0.1)
    im = Image.fromarray(a)
    if zoom > 1:
        w, h = im.size; cw, ch = w / zoom, h / zoom
        im = im.crop(((w - cw) / 2, (h - ch) / 2, (w + cw) / 2, (h + ch) / 2))
    return ImageOps.fit(im, (W, H), Image.LANCZOS)


def variantes(im):
    base = cuadro(im)
    a = np.asarray(base)
    src = np.float32([[0, 0], [W, 0], [W, H], [0, H]])
    dst = np.float32([[40, 30], [W - 10, 0], [W, H], [25, H - 40]])
    yield 'normal', base
    yield 'lejos', cuadro(im, 0.7)
    yield 'cerca', cuadro(im, 1.5)
    yield 'girado', base.rotate(12, resample=Image.BICUBIC, fillcolor=(90, 90, 90))
    yield 'perspectiva', Image.fromarray(cv2.warpPerspective(a, cv2.getPerspectiveTransform(src, dst), (W, H), borderMode=cv2.BORDER_REPLICATE))
    yield 'sombra', ImageEnhance.Brightness(ImageEnhance.Color(base).enhance(0.8)).enhance(0.5)
    tarde = np.asarray(base).astype(float) * [1.12, 1.0, 0.78]
    yield 'luz_tarde', Image.fromarray(tarde.clip(0, 255).astype(np.uint8))
    yield 'desenfoque', base.filter(ImageFilter.GaussianBlur(2))


def main():
    if SAL.exists(): shutil.rmtree(SAL)
    SAL.mkdir(parents=True)
    V, F, UV, UVF, tex = ra3d.malla()
    cams = ra3d.camaras()
    casos = []
    nuevas = [n for n in sorted(cams) if n not in OBJETIVOS and (ra3d.FOTOS / n).exists()]
    for n in nuevas:
        foto, giro = ra3d.foto_derecha(n, cams[n], V, F, UV, UVF, tex)
        foto = foto.rotate(giro, expand=True); foto.thumbnail((1500, 1500))
        for nombre, im in variantes(foto):
            f = f'{n[:-4]}_{nombre}.jpg'; im.save(SAL / f, quality=85)
            casos.append({'img': f, 'debe': True, 'grupo': n[:-4]})
    # negativos: otros geositios y otras rocas del recorrido
    for p in ['ar/g6_1_obj.jpg', 'ar/g6_2_obj.jpg', 'img/g2_1a.webp', 'img/g3_1a.webp', 'img/g4_1a.webp', 'img/g5_1a.webp', 'img/portada.webp']:
        src = ra3d.RAIZ / 'docs' / p
        if src.exists():
            f = 'neg_' + src.stem + '.jpg'; cuadro(Image.open(src).convert('RGB')).save(SAL / f, quality=85)
            casos.append({'img': f, 'debe': False, 'grupo': 'otros'})
    minds = {'nuevo': '/ar/g1.mind'}
    if len(sys.argv) > 1:
        shutil.copy(sys.argv[1], SAL / 'g1_antes.mind'); minds = {'antes': '/_prueba/g1_antes.mind', **minds}
    (SAL / 'casos.json').write_text(json.dumps({'minds': minds, 'casos': casos}, indent=1), encoding='utf-8')
    print(len(casos), 'casos;', 'fotos nuevas:', nuevas)


if __name__ == '__main__':
    main()
