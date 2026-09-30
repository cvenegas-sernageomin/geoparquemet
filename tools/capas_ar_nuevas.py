"""Objetivos RA del Geositio 1 con las fotos de terreno de 2026-09-30 (el entorno cambió: pasto, arbusto, talud).

Las fotos se ubican en el modelo 3D de 2019 con tools/ubicar_fotos_nuevas.py (→ tools/_ra3d/nuevas.json) y la interpretación de
Leapfrog se proyecta con esa cámara, con oclusión por la malla, igual que en capas_ar_3d.py.
Uso: python tools/capas_ar_nuevas.py [--prueba]   (--prueba escribe en tools/_ra3d/prueba_nuevas y no toca docs/)
"""
import json, sys
import cv2
import numpy as np
from PIL import Image
import ra3d
import capas_ar_3d as C
import carteles_ar
from capas_ar import LADO_OBJ, LADO_CAPA, SALIDA

NUEVAS = json.loads((ra3d.CACHE / 'nuevas.json').read_text())


def camara(d):
    return dict(w=d['w'], h=d['h'], K=np.array([[d['f'], 0, d['w'] / 2], [0, d['f'], d['h'] / 2], [0, 0, 1]]),
                rad=np.zeros(3), tan=np.zeros(2), t=np.array(d['t']), R=np.array(d['R']))


def main(prueba=False):
    V, F, *_ = ra3d.malla()
    p3d, *_ = carteles_ar.puntos3d()
    trazas, sup = ra3d.interpretacion()
    destino = ra3d.CACHE / 'prueba_nuevas' if prueba else SALIDA
    destino.mkdir(exist_ok=True)
    C.SALIDA = destino
    pares = []
    for k, (nombre, d) in enumerate(sorted(NUEVAS.items()), 1):
        foto = Image.open(ra3d.RAIZ / 'Fotos y modelos' / 'Fotos Terreno 30-09-26' / nombre)
        from PIL import ImageOps
        foto = ImageOps.exif_transpose(foto).convert('RGB')
        assert foto.size == (d['w'], d['h']), (foto.size, d)
        cp = C.capa(camara(d), V, F, trazas, sup, LADO_CAPA)
        C.guardar(k, foto, cp, pares, nombre)
        pos = {}
        for n3, X in p3d.items():
            u, v, z = ra3d.proyectar(camara(d), X[None])
            if z[0] > 0 and 0 <= u[0] < d['w'] and 0 <= v[0] < d['h']: pos[n3] = (u[0] / d['w'], v[0] / d['h'])
        c8 = np.asarray(Image.open(C.SALIDA / f'g1_{k}_capa.webp').convert('RGBA'))
        pares[-1]['carteles'] = {a: [round(float(x), 4), round(float(y), 4)] for a, (x, y) in carteles_ar.por_capa(c8, pos).items()}
        print('   carteles', pares[-1]['carteles'])
    if not prueba:
        idx = SALIDA / 'objetivos.json'
        todo = json.loads(idx.read_text(encoding='utf-8'))
        todo['1'] = {'mind': 'ar/g1.mind', 'pares': pares}
        idx.write_text(json.dumps(todo, ensure_ascii=False, indent=1), encoding='utf-8')


if __name__ == '__main__':
    main('--prueba' in sys.argv)
