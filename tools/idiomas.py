"""Arma docs/data/lang_en.json y lang_pt.json a partir de tools/_trad/*.json
y de las marcas de audio de docs/audio/<lang>/*.json (las genera tools/voces.py --lang en|pt).
"""
import json, re, sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
TRAD = RAIZ / 'tools' / '_trad'
DATA = RAIZ / 'docs' / 'data'
AUDIO = RAIZ / 'docs' / 'audio'
LANGS = ('en', 'pt')


def audio_meta(lang, nombre):
    p = AUDIO / lang / f'{nombre}.json'
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else None


def construir(lang):
    tour_es = json.loads((DATA / 'tour.json').read_text(encoding='utf-8'))
    glos_es = json.loads((DATA / 'glosario.json').read_text(encoding='utf-8'))
    t = json.loads((TRAD / f'tour_{lang}.json').read_text(encoding='utf-8'))
    g = json.loads((TRAD / f'glosario_{lang}.json').read_text(encoding='utf-8'))
    x = json.loads((TRAD / f'extra_{lang}.json').read_text(encoding='utf-8'))
    # controles: mismos párrafos que en español (las marcas de audio dependen de eso) y mismos términos
    for s in tour_es['sitios']:
        tr = t['sitios'][str(s['n'])]
        assert len(tr['texto']) == len(s['texto']), (lang, s['n'], 'texto')
        assert len(tr['texto_web']) == len(s['texto_web']), (lang, s['n'], 'texto_web')
    faltan = set(glos_es) - set(g)
    assert not faltan, (lang, faltan)
    for slug, v in g.items():
        for p in v['d']:
            for ref in re.findall(r'\[\[([^|\]]+)\|', p):
                assert ref in glos_es, (lang, slug, ref)
    out = {'intro': t['intro'], 'aviso': t['aviso'], 'ruta': t['ruta'], 'sitios': {}, 'glosario': g,
           'quiz': x['quiz'], 'geologia': x['geologia'], 'intro_audio': audio_meta(lang, 'intro')}
    for n, s in t['sitios'].items():
        s = dict(s)
        s['audio'] = audio_meta(lang, f'g{n}')
        out['sitios'][n] = s
    (DATA / f'lang_{lang}.json').write_text(json.dumps(out, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    con_audio = sum(1 for s in out['sitios'].values() if s['audio'])
    print(lang, 'ok ·', len(out['sitios']), 'geositios ·', len(g), 'términos · audio', con_audio, '/', len(out['sitios']))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    for l in (sys.argv[1:] or LANGS):
        construir(l)
