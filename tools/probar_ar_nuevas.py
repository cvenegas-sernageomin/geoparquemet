"""Prueba de reconocimiento de la RA del G1 con fotos de terreno 2026-09-30 que NO son objetivos (ver probar_ar.py).
Uso: python tools/probar_ar_nuevas.py [g1.mind anterior para comparar]   → abrir /_probar.html en servidor_ar."""
import json, shutil, sys
from PIL import Image, ImageOps
import ra3d
import probar_ar as P
from capas_ar_nuevas import NUEVAS

def main():
    if P.SAL.exists(): shutil.rmtree(P.SAL)
    P.SAL.mkdir(parents=True)
    casos = []
    libres = [f for f in sorted((ra3d.RAIZ / 'Fotos y modelos' / 'Fotos Terreno 30-09-26').glob('*.jpg')) if f.name not in NUEVAS]
    for f in libres:
        foto = ImageOps.exif_transpose(Image.open(f)).convert('RGB'); foto.thumbnail((1500, 1500))
        for nombre, im in P.variantes(foto):
            n = f'{f.stem}_{nombre}.jpg'; im.save(P.SAL / n, quality=85)
            casos.append({'img': n, 'debe': True, 'grupo': f.stem})
    for p in ['ar/g6_1_obj.jpg', 'ar/g6_2_obj.jpg', 'img/g2_1a.webp', 'img/g3_1a.webp', 'img/g4_1a.webp', 'img/g5_1a.webp', 'img/portada.webp']:
        src = ra3d.RAIZ / 'docs' / p
        if src.exists():
            n = 'neg_' + src.stem + '.jpg'; P.cuadro(Image.open(src).convert('RGB')).save(P.SAL / n, quality=85)
            casos.append({'img': n, 'debe': False, 'grupo': 'otros'})
    minds = {'nuevo': '/ar/g1.mind'}
    if len(sys.argv) > 1:
        shutil.copy(sys.argv[1], P.SAL / 'g1_antes.mind'); minds = {'antes': '/_prueba/g1_antes.mind', **minds}
    (P.SAL / 'casos.json').write_text(json.dumps({'minds': minds, 'casos': casos}, indent=1), encoding='utf-8')
    print(len(casos), 'casos; fotos libres:', [f.name for f in libres])

if __name__ == '__main__': main()
