"""Servidor local para compilar los objetivos de realidad aumentada (.mind) de MindAR.

El compilador de MindAR corre en el navegador; este servidor sirve docs/ y recibe el resultado:
  1. python tools/servidor_ar.py            (puerto 8792)
  2. abrir http://localhost:8792/_compilar.html  → compila los geositios de docs/ar/objetivos.json
     y guarda docs/ar/g<N>.mind con un POST a /guardar?archivo=ar/g<N>.mind
Solo acepta escribir dentro de docs/ar/ y archivos .mind.
"""
import http.server, sys
from pathlib import Path
from urllib.parse import urlparse, parse_qs

DOCS = Path(__file__).resolve().parent.parent / 'docs'
PAGINA = Path(__file__).resolve().parent / 'compilar_ar.html'
PROBAR = Path(__file__).resolve().parent / 'probar_ar.html'
PRUEBA = Path(__file__).resolve().parent / '_ra3d' / 'prueba'
SIMULADOR = """<script>
window.requestAnimationFrame = cb => setTimeout(() => cb(performance.now()), 33);   // la pestaña de prueba puede estar oculta
navigator.mediaDevices.getUserMedia = async () => {
  const q = new URLSearchParams(location.search), img = new Image();
  img.src = q.get('img') || 'ar/g1_1_obj.jpg'; await img.decode();
  const cv = Object.assign(document.createElement('canvas'), { width: 720, height: 1280 }), g = cv.getContext('2d');
  const zoom = +(q.get('zoom') || 1);
  setInterval(() => {   // foto a pantalla completa con un leve temblor de mano
    const s = Math.max(cv.width / img.width, cv.height / img.height) * zoom, t = performance.now() / 700;
    const w = img.width * s, h = img.height * s;
    g.fillStyle = '#555'; g.fillRect(0, 0, cv.width, cv.height);
    g.drawImage(img, (cv.width - w) / 2 + 4 * Math.sin(t), (cv.height - h) / 2 + 3 * Math.cos(t * 1.3), w, h);
  }, 33);
  return cv.captureStream(30);
};
</script>
"""


class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=str(DOCS), **k)

    def do_GET(self):
        ruta = urlparse(self.path).path
        # prueba de reconocimiento: página + imágenes de tools/_ra3d/prueba (ver tools/probar_ar.py)
        if ruta.startswith('/_prueba/'):
            f = (PRUEBA / ruta[len('/_prueba/'):]).resolve()
            if PRUEBA.resolve() not in f.parents or not f.is_file():
                self.send_error(404); return
            cuerpo = f.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', {'.json': 'application/json', '.jpg': 'image/jpeg'}.get(f.suffix, 'application/octet-stream'))
            self.send_header('Content-Length', str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)
            return
        if ruta == '/_ra_simulada.html':
            # ar.html real con la cámara reemplazada por un video hecho de una foto (?img=ar/g1_5_obj.jpg)
            # para ver la RA y sus carteles sin estar frente a la roca
            cuerpo = (DOCS / 'ar.html').read_text(encoding='utf-8').replace('<script src="i18n.js"></script>', SIMULADOR + '<script src="i18n.js"></script>').encode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)
            return
        if ruta in ('/_compilar.html', '/_probar.html'):
            cuerpo = (PAGINA if ruta == '/_compilar.html' else PROBAR).read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)
            return
        super().do_GET()

    def do_POST(self):
        u = urlparse(self.path)
        archivo = parse_qs(u.query).get('archivo', [''])[0]
        destino = (DOCS / archivo).resolve()
        if u.path != '/guardar' or not archivo.endswith('.mind') or (DOCS / 'ar').resolve() not in destino.parents:
            self.send_error(400, 'destino no permitido')
            return
        datos = self.rfile.read(int(self.headers.get('Content-Length', 0)))
        destino.write_bytes(datos)
        print(f'guardado {archivo} ({len(datos) // 1024} KB)', flush=True)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'ok')


if __name__ == '__main__':
    puerto = int(sys.argv[1]) if len(sys.argv) > 1 else 8792
    print(f'http://localhost:{puerto}/_compilar.html', flush=True)
    http.server.ThreadingHTTPServer(('127.0.0.1', puerto), H).serve_forever()
