"""Prepara la realidad aumentada: por cada par foto original / interpretada de un geositio genera
  docs/ar/g<N>_<k>_obj.jpg   foto original = objetivo que la cámara debe reconocer (MindAR)
  docs/ar/g<N>_<k>_capa.webp  solo lo dibujado por el geólogo, con fondo transparente
La capa se obtiene por diferencia entre ambas fotos (están alineadas píxel a píxel): donde la interpretada
cambia respecto de la original está el dibujo. Los tintes suaves quedan semitransparentes y las líneas opacas.
Uso: python tools/capas_ar.py [N ...]   (por defecto los geositios 1 y 6)
"""
import json, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageFilter

RAIZ = Path(__file__).resolve().parent.parent
DOCS = RAIZ / 'docs'
SALIDA = DOCS / 'ar'
LADO_OBJ = 1000     # MindAR no gana precisión con fotos más grandes y el archivo .mind crece mucho
LADO_CAPA = 1400


TINTES = {  # color con que se pinta cada tipo de tinte detectado (rojo = volcánica, verde = intrusiva, etc.)
    'rojo': (225, 60, 45), 'verde': (170, 205, 55), 'amarillo': (245, 205, 40), 'azul': (60, 90, 235),
    'violeta': (160, 70, 220), 'naranjo': (245, 140, 30),
}


def region(mask, radio):
    """Suaviza una máscara booleana ruidosa en una zona continua (cierra huecos, quita puntos sueltos)."""
    im = Image.fromarray((mask * 255).astype(np.uint8))
    im = im.filter(ImageFilter.MedianFilter(7)).filter(ImageFilter.GaussianBlur(radio))
    return np.asarray(im) > 110


def capa(a, b):
    A = np.asarray(a).astype(np.int16)
    B = np.asarray(b).astype(np.int16)
    D = B - A                                   # cambio con signo: qué color agregó el geólogo
    d = np.abs(D).sum(2).astype(np.float32)
    h, w = d.shape
    rgba = np.zeros((h, w, 4), np.uint8)
    # 1) trazos fuertes (líneas y superficies pintadas opacas): se copian tal cual de la interpretada
    fuerte = np.clip((d - 60) * 2.5, 0, 255)
    # 2) tintes suaves (lavados de color): se detecta el tono agregado y se rellena la zona con ese color
    dR, dG, dB = D[..., 0], D[..., 1], D[..., 2]
    r = max(5, w / 110)
    rojo = dR - np.maximum(dG, dB) > 14
    zonas = {
        'rojo': rojo,
        # el verde de los geólogos es verde-oliva/amarillento: se agrupa con el amarillo (sube G, baja B)
        'verde': ~rojo & (dG - dB > 8) & (dG > -3),
        'azul': (dB - np.maximum(dR, dG) > 14),
    }
    for nombre, m in zonas.items():
        z = region(m & (d > 12), r)
        if z.mean() < 0.01:
            continue
        col = TINTES[nombre]
        rgba[z, :3] = col
        rgba[z, 3] = np.maximum(rgba[z, 3], 105)              # relleno semitransparente
        borde = z & ~region(z & True, 1.5) | (z ^ np.roll(z, 3, 0)) | (z ^ np.roll(z, 3, 1))
        rgba[borde, :3] = col
        rgba[borde, 3] = 235                                  # contorno marcado
    opaco = fuerte > rgba[..., 3]
    rgba[opaco, :3] = B[opaco].astype(np.uint8)
    rgba[opaco, 3] = fuerte[opaco].astype(np.uint8)
    out = Image.fromarray(rgba, 'RGBA').filter(ImageFilter.SMOOTH)
    return out, float((rgba[..., 3] > 40).mean())


def main(sitios):
    SALIDA.mkdir(exist_ok=True)
    tour = json.loads((DOCS / 'data' / 'tour.json').read_text(encoding='utf-8'))
    resumen = {}
    for n in sitios:
        s = tour['sitios'][n - 1]
        pares = []
        for k, f in enumerate(s['fotos'], 1):
            a = Image.open(DOCS / f['a']).convert('RGB')
            b = Image.open(DOCS / f['b']).convert('RGB').resize(a.size)
            c, cobertura = capa(a, b)
            obj = a.copy(); obj.thumbnail((LADO_OBJ, LADO_OBJ), Image.LANCZOS)
            c.thumbnail((LADO_CAPA, LADO_CAPA), Image.LANCZOS)
            obj.save(SALIDA / f'g{n}_{k}_obj.jpg', quality=90)
            c.save(SALIDA / f'g{n}_{k}_capa.webp', 'WEBP', quality=82, method=6)
            pares.append({'k': k, 'obj': f'ar/g{n}_{k}_obj.jpg', 'capa': f'ar/g{n}_{k}_capa.webp',
                          'w': obj.width, 'h': obj.height, 'cobertura': round(cobertura, 3)})
            print(f'g{n}_{k}: {obj.size}, dibujo en {cobertura:.0%} de la foto')
        resumen[n] = pares
    idx = SALIDA / 'objetivos.json'
    previo = json.loads(idx.read_text(encoding='utf-8')) if idx.exists() else {}
    previo.update({str(n): {'mind': f'ar/g{n}.mind', 'pares': p} for n, p in resumen.items()})
    idx.write_text(json.dumps(previo, ensure_ascii=False, indent=1), encoding='utf-8')


if __name__ == '__main__':
    main([int(x) for x in sys.argv[1:]] or [1, 6])
