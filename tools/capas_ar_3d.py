"""Objetivos de realidad aumentada del Geositio 1 a partir del modelo 3D (Pix4D + Leapfrog), ver tools/ra3d.py.

Por cada foto real del afloramiento genera
  docs/ar/g1_<k>_obj.jpg    la foto (lo que MindAR debe reconocer)
  docs/ar/g1_<k>_capa.webp  la interpretación de Leapfrog proyectada con la cámara calibrada de esa foto:
                            trazas de fractura (líneas) + la parte de cada plano que aflora en la roca (relleno)
Lo que queda detrás de la roca se oculta con la profundidad de la malla.
k=1 es la foto publicada (docs/img/g1_1a.webp); su capa se traspasa desde la foto original más parecida
con una homografía (misma posición de cámara), el resto son las fotos de Fotos_modelo.
Colores: los mismos de la RA actual (líneas azules de la foto interpretada, tintes de tools/capas_ar.py).

Uso: python tools/capas_ar_3d.py   → después compilar g1.mind (tools/servidor_ar.py) y subir la versión del SW.
"""
import json
import numpy as np
from scipy import ndimage as ndi
from PIL import Image, ImageDraw, ImageFilter
import ra3d
from capas_ar import TINTES, LADO_OBJ, LADO_CAPA, SALIDA, DOCS

LINEA = (20, 12, 167)                  # azul de las líneas en docs/img/g1_1b.webp
RELLENO = {'Frac1': TINTES['rojo'], 'Frac4': TINTES['azul'], 'Frac5': TINTES['amarillo']}   # mismo orden que la foto interpretada
SS = 2                                 # sobremuestreo para bordes suaves
ANCHO_LINEA = 5                        # px en la capa final (lado largo 1400)
BANDA = 1.2                            # unidades del modelo: el plano "aflora" si está a menos de esto de la roca
# fotos elegidas por la posición de su cámara: cubren la vereda de izquierda a derecha, con la cámara
# inclinada hacia arriba, recta y hacia abajo, y con luz de mañana (0030, 0031, 0036) y de tarde (el resto)
FOTOS = ['DSC_0029.JPG', 'DSC_0030.JPG', 'DSC_0036.JPG', 'DSC_0031.JPG', 'DSC_0040.JPG', 'DSC_0035.JPG', 'DSC_0034.JPG', 'DSC_0037.JPG']
PUBLICADA, SU_ORIGINAL = DOCS / 'img' / 'g1_1a.webp', 'DSC_0030.JPG'


def familia(nombre):
    n = nombre.replace(' ', '')
    return 'Frac5' if n.startswith('Frac5') else 'Frac4' if n.startswith('Frac4') else n


def limpiar(m, r, area_min):
    """Zona continua: cierra huecos y grietas del relleno, quita manchas sueltas."""
    disco = np.hypot(*np.mgrid[-r:r + 1, -r:r + 1]) <= r
    m = ndi.binary_opening(ndi.binary_fill_holes(ndi.binary_closing(m, disco, border_value=0)), disco[::2, ::2])
    et, n = ndi.label(m)
    if n:
        tam = ndi.sum(m, et, range(1, n + 1))
        m = np.isin(et, 1 + np.flatnonzero(tam >= area_min))
    return m


def capa(c, V, F, trazas, sup, lado):
    """Capa RGBA en el marco de Pix4D, con el lado largo = lado*SS."""
    esc = lado * SS / max(c['w'], c['h'])
    w, h = round(c['w'] * esc), round(c['h'] * esc)
    # profundidad de la roca a 1/4 de resolución (más densa, sin huecos) y ampliada
    e4 = esc / 4; w4, h4 = round(c['w'] * e4), round(c['h'] * e4)
    zb = np.asarray(Image.fromarray(ra3d.zbuffer(c, V, F, w4, h4, e4)).resize((w, h), Image.NEAREST))
    rgba = np.zeros((h, w, 4), np.uint8)
    for nombre, (Vs, Fs) in sup.items():
        col = RELLENO.get(familia(nombre))
        if not col: continue
        zs = ra3d.raster_superficie(c, Vs, Fs, w, h, esc)
        with np.errstate(invalid='ignore'):
            z = np.isfinite(zb) & np.isfinite(zs) & (np.abs(zs - zb) < BANDA)
        z = limpiar(z, 7 * SS, (60 * SS) ** 2)
        borde = z & ~(np.asarray(Image.fromarray((z * 255).astype(np.uint8)).filter(ImageFilter.MinFilter(2 * SS + 1))) > 127)
        rgba[z, :3] = col; rgba[z, 3] = np.maximum(rgba[z, 3], 105)
        rgba[borde, :3] = col; rgba[borde, 3] = 235
    im = Image.fromarray(rgba, 'RGBA')
    dr = ImageDraw.Draw(im)
    for nombre, tramos in trazas.items():
        for t in tramos:
            P = ra3d.densificar(t, 0.25)
            u, v, z = ra3d.proyectar(c, P, esc)
            ui, vi = u.astype(int).clip(0, w - 1), v.astype(int).clip(0, h - 1)
            vis = (z > 0) & (z <= zb[vi, ui] + 2 * BANDA)
            vis = ndi.binary_closing(np.r_[False, vis, False], np.ones(9))[1:-1] | vis   # sin cortes por ruido de la malla
            for k in range(len(P) - 1):
                if vis[k] and vis[k + 1]:
                    dr.line([(u[k], v[k]), (u[k + 1], v[k + 1])], fill=(*LINEA, 255), width=ANCHO_LINEA * SS, joint='curve')
    return im


def main():
    V, F, UV, UVF, tex = ra3d.malla()
    cams = ra3d.camaras()
    trazas, sup = ra3d.interpretacion()
    print(len(trazas), 'trazas,', len(sup), 'superficies')
    pares, capas_orig = [], {}
    for k, n in enumerate(FOTOS, 2):
        c = cams[n]
        foto, giro = ra3d.foto_derecha(n, c, V, F, UV, UVF, tex)
        cp = capa(c, V, F, trazas, sup, LADO_CAPA).rotate(giro, expand=True)
        foto = foto.rotate(giro, expand=True)
        capas_orig[n] = (foto, cp)
        guardar(k, foto, cp, pares, n)
    # foto publicada: homografía desde su original
    import cv2
    pub = Image.open(PUBLICADA).convert('RGB')
    orig, cp = capas_orig[SU_ORIGINAL]
    a = np.asarray(pub.convert('L'))
    b = np.asarray(orig.convert('L').resize((cp.width // SS, cp.height // SS)))
    sift = cv2.SIFT_create(5000)
    ka, da = sift.detectAndCompute(a, None); kb, db = sift.detectAndCompute(b, None)
    m = [x for x, y in cv2.BFMatcher().knnMatch(db, da, k=2) if x.distance < .7 * y.distance]
    H, inl = cv2.findHomography(np.float32([kb[x.queryIdx].pt for x in m]), np.float32([ka[x.trainIdx].pt for x in m]), cv2.RANSAC, 3)
    print('homografía publicada:', int(inl.sum()), 'puntos de', len(m))
    esc = cp.width / b.shape[1]            # la capa está a SS veces la foto reducida
    S = np.diag([1 / esc, 1 / esc, 1])
    out_w, out_h = pub.width * SS * 2, pub.height * SS * 2      # 600x896 → capa de 2400 px antes de reducir
    U = np.diag([out_w / pub.width, out_h / pub.height, 1])
    cpw = cv2.warpPerspective(np.asarray(cp), U @ H @ S, (out_w, out_h), flags=cv2.INTER_LINEAR)
    guardar(1, pub, Image.fromarray(cpw, 'RGBA'), pares, 'publicada (desde ' + SU_ORIGINAL + ')')
    pares.sort(key=lambda p: p['k'])
    idx = SALIDA / 'objetivos.json'
    todo = json.loads(idx.read_text(encoding='utf-8'))
    todo['1'] = {'mind': 'ar/g1.mind', 'pares': pares}
    idx.write_text(json.dumps(todo, ensure_ascii=False, indent=1), encoding='utf-8')


def guardar(k, foto, cp, pares, origen):
    obj = foto.copy(); obj.thumbnail((LADO_OBJ, LADO_OBJ), Image.LANCZOS)
    cp = cp.resize((round(LADO_CAPA * obj.width / max(obj.size)), round(LADO_CAPA * obj.height / max(obj.size))), Image.LANCZOS)
    obj.save(SALIDA / f'g1_{k}_obj.jpg', quality=88)
    cp.save(SALIDA / f'g1_{k}_capa.webp', 'WEBP', quality=85, method=6)
    cob = float((np.asarray(cp)[..., 3] > 40).mean())
    pares.append({'k': k, 'obj': f'ar/g1_{k}_obj.jpg', 'capa': f'ar/g1_{k}_capa.webp', 'w': obj.width, 'h': obj.height, 'cobertura': round(cob, 3)})
    print(f'g1_{k}: {origen} {obj.size}, dibujo en {cob:.0%}')


if __name__ == '__main__':
    main()
