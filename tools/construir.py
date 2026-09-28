"""Arma docs/data/tour.json, geologia.geojson y las imágenes WebP a partir de:
- fuentes/earth_tour.json  (texto del geotour de Google Earth del autor)
- fuentes/geositio-N.html  (sitio geoparquemet.netlify.app: texto interpretativo, pares de fotos, 3D, videos)
- fuentes/*.geojson        (capas ArcGIS Online de Geopatrimonio Sernageomin: geositios, Georuta 1, geología)
- fuentes/terms/*.html     (glosario)
"""
import html, io, json, math, re, sys, urllib.request
from pathlib import Path
from PIL import Image

RAIZ = Path(__file__).resolve().parent.parent
F = RAIZ / 'fuentes'
D = RAIZ / 'docs'
CACHE = F / '_img'
CACHE.mkdir(exist_ok=True)
BASE = 'https://geoparquemet.netlify.app/assets/'


def limpiar_html_tooltips(s):
    # enlaces del glosario → [[slug|texto]]; se quita el contenido oculto del tooltip
    s = re.sub(r'<span class="hidden glossary-tooltip-content.*?</span>\s*</span>', '', s, flags=re.S)
    s = re.sub(r"<a href='/paginas/terms__([^']+)'[^>]*>(.*?)</a>",
               lambda m: f'[[{m.group(1)}|{re.sub("<[^>]+>", "", m.group(2)).strip()}]]', s, flags=re.S)
    return s


def a_texto(s):
    s = re.sub(r'<br\s*/?>', '\n', s)
    s = re.sub(r'<[^>]+>', '', s)
    s = html.unescape(s).replace('\xa0', ' ')
    s = re.sub(r'[ \t]+', ' ', s)
    s = re.sub(r'\s+([,.;:)])', r'\1', s)
    return s.strip()


def texto_web(s):
    """Párrafos del texto interpretativo (entre el reproductor de audio y 'Vista 3D' / primer comparador)."""
    i = s.find('<div class="post-content">')
    b = s[i:]
    ini = b.find('</audio>')
    fin = min(x for x in (b.find('fusion-image-before-after', ini), b.find('Vista 3D', ini), len(b)) if x > 0)
    trozo = limpiar_html_tooltips(b[ini:fin])
    trozo = re.sub(r'<script.*?</script>|<style.*?</style>', '', trozo, flags=re.S)
    pars = [a_texto(p) for p in re.findall(r'<p[^>]*>(.*?)</p>', trozo, flags=re.S)]
    pars = [p for p in pars if len(p) > 40]
    # las marcas de glosario pueden haber quedado con espacios raros
    return [re.sub(r'\[\[\s*', '[[', p) for p in pars]


def _norm(s):
    s = re.sub(r'\[\[[^|\]]+\|([^\]]+)\]\]', r'\1', s)
    return re.sub(r'[^a-záéíóúñü0-9]+', ' ', s.lower()).strip()


def sin_repetidos(web, earth):
    """Quita del texto web las oraciones que ya están en el texto del geotour de Earth."""
    base = _norm(' '.join(earth))
    out = []
    for p in web:
        ors = re.split(r'(?<=[.!?”])\s+', p)
        quedan = [o for o in ors if len(_norm(o)) < 25 or _norm(o) not in base]
        t = ' '.join(quedan).strip()
        if len(t) > 40:
            out.append(t)
    return out


def pares(s):
    out = []
    for bloque in re.findall(r'fusion-image-before-after-element.*?fusion-image-before-after-handle', s, flags=re.S):
        imgs = re.findall(r'src="\.\./assets/([^"]+)"', bloque)
        if len(imgs) >= 2:
            out.append(imgs[:2])
    return out


def embeds(s):
    i = s.find('<div class="post-content">')
    ifr = [html.unescape(x) for x in re.findall(r'<iframe[^>]+src="([^"]+)"', s[i:])]
    sk = [re.search(r'models/([0-9a-f]{32})', x).group(1) for x in ifr if 'sketchfab' in x]
    sq = [x.split('?')[0] for x in ifr if 'seequent' in x]
    yt = [re.search(r'embed/([\w-]{11})', x).group(1) for x in ifr if 'youtube' in x]
    return sk, sq, yt


def bajar(nombre):
    p = CACHE / nombre
    if not p.exists():
        with urllib.request.urlopen(BASE + urllib.request.quote(nombre), timeout=60) as r:
            p.write_bytes(r.read())
    return p


def webp(src, dst, lado=1600):
    im = Image.open(src).convert('RGB')
    im.thumbnail((lado, lado), Image.LANCZOS)
    im.save(dst, 'WEBP', quality=80, method=6)
    return im.size


def redondear(coords, nd=6):
    if isinstance(coords[0], (int, float)):
        return [round(coords[0], nd), round(coords[1], nd)]
    return [redondear(c, nd) for c in coords]


def glosario():
    out = {}
    lista = (F / 'glosario.html').read_text(encoding='utf-8')
    titulos = {m.group(1): a_texto(m.group(2)) for m in re.finditer(r"href='/paginas/terms__([^']+)'>(.*?)</a>", lista)}
    for f in sorted((F / 'terms').glob('*.html')):
        s = f.read_text(encoding='utf-8')
        slug = f.stem
        i = s.find('<div class="post-content">')
        b = s[i:]
        corte = [k for k in (b.find('Para seguir navegando'), b.find('fusion-widget-area'), b.find('fusion-meta-info')) if k > 0]
        b = b[:min(corte)] if corte else b[:20000]
        b = limpiar_html_tooltips(b)
        pars = [a_texto(p) for p in re.findall(r'<p[^>]*>(.*?)</p>', b, flags=re.S)]
        pars = [p.replace('[[eoceno-2|', '[[eoceno|') for p in pars if len(p) > 3 and not p.rstrip().endswith(':')]
        t = re.search(r'<h1[^>]*entry-title[^>]*>(.*?)</h1>', s, re.S)
        titulo = a_texto(t.group(1)) if t else slug
        if slug in titulos:
            titulo = titulos[slug]
        elif titulo.lower() == 'glosario':
            titulo = slug.replace('-2', '').replace('-', ' ').upper()
        imgs = re.findall(r'src="\.\./assets/([^"]+)"', b)
        out[slug.replace('-2', '') if slug == 'eoceno-2' else slug] = {'t': titulo.strip().capitalize() if titulo.isupper() else titulo, 'd': pars, 'img': imgs}
    return out


def main():
    earth = json.loads((F / 'earth_tour.json').read_text(encoding='utf-8'))
    puntos = json.loads((F / 'Geo_Sitios_ParqueMet.geojson').read_text(encoding='utf-8'))['features']
    puntos = {int(re.search(r'\d+', p['properties']['CATEGORIA']).group()): p for p in puntos}
    (D / 'img').mkdir(exist_ok=True)
    sitios = []
    for e in earth['sitios']:
        n = e['n']
        p = puntos[n]
        lon, lat = p['geometry']['coordinates'][:2]
        s = (F / f'geositio-{n}.html').read_text(encoding='utf-8')
        fotos = []
        for k, (a, b) in enumerate(pares(s), 1):
            par = {}
            for lado, nom in (('a', a), ('b', b)):
                dst = f'img/g{n}_{k}{lado}.webp'
                w, h = webp(bajar(nom), D / dst)
                par[lado] = dst
                par['w'], par['h'] = w, h
            fotos.append(par)
        extra = re.findall(r'src="\.\./assets/(piscina-tupahue\.png)"', s)
        historicas = []
        for nom in sorted(set(extra)):
            dst = f'img/g{n}_hist.webp'
            w, h = webp(bajar(nom), D / dst)
            historicas.append({'src': dst, 'w': w, 'h': h})
        sk, sq, yt = embeds(s)
        sitios.append({
            'n': n,
            'id': p['properties'].get('ID_PUNTO'),
            'titulo': e['titulo'],
            'lat': round(lat, 6), 'lon': round(lon, 6),
            'elev': round(p['properties'].get('ELEVACION') or 0),
            'texto': e['texto'],
            'texto_web': sin_repetidos(texto_web(s), e['texto']),
            'cap': e['cap'],
            'fotos': fotos,
            'historicas': historicas,
            'sketchfab': sk, 'seequent': sq, 'youtube': yt,
            'sv': e['sv'],
        })
        print(n, e['titulo'], len(fotos), 'pares', sk, yt, len(sitios[-1]['texto_web']), 'párr. web')

    ruta = json.loads((F / 'Georuta1_v2.geojson').read_text(encoding='utf-8'))['features'][0]['geometry']
    ruta_coords = redondear(ruta['coordinates'])
    largo = sum(dist(a, b) for a, b in zip(ruta_coords, ruta_coords[1:]))

    geol = []
    for arch, tipo in (('c04_Formaci%C3%B3n_Abanico.geojson', 'volcanica'), ('c05_Rocas_intrusivas_3.geojson', 'intrusiva')):
        for f in json.loads((F / arch).read_text(encoding='utf-8'))['features']:
            pr = f['properties']
            geol.append({'type': 'Feature', 'geometry': {'type': f['geometry']['type'], 'coordinates': redondear(f['geometry']['coordinates'])},
                         'properties': {'tipo': tipo, 'unidad': pr.get('Unidad'), 'nombre': pr.get('Nombre'),
                                        'codigo': pr.get('Codigo_Nom') or pr.get('Codigo'),
                                        'edad': (pr.get('Edad') or '').strip('"').replace('\n', ' '),
                                        'desc': (pr.get('Descripcio') or '').strip('"').strip(),
                                        'termino': (pr.get('Enlace') or '').rstrip('/').split('/')[-1] or None}})
    (D / 'data' / 'geologia.geojson').write_text(json.dumps({'type': 'FeatureCollection', 'features': geol}, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')

    tour = {'titulo': 'GeoParquemet', 'ruta': earth['ruta'], 'largo_m': round(largo),
            'ruta_coords': [[c[1], c[0]] for c in ruta_coords], 'sitios': sitios}
    (D / 'data' / 'tour.json').write_text(json.dumps(tour, ensure_ascii=False, indent=1), encoding='utf-8')
    tour['intro'] = [
        'El Parque Metropolitano de Santiago es el parque urbano más grande de Chile y guarda en sus cerros la historia geológica de la ciudad. GEOPARQUEMET es un proyecto de la Unidad de Geopatrimonio de Sernageomin para identificar, registrar y poner en valor la geodiversidad y los geositios del parque.',
        'Para contarte esa historia hemos escogido algunos lugares significativos, a los que llamamos geositios, que reflejan los procesos más importantes o singulares que dieron origen a estos cerros y al relieve de nuestra ciudad. Estos geositios han sido agrupados en georutas, que puedes recorrer caminando en el parque o de manera virtual.',
        'La Geo-Ruta 1 une el acceso Pío Nono con la piscina Tupahue. A lo largo de casi tres kilómetros conocerás rocas volcánicas de 28 millones de años, rocas intrusivas de 21 millones de años y los procesos que las transforman hasta formar el suelo que pisamos.',
    ]
    tour['aviso'] = 'Camina por las veredas y senderos peatonales, lleva agua y protector solar, y mantente alejado de las paredes de roca: pueden caer bloques.'
    g = glosario()
    for v in g.values():
        for a, b in (('abanico', 'Abanico'), ('cerro blanco', 'Cerro Blanco'), ('cerro el carbón', 'Cerro El Carbón'), ('cerro san cristóbal', 'Cerro San Cristóbal')):
            v['t'] = v['t'].replace(a, b)
    g['macla'] = {'t': 'Macla', 'd': ['Agrupación de dos o más cristales de un mismo mineral que crecen unidos siguiendo una relación de simetría definida, de modo que unos aparecen como el reflejo o la rotación de los otros. Es muy común en los feldespatos, como la [[plagioclasa|plagioclasa]].'], 'img': [], 'corregido': True}
    for slug, v in g.items():
        nuevas = []
        for k, nom in enumerate(v['img']):
            try:
                dst = f'img/gl_{slug}_{k}.webp'
                w, h = webp(bajar(nom), D / dst, 1200)
                nuevas.append({'src': dst, 'w': w, 'h': h})
            except Exception as ex:
                print('  sin imagen', slug, nom, ex)
        v['img'] = nuevas
    s = (F / 'glosario.html').read_text(encoding='utf-8')
    i = s.find('Bibliograf')
    bib = []
    for p in re.findall(r'<p[^>]*>(.*?)</p>', s[i:i + 60000], flags=re.S):
        enlace = re.search(r'<a[^>]+href="(http[^"]+)"', p)
        t = a_texto(re.sub(r'Obtenido de\s*<a.*?</a>', '', p, flags=re.S)).replace('\n', ' ')
        t = re.sub(r'\s+', ' ', t).replace('Obtenido de', '').strip()
        if re.search(r'\(\d{4}\)', t):
            bib.append({'t': t, 'url': html.unescape(enlace.group(1)) if enlace else None})
    tour['bibliografia'] = bib
    (D / 'data' / 'tour.json').write_text(json.dumps(tour, ensure_ascii=False, indent=1), encoding='utf-8')
    print(len(bib), 'referencias')
    (D / 'data' / 'glosario.json').write_text(json.dumps(g, ensure_ascii=False, indent=1), encoding='utf-8')
    print('ruta', round(largo), 'm;', len(geol), 'polígonos;', len(g), 'términos')


def dist(a, b):
    R = 6371000
    la1, la2 = math.radians(a[1]), math.radians(b[1])
    dla, dlo = la2 - la1, math.radians(b[0] - a[0])
    h = math.sin(dla / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin(dlo / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
