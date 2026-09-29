"""Audio corto de cada cartel de la RA (título + explicación para niños), con las mismas voces de la narración.

Lee docs/ar/carteles.json y genera docs/ar/audio/<lang>/g<N>_<id>.mp3 (es, en, pt).
Uso: python tools/voces_carteles.py [--forzar]
"""
import asyncio, json, re, sys
from voces import VOZ, guion, sintetizar, RAIZ

CARTELES = RAIZ / 'docs' / 'ar' / 'carteles.json'
SALIDA = RAIZ / 'docs' / 'ar' / 'audio'
# los títulos usan signos que la voz lee mal
DECIR = {'es': [(r'\s*\+\s*', ' más '), (r'\s*=\s*', ', forman ')],
         'en': [(r'\s*\+\s*', ' plus '), (r'\s*=\s*', ' make ')],
         'pt': [(r'\s*\+\s*', ' mais '), (r'\s*=\s*', ' formam ')]}


def texto(c, lang):
    t = c['titulo'][lang]
    for a, b in DECIR[lang]:
        t = re.sub(a, b, t)
    t = t.replace(':', '.')
    return guion(f"{t}. {c['texto'][lang]}", lang)


async def main(forzar):
    datos = json.loads(CARTELES.read_text(encoding='utf-8'))
    for n, lista in datos.items():
        for lang in VOZ:
            carpeta = SALIDA / lang
            carpeta.mkdir(parents=True, exist_ok=True)
            for c in lista:
                dst = carpeta / f"g{n}_{c['id']}.mp3"
                if dst.exists() and not forzar:
                    continue
                for intento in range(4):
                    try:
                        dst.write_bytes(await sintetizar(texto(c, lang), lang)); break
                    except Exception as ex:
                        print('  reintento', dst.name, ex); await asyncio.sleep(3 * (intento + 1))
                print(lang, dst.name, dst.stat().st_size // 1024, 'KB', '·', texto(c, lang)[:70])


if __name__ == '__main__':
    asyncio.run(main('--forzar' in sys.argv))
