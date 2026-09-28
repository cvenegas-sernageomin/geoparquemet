"""Narración neural (edge-tts, voz chilena) de la introducción y de cada geositio.

Cada párrafo se sintetiza aparte y los MP3 se concatenan (CBR 48 kbps), así se conoce el
segundo en que empieza cada párrafo para resaltarlo en la app.
Uso: python tools/voces.py [--forzar]
"""
import argparse, asyncio, json, re, sys
from pathlib import Path
import edge_tts

RAIZ = Path(__file__).resolve().parent.parent
DATOS = RAIZ / 'docs' / 'data' / 'tour.json'
AUDIO = RAIZ / 'docs' / 'audio'
BYTES_S = 48000 / 8
VOZ = 'es-CL-CatalinaNeural'

REEMPLAZOS = [
    (r'\[\[[^|\]]+\|([^\]]+)\]\]', r'\1'),
    (r'\b([Gg])eositio', r'\1eo sitio'),          # "geositio" suena "geosicio"
    (r'\b([Gg])eo-?[Rr]uta', r'\1eo ruta'),
    (r'\bNo\.\s*(\d)', r'número \1'),
    (r'(\d)\s*cm\b', r'\1 centímetros'),
    (r'’60', 'sesenta'),
    (r'\bPío Nono\b', 'Pío Nono'),
]


def guion(t):
    for a, b in REEMPLAZOS:
        t = re.sub(a, b, t)
    return re.sub(r'\s+', ' ', t).strip()


async def sintetizar(texto, destino):
    com = edge_tts.Communicate(texto, VOZ, rate='-5%')
    datos = bytearray()
    async for trozo in com.stream():
        if trozo['type'] == 'audio':
            datos += trozo['data']
    return bytes(datos)


async def pista(nombre, parrafos, forzar):
    dst = AUDIO / f'{nombre}.mp3'
    meta = AUDIO / f'{nombre}.json'
    if dst.exists() and meta.exists() and not forzar:
        return json.loads(meta.read_text(encoding='utf-8'))
    total = bytearray()
    marcas = []
    for p in parrafos:
        marcas.append(round(len(total) / BYTES_S, 2))
        for intento in range(4):
            try:
                total += await sintetizar(guion(p), dst)
                break
            except Exception as ex:
                print('  reintento', nombre, ex)
                await asyncio.sleep(3 * (intento + 1))
    dst.write_bytes(bytes(total))
    info = {'src': f'audio/{nombre}.mp3', 'dur': round(len(total) / BYTES_S, 1), 'marcas': marcas}
    meta.write_text(json.dumps(info), encoding='utf-8')
    print(nombre, info['dur'], 's')
    return info


async def main(forzar):
    AUDIO.mkdir(exist_ok=True)
    tour = json.loads(DATOS.read_text(encoding='utf-8'))
    tour['intro_audio'] = await pista('intro', ['GeoParquemet. Geo-Ruta 1: Pío Nono, Tupahue.'] + tour['intro'] + [tour['aviso']], forzar)
    for s in tour['sitios']:
        pars = [f"Geositio {s['n']}. {s['titulo']}."] + s['texto'] + s['texto_web']
        s['audio'] = await pista(f"g{s['n']}", pars, forzar)
    DATOS.write_text(json.dumps(tour, ensure_ascii=False, indent=1), encoding='utf-8')


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser()
    ap.add_argument('--forzar', action='store_true')
    asyncio.run(main(ap.parse_args().forzar))
