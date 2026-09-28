"""Analiza la calidad de las traducciones (en, pt) de GeoParquemet comparando cada segmento con el español.

Revisiones automáticas (sin internet, siempre):
  - sin traducir: segmento vacío o idéntico al español
  - glosario: los enlaces [[termino|...]] deben ser los mismos que en español
  - números: todas las cifras del español deben aparecer (2,6 ↔ 2.6; 11.700 ↔ 11,700)
  - nombres propios: Pío Nono, Tupahue, San Cristóbal, Sernageomin, etc. se conservan
  - terminología: cada término geológico se traduce con la forma acordada y siempre igual
  - restos de español: palabras que delatan texto sin traducir
  - longitud: largo anómalo respecto del español (posible omisión o agregado)
  - formato: paréntesis, comillas, etiquetas HTML y variables {x} de la interfaz
Análisis opcionales:
  --semantica  similitud de significado con un modelo multilingüe de frases (descarga ~470 MB la 1ª vez)
               y detección de párrafos desalineados (la traducción se parece más a otro párrafo)
  --audio      transcribe la narración con Whisper y la compara con el guion (pronunciación, cortes)
  --ia         evaluación de adecuación y fluidez con Claude (requiere ANTHROPIC_API_KEY)

Uso:  python tools/revisar_traducciones.py [--lang en pt] [--semantica] [--audio] [--ia]
Salida: tools/_revision/informe.html y tools/_revision/informe.json
"""
import argparse, difflib, html, json, os, re, sys, unicodedata, urllib.request
from collections import Counter, defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DATA = RAIZ / 'docs' / 'data'
TRAD = RAIZ / 'tools' / '_trad'
SALIDA = RAIZ / 'tools' / '_revision'
NOMBRE_IDIOMA = {'en': 'Inglés', 'pt': 'Portugués'}

# ---------------------------------------------------------------- reglas
# nombres propios que deben conservarse tal cual (se comparan sin tildes)
NOMBRES = ['Pío Nono', 'Tupahue', 'San Cristóbal', 'Sernageomin', 'GEOPARQUEMET', 'Parquemet', 'Santiago',
           'Abanico', 'El Carbón', 'Cerro Blanco', 'La Pirámide', 'Chacarillas', 'Gemelo', 'Atacameño',
           'Santa Lucía', 'Lota', 'Osorno', 'Pilauco', 'Tagua-Tagua', 'Higgins', 'Luis Aguirre', 'Sellés',
           'Grande Coupure', 'Homo sapiens', 'Homo habilis', 'Homo erectus', 'Australopithecus', 'Albita', 'Anortita',
           'Himalaya', 'Alpes', 'Panamá', 'Google']
EQUIV_NOMBRE = {  # formas válidas en otros idiomas
    'Albita': ['albite', 'albita'], 'Anortita': ['anorthite', 'anortita'], 'Alpes': ['alps', 'alpes'],
    'Himalaya': ['himalaya', 'himalaia'], 'Panamá': ['panama'], 'Cerro Blanco': ['cerro blanco', 'morro blanco'],
    'Higgins': ['higgins'],
}
# términos geológicos: regex en español → formas esperadas / formas a evitar
TERMINOS = [
    # (id, regex español, {lang: (regex esperada, regex a evitar | None)})
    ('meteorización esferoidal', r'meteorizaci[oó]n esferoidal',
     {'en': (r'spheroidal weathering', None), 'pt': (r'esfolia[çc][ãa]o esferoidal', r'meteoriza[çc][ãa]o')}),
    ('meteorización', r'meteorizaci[oó]n(?! esferoidal)',
     {'en': (r'weathering', None), 'pt': (r'intemperismo', r'meteoriza[çc][ãa]o')}),
    ('rocas intrusivas', r'rocas? intrusivas?', {'en': (r'intrusive', None), 'pt': (r'rochas? intrusivas?', None)}),
    ('rocas volcánicas', r'rocas? volc[aá]nicas?', {'en': (r'volcanic', None), 'pt': (r'rochas? vulc[aâ]nicas?', None)}),
    ('toba soldada', r'tobas? soldadas?', {'en': (r'welded tuffs?', r'\btuft'), 'pt': (r'tufos? soldados?', None)}),
    ('toba', r'\btobas?\b(?! soldad)', {'en': (r'\btuffs?\b', r'\btufts?\b'), 'pt': (r'\btufos?\b', None)}),
    ('dique', r'\bdiques?\b', {'en': (r'\bdikes?\b', r'\bdykes?\b'), 'pt': (r'\bdiques?\b', None)}),
    ('piroxeno', r'piroxenos?', {'en': (r'pyroxenes?', None), 'pt': (r'pirox[êe]nios?', r'piroxenos?\b')}),
    ('plagioclasa', r'plagioclasas?', {'en': (r'plagioclases?', None), 'pt': (r'plagiocl[áa]sios?', r'plagioclasas?\b')}),
    ('geositio', r'geositios?', {'en': (r'geosites?', None), 'pt': (r'geoss[íi]tios?', r'geos[íi]tios?\b')}),
    ('georuta', r'geo-?rutas?', {'en': (r'geo-?routes?', None), 'pt': (r'georrotas?', r'georutas?')}),
    ('cámara magmática', r'c[aá]maras? (?:volc[aá]nicas? o )?magm[aá]ticas?',
     {'en': (r'magma chambers?', None), 'pt': (r'c[âa]maras? (?:vulc[âa]nicas? ou )?magm[áa]ticas?', None)}),
    ('placas tectónicas', r'placas tect[oó]nicas', {'en': (r'tectonic plates', None), 'pt': (r'placas tect[ôo]nicas', None)}),
    ('carbonato de calcio', r'carbonato de calcio', {'en': (r'calcium carbonate', None), 'pt': (r'carbonato de c[áa]lcio', None)}),
    ('agentes atmosféricos', r'agentes atmosf[eé]ricos', {'en': (r'atmospheric agents', None), 'pt': (r'agentes atmosf[ée]ricos', None)}),
    ('conductos alimentadores', r'conductos? alimentadores?', {'en': (r'feeder conduits?', None), 'pt': (r'condutos? alimentadores?', None)}),
    ('fiammes', r'fiammes?', {'en': (r'fiamme', None), 'pt': (r'fiammes', None)}),
    ('erupción volcánica', r'erupci[oó]n(?:es)? volc[aá]nicas?', {'en': (r'volcanic eruptions?', None), 'pt': (r'erup[çc][õo](?:es)? vulc[âa]nicas?|erup[çc][ãa]o vulc[âa]nica', None)}),
    ('Formación Abanico', r'Formaci[oó]n Abanico', {'en': (r'Abanico Formation', None), 'pt': (r'Forma[çc][ãa]o Abanico', None)}),
    ('cerro (nombre de lugar)*', r'\bcerros?\b', {'en': (r'\bhills?\b|\bcerro\b|\bridge\b', None), 'pt': (r'\bmorros?\b|\bcerro\b', r'\bcerros\b')}),
]
# palabras que delatan español sin traducir
RESTOS = {
    'en': r'\b(?:de|la|las|los|del|que|y|en|por|con|una|es|son|muy|pero|como|esta|este|rocas?|cerro)\b',
    # (?<!-) evita los pronombres enclíticos del portugués: vê-los, destacá-las
    'pt': r'(?<!-)\b(?:y|del|los|las|hacia|muy|también|cuando|donde|pero|cerros|puede|pueden|ellas?)\b|ci[oó]n\b|ciones\b',
}
# largo esperado de la traducción respecto del español (proporción de caracteres)
RANGO_LARGO = {'en': (0.62, 1.25), 'pt': (0.74, 1.25)}


def sin_tildes(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn').lower()


def plano(s):
    return re.sub(r'\[\[[^|\]]+\|([^\]]+)\]\]', r'\1', s)


_N = ['cuatro', 'cinco', 'seis', 'siete', 'ocho', 'nueve', 'diez']
PALABRAS_NUM = {
    'es': dict(zip(['uno', 'una', 'dos', 'tres'] + _N, [1, 1, 2, 3] + list(range(4, 11)))),
    'en': dict(zip(['one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten'], range(1, 11))),
    'pt': dict(zip(['um', 'uma', 'dois', 'duas', 'três', 'quatro', 'cinco', 'seis', 'sete', 'oito', 'nove', 'dez'],
                   [1, 1, 2, 2, 3, 4, 5, 6, 7, 8, 9, 10])),
}
# un número escrito con palabras cuenta como cifra solo antes de estas palabras (evita «una roca», «one of»)
CONTABLES = r'millones|million|milhões|glaciaciones|glaciations|glacia[çc][õo]es|lados|sides|metros|meters|subunidades|subunits'


def numeros(s, lang):
    """Cifras normalizadas: 11.700 / 11,700 → 11700 ; 2,6 / 2.6 → 2.6 ; ’60 → 1960 ; «cinco glaciaciones» → 5."""
    s = plano(s)
    s = re.sub(r"[’']\s?(\d{2})\b", r'19\1', s)
    pal = PALABRAS_NUM[lang]
    s = re.sub(rf"\b({'|'.join(pal)})\b(?=\s+(?:de\s+)?(?:{CONTABLES})|\s*\))",
               lambda m: str(pal[m.group(1).lower()]), s, flags=re.I)
    out = []
    for m in re.finditer(r'\d[\d.,]*\d|\d', s):
        x = m.group()
        if lang == 'en':
            x = x.replace(',', '')
        else:  # es y pt: punto = miles, coma = decimal
            if re.fullmatch(r'\d{1,3}(?:\.\d{3})+', x):
                x = x.replace('.', '')
            x = x.replace(',', '.')
        x = x.rstrip('.')
        try:
            v = float(x)
            out.append(str(int(v)) if v == int(v) else str(v))
        except ValueError:
            pass
    return Counter(out)


def enlaces(s):
    return Counter(re.findall(r'\[\[([^|\]]+)\|', s))


# ---------------------------------------------------------------- segmentos
def cargar_ui():
    """Lee docs/i18n.js sin Node: extrae clave → texto de cada bloque de idioma."""
    js = (RAIZ / 'docs' / 'i18n.js').read_text(encoding='utf-8')
    bloques = {}
    for lang in ('es', 'en', 'pt'):
        m = re.search(rf'\n  {lang}: \{{(.*?)\n  \}},', js, re.S)
        cuerpo = m.group(1)
        d = {}
        for k, v in re.findall(r"(\w+): ('(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"|\[[^\]]*\])", cuerpo):
            if v.startswith('['):
                d[k] = ' | '.join(re.findall(r"'([^']*)'", v))
            else:
                d[k] = v[1:-1].replace("\\'", "'").replace('\\"', '"')
        bloques[lang] = d
    return bloques


def segmentos(lang):
    """Lista de (id, grupo, es, traducción)."""
    tour = json.loads((DATA / 'tour.json').read_text(encoding='utf-8'))
    glos = json.loads((DATA / 'glosario.json').read_text(encoding='utf-8'))
    quiz = json.loads((DATA / 'quiz.json').read_text(encoding='utf-8'))
    geo = json.loads((DATA / 'geologia.geojson').read_text(encoding='utf-8'))
    t = json.loads((TRAD / f'tour_{lang}.json').read_text(encoding='utf-8'))
    g = json.loads((TRAD / f'glosario_{lang}.json').read_text(encoding='utf-8'))
    x = json.loads((TRAD / f'extra_{lang}.json').read_text(encoding='utf-8'))
    segs = []
    add = lambda i, gr, a, b: segs.append({'id': i, 'grupo': gr, 'es': a, 'tr': b if b is not None else ''})
    for i, p in enumerate(tour['intro']):
        add(f'intro.{i + 1}', 'Introducción', p, t['intro'][i] if i < len(t['intro']) else None)
    add('aviso', 'Introducción', tour['aviso'], t.get('aviso'))
    for s in tour['sitios']:
        tr = t['sitios'].get(str(s['n']), {})
        gr = f"Geositio {s['n']}"
        add(f"g{s['n']}.titulo", gr, s['titulo'], tr.get('titulo'))
        add(f"g{s['n']}.pie", gr, s['cap'], tr.get('cap'))
        for k in ('texto', 'texto_web'):
            for i, p in enumerate(s[k]):
                lst = tr.get(k, [])
                add(f"g{s['n']}.{k}.{i + 1}", gr, p, lst[i] if i < len(lst) else None)
    for slug, v in glos.items():
        tr = g.get(slug, {})
        add(f'glos.{slug}.titulo', 'Glosario', v['t'], tr.get('t'))
        for i, p in enumerate(v['d']):
            lst = tr.get('d', [])
            add(f'glos.{slug}.{i + 1}', 'Glosario', p, lst[i] if i < len(lst) else None)
    for n, q in quiz.items():
        tq = x['quiz'].get(n, {})
        add(f'quiz.{n}.pregunta', 'Quiz', q['p'], tq.get('p'))
        for i, r in enumerate(q['r']):
            lst = tq.get('r', [])
            add(f'quiz.{n}.alt{i + 1}', 'Quiz', r, lst[i] if i < len(lst) else None)
        add(f'quiz.{n}.explicacion', 'Quiz', q['e'], tq.get('e'))
    vistos = set()
    for f in geo['features']:
        p = f['properties']
        if p['unidad'] in vistos:
            continue
        vistos.add(p['unidad'])
        tg = x['geologia'].get(p['unidad'], {})
        d = p['desc'] or ''
        d = d[:d.rfind('.') + 1] if d.rfind('.') > 40 else d
        add(f"geo.{p['unidad']}.edad", 'Geología', p['edad'].replace('\n', ' '), tg.get('edad'))
        add(f"geo.{p['unidad']}.desc", 'Geología', re.sub(r'\s+', ' ', d), tg.get('desc'))
    ui = cargar_ui()
    for k, v in ui['es'].items():
        add(f'ui.{k}', 'Interfaz', v, ui[lang].get(k))
    return segs


# ---------------------------------------------------------------- revisiones
def revisar(seg, lang):
    es, tr = seg['es'], seg['tr']
    P = []  # (gravedad, revisión, detalle)
    if not tr.strip():
        return [('error', 'sin traducir', 'falta la traducción')]
    corto = len(plano(es)) < 25
    if plano(tr).strip() == plano(es).strip() and not corto and not re.fullmatch(r'[\W\d]*[A-Z][\w\s·–-]*', es):
        P.append(('error', 'sin traducir', 'idéntico al español'))
    a, b = enlaces(es), enlaces(tr)
    if a != b:
        faltan, sobran = a - b, b - a
        det = []
        if faltan: det.append('faltan ' + ', '.join(faltan))
        if sobran: det.append('sobran ' + ', '.join(sobran))
        P.append(('error', 'glosario', '; '.join(det)))
    na, nb = numeros(es, 'es'), numeros(tr, lang)
    faltan = na - nb
    if faltan:
        P.append(('error', 'números', 'faltan ' + ', '.join(sorted(faltan))))
    trs = sin_tildes(plano(tr))
    sin_marcas = lambda s: ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')
    esp = sin_marcas(plano(es))
    for nom in NOMBRES:
        # se respetan mayúsculas: «el carbón» (el mineral) no es el cerro «El Carbón»
        if re.search(rf'\b{re.escape(sin_marcas(nom))}\b', esp):
            formas = [sin_tildes(f) for f in EQUIV_NOMBRE.get(nom, [nom])]
            if not any(re.search(rf'\b{re.escape(f)}', trs) for f in formas):
                P.append(('aviso', 'nombres propios', f'no aparece «{nom}»'))
    for tid, rx_es, por_lang in TERMINOS:
        if lang not in por_lang or not re.search(rx_es, plano(es), re.I):
            continue
        esperado, evitar = por_lang[lang]
        if evitar and re.search(evitar, plano(tr), re.I):
            P.append(('aviso', 'terminología', f'«{tid}»: forma a evitar ({re.search(evitar, plano(tr), re.I).group()})'))
        elif not re.search(esperado, plano(tr), re.I):
            P.append(('aviso', 'terminología', f'«{tid}» sin la forma acordada'))
    # restos de español: se ignoran nombres propios
    limpio = plano(tr)
    extra = ['Cerro El Carbón', 'Cerro San Cristóbal', 'La Pirámide', 'de Chile', 'San Vicente de Tagua-Tagua', 'Los Lagos', 'Los Gemelos', 'Pío Nono']
    for nom in sorted(NOMBRES + extra, key=len, reverse=True):  # primero los más largos
        limpio = re.sub(re.escape(nom), ' ', limpio, flags=re.I)
    if seg['grupo'] != 'Interfaz' or lang == 'en':
        restos = re.findall(RESTOS[lang], limpio, re.I)
        if lang == 'en':
            restos = [r for r in restos if r.lower() not in ('de',)] if len(restos) < 3 else restos
        if len(restos) >= (2 if lang == 'en' else 1):
            P.append(('aviso', 'restos de español', ', '.join(sorted(set(r.lower() for r in restos)))))
    la, lb = len(plano(es)), len(plano(tr))
    if la >= 60 and seg['grupo'] != 'Geología':  # el español de ArcGIS viene recortado
        r = lb / la
        mn, mx = RANGO_LARGO[lang]
        if r < mn or r > mx:
            P.append(('aviso', 'longitud', f'{r:.2f} × el español (esperado {mn}–{mx})'))
    for ab, ce, nombre in (('(', ')', 'paréntesis'), ('«', '»', 'comillas «»'), ('“', '”', 'comillas “”')):
        if tr.count(ab) != tr.count(ce):
            P.append(('aviso', 'formato', f'{nombre} desbalanceados'))
    if es.count('(') != tr.count('(') and seg['grupo'] != 'Interfaz':
        P.append(('info', 'formato', f'paréntesis: {es.count("(")} en español, {tr.count("(")} en la traducción'))
    if seg['grupo'] == 'Interfaz':
        va, vb = set(re.findall(r'\{(\w+)\}', es)), set(re.findall(r'\{(\w+)\}', tr))
        if va != vb:
            P.append(('error', 'formato', f'variables distintas: {sorted(va)} vs {sorted(vb)}'))
        ta, tb = Counter(re.findall(r'</?(\w+)', es)), Counter(re.findall(r'</?(\w+)', tr))
        if ta != tb:
            P.append(('error', 'formato', 'etiquetas HTML distintas'))
    if re.search(r'  |\s[,.;:]', plano(tr)):
        P.append(('info', 'formato', 'espacios dobles o antes de puntuación'))
    fin_es, fin_tr = plano(es).rstrip()[-1:], plano(tr).rstrip()[-1:]
    if fin_es in '.!?' and fin_tr not in '.!?”»"' and seg['grupo'] != 'Interfaz' and len(es) > 40:
        P.append(('info', 'formato', 'no termina en punto como el español'))
    return P


def consistencia(segs, lang):
    """El mismo término en español debe traducirse siempre igual (títulos del glosario vs uso en textos)."""
    avisos = []
    for tid, rx_es, por_lang in TERMINOS:
        if lang not in por_lang or tid.endswith('*'):  # * = varias formas válidas (nombres de lugar)
            continue
        formas = Counter()
        for s in segs:
            if s['tr'] and re.search(rx_es, plano(s['es']), re.I):
                m = re.search(por_lang[lang][0], plano(s['tr']), re.I)
                if m:
                    formas[sin_tildes(m.group())] += 1
        if len(formas) > 1:
            # singular/plural y guiones no cuentan como formas distintas
            norm = lambda f: ' '.join(re.sub(r'(?<=[a-z]{3})s$', '', re.sub(r'oes$', 'ao', w)) for w in f.replace('-', '').split())
            base = {norm(f) for f in formas if not re.search(r' (?:ou|o|or) ', f)}
            if len(base) > 1:
                avisos.append({'termino': tid, 'formas': dict(formas)})
    return avisos


# ---------------------------------------------------------------- opcionales
def semantica(segs, modelo):
    from sentence_transformers import SentenceTransformer
    import numpy as np
    m = SentenceTransformer(modelo)
    utiles = [s for s in segs if s['tr'] and len(plano(s['es'])) >= 40 and s['grupo'] != 'Interfaz']
    ea = m.encode([plano(s['es']) for s in utiles], normalize_embeddings=True, batch_size=16, show_progress_bar=False)
    eb = m.encode([plano(s['tr']) for s in utiles], normalize_embeddings=True, batch_size=16, show_progress_bar=False)
    sim = eb @ ea.T
    for i, s in enumerate(utiles):
        s['similitud'] = float(sim[i, i])
        j = int(np.argmax(sim[i]))
        if j != i and sim[i, j] - sim[i, i] > 0.03:
            s.setdefault('problemas', []).append(('error', 'desalineado', f"se parece más a {utiles[j]['id']} ({sim[i, j]:.2f} vs {sim[i, i]:.2f})"))
        if s['similitud'] < 0.80:
            s.setdefault('problemas', []).append(('aviso' if s['similitud'] >= 0.70 else 'error', 'significado', f"similitud {s['similitud']:.2f}"))


def audio(lang):
    sys.path.insert(0, str(Path(__file__).parent))
    from voces import guion, TITULO, INTRO
    from faster_whisper import WhisperModel
    m = WhisperModel('small', device='cpu', compute_type='int8')
    t = json.loads((TRAD / f'tour_{lang}.json').read_text(encoding='utf-8'))
    pistas = [('intro', [INTRO[lang]] + t['intro'] + [t['aviso']])]
    pistas += [(f'g{n}', [TITULO[lang].format(n=n, t=s['titulo'])] + s['texto'] + s['texto_web']) for n, s in t['sitios'].items()]
    norm = lambda s: re.findall(r'[a-z0-9]+', sin_tildes(s))
    res = []
    for nombre, pars in pistas:
        mp3 = RAIZ / 'docs' / 'audio' / lang / f'{nombre}.mp3'
        if not mp3.exists():
            res.append({'pista': nombre, 'error': 'no existe'}); continue
        escrito = norm(' '.join(guion(p, lang) for p in pars))
        segs_w, _ = m.transcribe(str(mp3), language=lang, beam_size=1)
        oido = norm(' '.join(s.text for s in segs_w))
        sm = difflib.SequenceMatcher(None, escrito, oido, autojunk=False)
        difs = []
        for op, a1, a2, b1, b2 in sm.get_opcodes():
            if op != 'equal':
                difs.append((' '.join(escrito[a1:a2]), ' '.join(oido[b1:b2])))
        res.append({'pista': nombre, 'coincidencia': round(sm.ratio(), 3), 'palabras': len(escrito),
                    'diferencias': Counter(f'{a} → {b}' for a, b in difs if a).most_common(15)})
        print(f'  audio {lang}/{nombre}: {sm.ratio():.1%}')
    return res


def evaluar_ia(segs, lang, modelo):
    clave = os.environ.get('ANTHROPIC_API_KEY')
    if not clave:
        print('  --ia: falta la variable ANTHROPIC_API_KEY; se omite'); return
    idioma = {'en': 'English', 'pt': 'Brazilian Portuguese'}[lang]
    por_grupo = defaultdict(list)
    for s in segs:
        if s['tr'] and s['grupo'] != 'Interfaz' and len(plano(s['es'])) > 20:
            por_grupo[s['grupo']].append(s)
    idx = {s['id']: s for s in segs}
    for grupo, lote in por_grupo.items():
        for k in range(0, len(lote), 12):
            parte = lote[k:k + 12]
            items = '\n'.join(json.dumps({'id': s['id'], 'es': plano(s['es']), 'tr': plano(s['tr'])}, ensure_ascii=False) for s in parte)
            prompt = (f'You review Spanish→{idioma} translations of a geology field-guide app for park visitors (Santiago, Chile). '
                      'For each item rate adequacy (meaning preserved, 1-5) and fluency (natural target language, 1-5). '
                      'List concrete problems (mistranslation, omission, addition, wrong geology term, awkward phrasing) and '
                      'give a corrected version only if there is a real problem. Answer ONLY a JSON array of objects '
                      '{"id","adecuacion","fluidez","problemas":[...],"sugerencia":""}. Problems in Spanish.\n\n' + items)
            cuerpo = json.dumps({'model': modelo, 'max_tokens': 4000, 'messages': [{'role': 'user', 'content': prompt}]}).encode()
            req = urllib.request.Request('https://api.anthropic.com/v1/messages', data=cuerpo, headers={
                'x-api-key': clave, 'anthropic-version': '2023-06-01', 'content-type': 'application/json'})
            try:
                with urllib.request.urlopen(req, timeout=180) as r:
                    txt = json.loads(r.read())['content'][0]['text']
                datos = json.loads(txt[txt.find('['):txt.rfind(']') + 1])
            except Exception as ex:
                print('  --ia error', grupo, ex); continue
            for d in datos:
                s = idx.get(d.get('id'))
                if not s:
                    continue
                s['ia'] = d
                nota = min(d.get('adecuacion', 5), d.get('fluidez', 5))
                if nota <= 3:
                    s.setdefault('problemas', []).append(('error' if nota <= 2 else 'aviso', 'IA',
                                                          f"adecuación {d.get('adecuacion')}, fluidez {d.get('fluidez')}: " + '; '.join(d.get('problemas', []))))
            print(f'  IA {lang} {grupo}: {len(datos)} segmentos')


# ---------------------------------------------------------------- informe
def puntaje(segs):
    pen = sum({'error': 5, 'aviso': 1.5, 'info': 0.2}[g] for s in segs for g, _, _ in s.get('problemas', []))
    return max(0, round(100 - pen * 100 / max(1, len(segs)) / 2, 1))


def informe(resultados, destino):
    SALIDA.mkdir(parents=True, exist_ok=True)
    (SALIDA / 'informe.json').write_text(json.dumps(resultados, ensure_ascii=False, indent=1, default=list), encoding='utf-8')
    e = html.escape
    marca = lambda s: re.sub(r'\[\[[^|\]]+\|([^\]]+)\]\]', r'<u>\1</u>', e(s))
    partes = []
    for lang, r in resultados.items():
        segs = r['segmentos']
        cnt = Counter(g for s in segs for g, _, _ in s.get('problemas', []))
        porrev = Counter(rv for s in segs for _, rv, _ in s.get('problemas', []))
        limpios = sum(1 for s in segs if not any(g != 'info' for g, _, _ in s.get('problemas', [])))
        filas = []
        for s in segs:
            pr = s.get('problemas', [])
            if not pr:
                continue
            gmax = 'error' if any(g == 'error' for g, _, _ in pr) else 'aviso' if any(g == 'aviso' for g, _, _ in pr) else 'info'
            sim = f"<br><small>similitud {s['similitud']:.2f}</small>" if 'similitud' in s else ''
            sug = f"<div class='sug'>💡 {e(s['ia']['sugerencia'])}</div>" if s.get('ia', {}).get('sugerencia') else ''
            filas.append(f"<tr class='{gmax}' data-g='{gmax}'><td><b>{e(s['id'])}</b><br><small>{e(s['grupo'])}</small>{sim}</td>"
                         f"<td>{marca(s['es'])}</td><td>{marca(s['tr'])}{sug}</td><td><ul>"
                         + ''.join(f"<li class='{g}'><b>{e(rv)}</b>: {e(d)}</li>" for g, rv, d in pr) + '</ul></td></tr>')
        cons = ''.join(f"<li><b>{e(c['termino'])}</b>: {e(', '.join(f'{k} ({v})' for k, v in c['formas'].items()))}</li>" for c in r['consistencia'])
        aud = ''
        if r.get('audio'):
            aud = '<h3>Narración (Whisper vs guion)</h3><table><tr><th>Pista</th><th>Coincidencia</th><th>Diferencias más frecuentes (guion → oído)</th></tr>' + ''.join(
                f"<tr class='{'error' if a.get('coincidencia', 0) < .85 else 'aviso' if a.get('coincidencia', 0) < .93 else ''}'><td>{e(a['pista'])}</td><td>{a.get('coincidencia', a.get('error'))}</td>"
                f"<td>{e('; '.join(f'{d} ×{n}' for d, n in a.get('diferencias', [])))}</td></tr>" for a in r['audio']) + '</table>'
        partes.append(f"""<section><h2>{NOMBRE_IDIOMA[lang]} <span class='nota'>{r['puntaje']}/100</span></h2>
<p>{len(segs)} segmentos · <b>{limpios}</b> sin problemas ({limpios * 100 // len(segs)} %) · {cnt['error']} errores · {cnt['aviso']} avisos · {cnt['info']} observaciones menores</p>
<p class='chips'>{' '.join(f'<span>{e(k)}: {v}</span>' for k, v in porrev.most_common())}</p>
{f'<h3>Términos traducidos de más de una forma</h3><ul>{cons}</ul>' if cons else ''}
{aud}
<h3>Segmentos con observaciones</h3>
<table class='segs'><tr><th>Segmento</th><th>Español</th><th>Traducción</th><th>Observaciones</th></tr>{''.join(filas)}</table></section>""")
    doc = f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Revisión de traducciones</title><style>
:root{{--f:#fff;--t:#1f2a24;--l:#ddd;--err:#fde2e1;--av:#fff4d6;--inf:#eef3f8}}
@media (prefers-color-scheme:dark){{:root{{--f:#141b17;--t:#e9ece8;--l:#333;--err:#4a2323;--av:#443a1c;--inf:#1e2a36}}}}
body{{font:15px/1.5 system-ui,sans-serif;background:var(--f);color:var(--t);margin:0;padding:16px;max-width:1300px;margin:auto}}
h1{{margin:0 0 4px}}.nota{{background:#e08a00;color:#fff;border-radius:999px;padding:2px 12px;font-size:.9em}}
table{{border-collapse:collapse;width:100%;margin:8px 0 20px}}td,th{{border:1px solid var(--l);padding:6px 8px;vertical-align:top;text-align:left}}
.segs td:nth-child(2),.segs td:nth-child(3){{width:32%}}tr.error td:first-child{{border-left:5px solid #d33}}tr.aviso td:first-child{{border-left:5px solid #e0a000}}
li.error{{background:var(--err)}}li.aviso{{background:var(--av)}}li.info{{background:var(--inf)}}ul{{margin:0;padding-left:18px}}
.chips span{{display:inline-block;border:1px solid var(--l);border-radius:999px;padding:1px 10px;margin:2px;font-size:.85em}}
.sug{{margin-top:6px;font-size:.9em;border-top:1px dashed var(--l);padding-top:4px}}u{{text-decoration-color:#e08a00}}
.filtro button{{margin-right:6px}}@media(max-width:700px){{.segs td{{display:block;width:auto!important}}}}
</style></head><body><h1>Revisión de traducciones · GeoParquemet</h1>
<p>Comparación automática de cada segmento traducido con el español. <b>Errores</b>: casi seguro hay que corregir. <b>Avisos</b>: revisar. <b>Observaciones</b>: detalles de forma.</p>
<p class="filtro">Mostrar: <button onclick="f('')">todo</button><button onclick="f('error')">solo errores</button><button onclick="f('aviso')">errores y avisos</button></p>
{''.join(partes)}
<script>function f(g){{document.querySelectorAll('tr[data-g]').forEach(r=>r.hidden=g&&!(r.dataset.g==='error'||(g==='aviso'&&r.dataset.g==='aviso')))}}</script>
</body></html>"""
    destino.write_text(doc, encoding='utf-8')


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--lang', nargs='+', default=['en', 'pt'], choices=['en', 'pt'])
    ap.add_argument('--semantica', action='store_true')
    ap.add_argument('--modelo-semantico', default='sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')
    ap.add_argument('--audio', action='store_true')
    ap.add_argument('--ia', action='store_true')
    ap.add_argument('--modelo-ia', default='claude-sonnet-5')
    a = ap.parse_args()
    resultados = {}
    for lang in a.lang:
        segs = segmentos(lang)
        for s in segs:
            s['problemas'] = revisar(s, lang)
        if a.semantica:
            semantica(segs, a.modelo_semantico)
        if a.ia:
            evaluar_ia(segs, lang, a.modelo_ia)
        r = {'segmentos': segs, 'consistencia': consistencia(segs, lang)}
        if a.audio:
            r['audio'] = audio(lang)
        r['puntaje'] = puntaje(segs)
        resultados[lang] = r
        cnt = Counter(g for s in segs for g, _, _ in s['problemas'])
        print(f"{NOMBRE_IDIOMA[lang]}: {r['puntaje']}/100 · {len(segs)} segmentos · {cnt['error']} errores · {cnt['aviso']} avisos · {cnt['info']} menores")
        for s in segs:
            for g, rv, d in s['problemas']:
                if g == 'error':
                    print(f"   ✗ {s['id']}: {rv} — {d}")
    destino = SALIDA / 'informe.html'
    SALIDA.mkdir(parents=True, exist_ok=True)
    informe(resultados, destino)
    print('Informe:', destino)


if __name__ == '__main__':
    main()
