"""Ícono de GeoParquemet: cerro San Cristóbal con la estatua de la cumbre sobre el verde de Parquemet,
árboles del parque en la base y, dentro del cerro, capas volcánicas cortadas por un dique (Geositio 2).
Genera docs/icons/{icon-192,icon-512,apple-touch-icon,favicon,maskable-512}.png
"""
import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

RAIZ = Path(__file__).resolve().parent.parent
S = 2048                           # lienzo de trabajo (se reduce con antialias)
VERDE = (1, 140, 121)              # verde institucional de Parquemet
CIELO = (40, 172, 148)
ARBOL = [(0, 98, 80), (0, 112, 90), (12, 124, 98)]
CAPAS = [(226, 114, 91), (196, 88, 72), (240, 152, 112), (176, 74, 64), (214, 104, 84)]  # tobas rojizas
DIQUE = (245, 196, 80)
CREMA = (255, 250, 240)


def catmull(pts, n=24):
    out = []
    p = [pts[0]] + pts + [pts[-1]]
    for i in range(1, len(p) - 2):
        p0, p1, p2, p3 = p[i - 1], p[i], p[i + 1], p[i + 2]
        for k in range(n):
            t = k / n
            t2, t3 = t * t, t * t * t
            out.append(tuple(0.5 * ((2 * p1[j]) + (-p0[j] + p2[j]) * t + (2 * p0[j] - 5 * p1[j] + 4 * p2[j] - p3[j]) * t2 + (-p0[j] + 3 * p1[j] - 3 * p2[j] + p3[j]) * t3) for j in (0, 1)))
    out.append(pts[-1])
    return out


def dibujar(tam_final, k=1.0):
    """k < 1 achica el motivo (versión maskable, que el sistema recorta en círculo o gota)."""
    img = Image.new('RGBA', (S, S), VERDE + (255,))
    halo = Image.new('L', (S, S), 0)
    ImageDraw.Draw(halo).ellipse([S * .12, S * .02, S * .88, S * .70], fill=120)
    img.paste(Image.new('RGBA', (S, S), CIELO + (255,)), (0, 0), halo.filter(ImageFilter.GaussianBlur(S * .08)))
    d = ImageDraw.Draw(img)

    c = S / 2
    X = lambda x: c + (x - 0.5) * S * k
    Y = lambda y: c + (y - 0.5) * S * k
    base = Y(0.80)
    # perfil del cerro (hombro a la izquierda, cumbre redondeada levemente a la derecha del centro)
    perfil = [(-0.05, 0.80), (0.08, 0.70), (0.20, 0.58), (0.30, 0.52), (0.38, 0.47), (0.46, 0.39), (0.53, 0.355),
              (0.60, 0.38), (0.70, 0.47), (0.82, 0.60), (0.95, 0.72), (1.05, 0.80)]
    sil = [(X(x), Y(y)) for x, y in catmull(perfil)]
    cima = min(sil, key=lambda p: p[1])
    m = Image.new('L', (S, S), 0)
    ImageDraw.Draw(m).polygon(sil, fill=255)
    capas = Image.new('RGBA', (S, S))
    dc = ImageDraw.Draw(capas)
    paso = S * k * 0.062
    for i in range(-15, 30):
        y0 = Y(0.36) + i * paso
        dc.polygon([(0, y0), (S, y0 - S * 0.13), (S, y0 - S * 0.13 + paso), (0, y0 + paso)], fill=CAPAS[i % len(CAPAS)] + (255,))
    w = S * k * 0.034
    dc.polygon([(X(0.40) - w, base), (X(0.40) + w, base), (X(0.57) + w, Y(0.33)), (X(0.57) - w, Y(0.33))], fill=DIQUE + (255,))
    img.paste(capas, (0, 0), m)
    d.line(sil, fill=CREMA, width=int(S * 0.011 * k), joint='curve')

    # estatua: pedestal de dos cuerpos, túnica esbelta, brazos abiertos hacia abajo, cabeza y aureola
    tx, ty = cima[0], cima[1] + S * k * 0.004
    h = S * k * 0.20
    b = CREMA
    d.rectangle([tx - h * .11, ty - h * .12, tx + h * .11, ty + S * 0.004], fill=b)
    d.rectangle([tx - h * .075, ty - h * .26, tx + h * .075, ty - h * .12], fill=b)
    d.polygon([(tx - h * .085, ty - h * .26), (tx + h * .085, ty - h * .26), (tx + h * .05, ty - h * .74), (tx - h * .05, ty - h * .74)], fill=b)
    for sgn in (-1, 1):
        d.polygon([(tx + sgn * h * .04, ty - h * .70), (tx + sgn * h * .20, ty - h * .55), (tx + sgn * h * .185, ty - h * .51), (tx + sgn * h * .035, ty - h * .62)], fill=b)
    r = h * .065
    hy = ty - h * .74 - r * 1.05
    d.ellipse([tx - r, hy - r, tx + r, hy + r], fill=b)
    for a in range(12):                                  # aureola de estrellas: la distingue de una figura cualquiera
        ang = math.pi * (a / 11)
        rx, ry = tx + math.cos(ang) * r * 2.3, hy - math.sin(ang) * r * 2.3 + r * .4
        rr = r * .28
        d.ellipse([rx - rr, ry - rr, rx + rr, ry + rr], fill=b)

    # árboles del parque sobre la base
    d.rectangle([0, base, S, S], fill=ARBOL[0])
    import random
    rnd = random.Random(7)
    for i in range(26):
        x = rnd.uniform(-0.05, 1.05)
        rr = S * k * rnd.uniform(0.035, 0.06)
        yy = base - rr * rnd.uniform(0.1, 0.55)
        col = ARBOL[rnd.randrange(3)]
        d.ellipse([X(x) - rr, yy - rr, X(x) + rr, yy + rr], fill=col)
    d.rectangle([0, base + S * k * 0.02, S, S], fill=ARBOL[0])
    return img.resize((tam_final, tam_final), Image.LANCZOS)


def main():
    ic = RAIZ / 'docs' / 'icons'
    for tam, nombre in ((192, 'icon-192.png'), (512, 'icon-512.png'), (180, 'apple-touch-icon.png'), (48, 'favicon.png')):
        dibujar(tam).convert('RGB').save(ic / nombre)
    dibujar(512, k=0.78).convert('RGB').save(ic / 'maskable-512.png')   # motivo dentro de la zona segura (80 %)
    print('iconos listos')


if __name__ == '__main__':
    main()
