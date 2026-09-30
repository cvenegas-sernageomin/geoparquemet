"""Lectura del modelo 3D del Geositio 1 (Pix4D + Leapfrog) y proyección de la interpretación sobre las fotos reales.

Material (no versionado, ~3 GB): 'Fotos y modelos/GST1_3D/GST1_3D/'
  Pix4D/Caida1_PM1/...                 malla FBX binaria con la textura embebida + cámaras calibradas
  Leapfrog/LF/Leapfrog/Geositio1.aproj trazas (Polyline3DBlock) y superficies (UserMeshBlock) de las fracturas
  Fotos_modelo/DSC_*.JPG               las fotos con que se armó el modelo (2019)
La malla de Leapfrog es la misma de Pix4D y está en las mismas coordenadas, por eso las trazas caen
exactamente sobre cada foto al proyectarlas con su cámara calibrada.
Ojo: sin puntos de control y con GPS de cámara errático, el modelo tiene escala (~10x) y orientación
arbitrarias: sirve para la RA, no para medir rumbos o manteos.
"""
import glob, io, json, pickle, re, sqlite3, struct, zlib
from pathlib import Path
import cv2
import numpy as np
from PIL import Image

RAIZ = Path(__file__).resolve().parent.parent
MATERIAL = RAIZ / 'Fotos y modelos' / 'GST1_3D' / 'GST1_3D'
PIX4D = MATERIAL / 'Pix4D' / 'Caida1_PM1'
FBX = PIX4D / '2_densification' / '3d_mesh' / 'Caida1_PM1_simplified_3d_mesh.fbx'
CAMARAS = PIX4D / '1_initial' / 'params' / 'Caida1_PM1_calibrated_camera_parameters.txt'
APROJ = MATERIAL / 'Leapfrog' / 'LF' / 'Leapfrog' / 'Geositio1.aproj'
FOTOS = MATERIAL / 'Fotos_modelo'
CACHE = RAIZ / 'tools' / '_ra3d'          # ignorado por git: malla y textura ya extraídas


# ---------- FBX binario (solo lo que exporta Pix4D: una malla de triángulos con UV) ----------
def _fbx_arbol(d):
    big = struct.unpack('<I', d[23:27])[0] >= 7500
    def prop(p):
        t = chr(d[p]); p += 1
        fmt = {'Y': '<h', 'C': '<?', 'I': '<i', 'F': '<f', 'D': '<d', 'L': '<q'}
        if t in fmt:
            s = struct.calcsize(fmt[t]); return struct.unpack(fmt[t], d[p:p+s])[0], p + s
        if t in 'fdilb':
            n, enc, clen = struct.unpack('<III', d[p:p+12]); p += 12
            raw = d[p:p+clen]; p += clen
            if enc: raw = zlib.decompress(raw)
            return np.frombuffer(raw, {'f': '<f4', 'd': '<f8', 'i': '<i4', 'l': '<i8', 'b': '?'}[t], n), p
        if t in 'SR':
            n = struct.unpack('<I', d[p:p+4])[0]; p += 4
            return d[p:p+n], p + n
        raise ValueError(f'tipo FBX {t!r}')
    def nodo(p):
        if big: end, npr, _ = struct.unpack('<QQQ', d[p:p+24]); p += 24
        else: end, npr, _ = struct.unpack('<III', d[p:p+12]); p += 12
        nl = d[p]; p += 1; nombre = d[p:p+nl].decode(); p += nl
        if end == 0: return None, p
        props = []
        for _ in range(npr):
            v, p = prop(p); props.append(v)
        hijos = []
        while p < end:
            h, p = nodo(p)
            if h is None: break
            hijos.append(h)
        return (nombre, props, hijos), end
    p, out = 27, []
    while p < len(d) - 200:
        n, p = nodo(p)
        if n is None: break
        out.append(n)
    return out


def _buscar(nodos, nombre, res):
    for n in nodos:
        if n[0] == nombre: res.append(n)
        _buscar(n[2], nombre, res)
    return res


def malla():
    """Vértices, triángulos, UV por esquina y textura (8192²) de la malla del afloramiento. Se cachea."""
    CACHE.mkdir(exist_ok=True)
    npz, tex = CACHE / 'malla.npz', CACHE / 'textura.jpg'
    if not npz.exists():
        d = FBX.read_bytes()
        g = [x for x in _buscar(_fbx_arbol(d), 'Geometry', []) if any(k[0] == 'Vertices' for k in x[2])][0]
        k = {h[0]: h for h in g[2]}
        V = k['Vertices'][1][0].reshape(-1, 3)
        idx = k['PolygonVertexIndex'][1][0].copy(); idx[idx < 0] = ~idx[idx < 0]
        uvk = {h[0]: h for h in [h for h in g[2] if h[0] == 'LayerElementUV'][0][2]}
        UV = uvk['UV'][1][0].reshape(-1, 2)
        UVF = uvk['UVIndex'][1][0].reshape(-1, 3) if 'UVIndex' in uvk else np.arange(len(UV)).reshape(-1, 3)
        np.savez_compressed(npz, V=V, F=idx.reshape(-1, 3), UV=UV, UVF=UVF)
        i = d.find(b'JFIF') - 6                       # la textura va embebida como JPEG
        Image.open(io.BytesIO(d[i:])).save(tex, quality=92)
    m = np.load(npz)
    return m['V'], m['F'], m['UV'], m['UVF'], tex


# ---------- cámaras Pix4D ----------
def camaras():
    L = [l.split() for l in open(CAMARAS) if l.strip()]
    i = next(k for k, l in enumerate(L) if l[0].upper().endswith('.JPG'))
    cams = {}
    while i < len(L):
        n, w, h = L[i][0], int(L[i][1]), int(L[i][2])
        cams[n] = dict(w=w, h=h, K=np.array(L[i+1:i+4], float), rad=np.array(L[i+4], float),
                       tan=np.array(L[i+5], float), t=np.array(L[i+6], float), R=np.array(L[i+7:i+10], float))
        i += 10
    return cams


def proyectar(c, X, esc=1.0):
    """Modelo del archivo: m = K [R | -Rt] X, con distorsión radial y tangencial. Devuelve u, v (px) y profundidad."""
    Xc = (np.asarray(X) - c['t']) @ c['R'].T
    z = Xc[:, 2]
    x, y = Xc[:, 0] / z, Xc[:, 1] / z
    r2 = x*x + y*y; k1, k2, k3 = c['rad']; t1, t2 = c['tan']
    f = 1 + k1*r2 + k2*r2**2 + k3*r2**3
    xd = x*f + 2*t1*x*y + t2*(r2 + 2*x*x); yd = y*f + 2*t2*x*y + t1*(r2 + 2*y*y)
    K = c['K']
    return (K[0, 0]*xd + K[0, 2]) * esc, (K[1, 1]*yd + K[1, 2]) * esc, z


# ---------- Leapfrog ----------
class _Stub:
    def __init__(self, *a, **k): pass
    def __setstate__(self, s): self._state = s


class _Unpickler(pickle.Unpickler):
    """Leapfrog guarda pickles de Python 2 con sus propias clases: se reemplazan por objetos vacíos."""
    def find_class(self, mod, name):
        if mod.startswith('numpy') or mod in ('copy_reg', 'copyreg', '__builtin__', 'builtins', 'collections'):
            try: return super().find_class(mod, name)
            except Exception: pass
        return type(name, (_Stub,), {'_cls': f'{mod}.{name}'})
    def persistent_load(self, pid): return pid


def _npy(d):
    """Arreglos .npy incrustados en un .lfdata (las formas traen el sufijo 'L' de Python 2)."""
    out = []
    for m in re.finditer(rb'\x93NUMPY', d):
        f = io.BytesIO(d[m.start():])
        f.read(6); maj = f.read(1)[0]; f.read(1)
        hl = int.from_bytes(f.read(2 if maj == 1 else 4), 'little')
        h = eval(re.sub(r'(\d)L', lambda x: x.group(1), f.read(hl).decode('latin1')))
        dt = np.dtype(h['descr']); n = int(np.prod(h['shape'])) * dt.itemsize
        raw = f.read(n)
        if len(raw) == n: out.append(np.frombuffer(raw, dt).reshape(h['shape'], order='F' if h['fortran_order'] else 'C'))
    return out


def interpretacion():
    """Trazas {nombre: [tramos Nx3]} y superficies {nombre: (V, F)} vigentes del proyecto Leapfrog."""
    bloques = []
    for _, _, d in sqlite3.connect(APROJ).execute('select oid, serial, data from data'):
        f = io.BytesIO(bytes(d))
        try: a = _Unpickler(f, encoding='latin1').load(); b = _Unpickler(f, encoding='latin1').load()
        except Exception: continue
        cl = getattr(a, '_cls', '').split('.')[-1]
        if cl in ('Polyline3DBlock', 'UserMeshBlock') and isinstance(b, dict) and not b.get('_deleted'):
            bb = np.asarray(b.get('_Polyline3DBlock__bbox', b.get('_bounding_box')))
            bloques.append((cl, b['label'], bb, (b.get('_meta') or {}).get('vertices')))
    polis, mallas = [], []
    for p in glob.glob(str(APROJ) + '_data/*/*.lfdata'):
        d = open(p, 'rb').read()
        if b'LF3DPolyline' in d[:120]:
            tramos, cur, i = [], [], 64
            while (j := d.find(b'node', i)) >= 0:
                k = d.find(b'path', i + 1)
                if 0 <= k < j and cur: tramos.append(np.array(cur)); cur = []
                cur.append(struct.unpack('<3d', d[j+4:j+28])); i = j + 28
            if cur: tramos.append(np.array(cur))
            polis.append(tramos)
        elif len(d) < 100000 and b'Mesh3' in d:
            arr = _npy(d)
            F = [a for a in arr if a.dtype.kind == 'i' and a.ndim == 2]
            V = [a for a in arr if a.dtype.kind == 'f' and a.ndim == 2 and a.shape[1] == 3]
            if F and V: mallas.append((V[0], F[0]))
    trazas, sup = {}, {}
    for cl, nombre, bb, nv in bloques:
        if cl == 'Polyline3DBlock':
            c = [t for t in polis if np.allclose(np.vstack(t).min(0), bb[0], atol=.05) and np.allclose(np.vstack(t).max(0), bb[1], atol=.05)]
            if c: trazas[nombre] = c[0]
        else:
            c = [m for m in mallas if len(m[0]) == nv and np.allclose(m[0].min(0), bb[0], atol=.05)]
            if c: sup[nombre] = c[0]
    return trazas, sup


# ---------- rasterizado ----------
def zbuffer(c, V, F, w, h, esc):
    """Profundidad de la roca por píxel (splat denso de vértices, centroides y aristas + mínimo local)."""
    zb = np.full((h, w), np.inf, np.float32)
    for P in (V, V[F].mean(1), (V[F[:, 0]] + V[F[:, 1]]) / 2, (V[F[:, 1]] + V[F[:, 2]]) / 2, (V[F[:, 2]] + V[F[:, 0]]) / 2):
        u, v, z = proyectar(c, P, esc)
        ok = (z > 0) & (u >= 0) & (u < w) & (v >= 0) & (v < h)
        np.minimum.at(zb, (v[ok].astype(int), u[ok].astype(int)), z[ok])
    return cv2.erode(zb, np.ones((3, 3), np.uint8))   # mínimo local 3x3 (sin scipy: su DLL está bloqueado en este PC)


def raster_superficie(c, V, F, w, h, esc):
    """Profundidad de una superficie por píxel (inf donde no hay)."""
    u, v, z = proyectar(c, V, esc); P = np.c_[u, v]
    zs = np.full((h, w), np.inf, np.float32)
    for tri in F:
        p, zz = P[tri], z[tri]
        if (zz <= 0).any(): continue
        x0, y0 = np.floor(p.min(0)).astype(int); x1, y1 = np.ceil(p.max(0)).astype(int)
        x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, w - 1), min(y1, h - 1)
        if x1 < x0 or y1 < y0: continue
        Y, X = np.mgrid[y0:y1+1, x0:x1+1] + .5
        (ax, ay), (bx, by), (cx, cy) = p
        den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(den) < 1e-9: continue
        l1 = ((by - cy) * (X - cx) + (cx - bx) * (Y - cy)) / den
        l2 = ((cy - ay) * (X - cx) + (ax - cx) * (Y - cy)) / den
        l3 = 1 - l1 - l2
        dentro = (l1 >= -1e-6) & (l2 >= -1e-6) & (l3 >= -1e-6)
        zi = np.where(dentro, l1 * zz[0] + l2 * zz[1] + l3 * zz[2], np.inf)
        sub = zs[y0:y1+1, x0:x1+1]; np.minimum(sub, zi, out=sub)
    return zs


def densificar(t, paso):
    out = [t[0]]
    for a, b in zip(t[:-1], t[1:]):
        n = max(1, int(np.linalg.norm(b - a) / paso)); out += [a + (b - a) * k / n for k in range(1, n + 1)]
    return np.array(out)


def foto_derecha(n, c, V, F, UV, UVF, tex):
    """Abre la foto con los píxeles en el marco de Pix4D (w x h de la cámara) y dice cómo girarla para verla derecha.
    Algunos archivos ya vienen girados a vertical sin EXIF: el giro se elige por correlación con la malla proyectada."""
    im = Image.open(FOTOS / n)
    ori = im.getexif().get(274, 1)
    if im.width == c['w']:
        return im.convert('RGB'), {3: 180, 6: 270, 8: 90}.get(ori, 0)
    g = im.convert('L'); g.draft('L', (g.width // 8, g.height // 8))
    esc = 0.1; w, h = int(c['w'] * esc), int(c['h'] * esc)
    L = np.asarray(Image.open(tex).convert('L').resize((2048, 2048)), float)
    uv = UV[UVF[:, 0]]; gv = np.zeros(len(V)); gv[F[:, 0]] = L[((1 - uv[:, 1]) * 2047).astype(int).clip(0, 2047), (uv[:, 0] * 2047).astype(int).clip(0, 2047)]
    u, v, z = proyectar(c, V, esc); ok = (z > 0) & (u >= 0) & (u < w) & (v >= 0) & (v < h)
    ref, cnt = np.zeros((h, w)), np.zeros((h, w))
    np.add.at(ref, (v[ok].astype(int), u[ok].astype(int)), gv[ok]); np.add.at(cnt, (v[ok].astype(int), u[ok].astype(int)), 1)
    msk = cnt > 0; ref[msk] /= cnt[msk]
    cc = {r: np.corrcoef(np.asarray(g.rotate(r, expand=True).resize((w, h)), float)[msk], ref[msk])[0, 1] for r in (90, 270)}
    r = max(cc, key=cc.get)
    return im.convert('RGB').rotate(r, expand=True), 360 - r
