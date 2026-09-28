"""Narración neural (edge-tts) de la introducción y de cada geositio, en español, inglés y portugués.

Cada párrafo se sintetiza aparte y los MP3 se concatenan (CBR 48 kbps), así se conoce el
segundo en que empieza cada párrafo para resaltarlo en la app.
Uso: python tools/voces.py [--lang es|en|pt] [--forzar]
  es → docs/audio/*.mp3 y marcas en docs/data/tour.json
  en/pt → docs/audio/<lang>/*.mp3 y marcas en docs/data/lang_<lang>.json (vía tools/idiomas.py)
"""
import argparse, asyncio, json, re, sys
from pathlib import Path
import edge_tts

RAIZ = Path(__file__).resolve().parent.parent
DATOS = RAIZ / 'docs' / 'data' / 'tour.json'
TRAD = RAIZ / 'tools' / '_trad'
AUDIO = RAIZ / 'docs' / 'audio'
BYTES_S = 48000 / 8
VOZ = {'es': 'es-CL-CatalinaNeural', 'en': 'en-US-AvaMultilingualNeural', 'pt': 'pt-BR-FranciscaNeural'}

COMUNES = [(r'\[\[[^|\]]+\|([^\]]+)\]\]', r'\1')]
REEMPLAZOS = {
    'es': [
        (r'\b([Gg])eositio', r'\1eo sitio'),          # "geositio" suena "geosicio"
        (r'\b([Gg])eo-?[Rr]uta', r'\1eo ruta'),
        (r'\bNo\.\s*(\d)', r'número \1'),
        (r'(\d)\s*cm\b', r'\1 centímetros'),
        (r'’60', 'sesenta'),
    ],
    'en': [
        (r'\bGeo-Route\b', 'Geo Route'),
        (r'\bNo\.\s*(\d)', r'number \1'),
        (r'(\d)\s*cm\b', r'\1 centimeters'),
        (r'\bGEOPARQUEMET\b|\bGeoParquemet\b', 'Geo Parque Met'),
        (r'\bTupahue\b', 'Tupawe'),
    ],
    'pt': [
        (r'\bnº\s*(\d)', r'número \1'),
        (r'\bGEOPARQUEMET\b|\bGeoParquemet\b', 'Geo Parque Mét'),
        (r'\bTupahue\b', 'Tupauê'),
        (r'(\d)\s*cm\b', r'\1 centímetros'),
    ],
}
TITULO = {'es': 'Geositio {n}. {t}.', 'en': 'Geosite {n}. {t}.', 'pt': 'Geossítio {n}. {t}.'}
INTRO = {'es': 'GeoParquemet. Geo-Ruta 1: Pío Nono, Tupahue.', 'en': 'GeoParquemet. Geo-Route 1: Pío Nono, Tupahue.',
         'pt': 'GeoParquemet. Georrota 1: Pío Nono, Tupahue.'}


def guion(t, lang):
    for a, b in COMUNES + REEMPLAZOS[lang]:
        t = re.sub(a, b, t)
    return re.sub(r'\s+', ' ', t).strip()


async def sintetizar(texto, lang):
    com = edge_tts.Communicate(texto, VOZ[lang], rate='-5%')
    datos = bytearray()
    async for trozo in com.stream():
        if trozo['type'] == 'audio':
            datos += trozo['data']
    return bytes(datos)


async def pista(nombre, parrafos, lang, forzar):
    carpeta = AUDIO if lang == 'es' else AUDIO / lang
    carpeta.mkdir(parents=True, exist_ok=True)
    dst = carpeta / f'{nombre}.mp3'
    meta = carpeta / f'{nombre}.json'
    if dst.exists() and meta.exists() and not forzar:
        return json.loads(meta.read_text(encoding='utf-8'))
    total = bytearray()
    marcas = []
    for p in parrafos:
        marcas.append(round(len(total) / BYTES_S, 2))
        for intento in range(4):
            try:
                total += await sintetizar(guion(p, lang), lang)
                break
            except Exception as ex:
                print('  reintento', nombre, ex)
                await asyncio.sleep(3 * (intento + 1))
    dst.write_bytes(bytes(total))
    ruta = f'audio/{nombre}.mp3' if lang == 'es' else f'audio/{lang}/{nombre}.mp3'
    info = {'src': ruta, 'dur': round(len(total) / BYTES_S, 1), 'marcas': marcas}
    meta.write_text(json.dumps(info), encoding='utf-8')
    print(lang, nombre, info['dur'], 's')
    return info


async def main(lang, forzar):
    AUDIO.mkdir(exist_ok=True)
    tour = json.loads(DATOS.read_text(encoding='utf-8'))
    if lang == 'es':
        tour['intro_audio'] = await pista('intro', [INTRO[lang]] + tour['intro'] + [tour['aviso']], lang, forzar)
        for s in tour['sitios']:
            pars = [TITULO[lang].format(n=s['n'], t=s['titulo'])] + s['texto'] + s['texto_web']
            s['audio'] = await pista(f"g{s['n']}", pars, lang, forzar)
        DATOS.write_text(json.dumps(tour, ensure_ascii=False, indent=1), encoding='utf-8')
        return
    t = json.loads((TRAD / f'tour_{lang}.json').read_text(encoding='utf-8'))
    await pista('intro', [INTRO[lang]] + t['intro'] + [t['aviso']], lang, forzar)
    for n, s in t['sitios'].items():
        pars = [TITULO[lang].format(n=n, t=s['titulo'])] + s['texto'] + s['texto_web']
        await pista(f'g{n}', pars, lang, forzar)
    sys.path.insert(0, str(Path(__file__).parent))
    import idiomas
    idiomas.construir(lang)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser()
    ap.add_argument('--lang', default='es', choices=['es', 'en', 'pt'])
    ap.add_argument('--forzar', action='store_true')
    a = ap.parse_args()
    asyncio.run(main(a.lang, a.forzar))
