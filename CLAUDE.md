# GeoParquemet — notas para Claude

PWA de geotour GPS por los 8 geositios de la Geo-Ruta 1 Pío Nono–Tupahue (Parquemet), con RA
MindAR. Publicada desde `docs/` en https://cvenegas-sernageomin.github.io/geoparquemet/ (rama `main`).
Ficha en memoria: `proyecto-geoparquemet-tour`. Contenido y licencias: `README.md`.

## Antes de editar
- Se trabajó también en otro PC: `git pull` y comparar la versión con el sitio en vivo.
- Material pesado (Pix4D, Leapfrog, fotos originales) **no está en git** ni en este PC.
- **No cambiar colores** sin validar con los colegas: solo proponer.

## Cada cambio
- Subir `VERSION` (`gpm-vN`) en `docs/sw.js`. `RA` (`gpm-ra-N`) solo al regenerar objetivos de RA.
- `docs/data/*.json` y `docs/img/` se generan: no editarlos a mano.

## Pipeline (en este orden)
1. `tools/construir.py` (fuentes/ → docs/data, docs/img)
2. `tools/voces.py` (después, porque construir reescribe `tour.json` sin audio)
3. `tools/idiomas.py` (traducciones a mano en `tools/_trad/`) → `tools/revisar_traducciones.py`
4. RA: `tools/capas_ar*.py` → `tools/carteles_*.py` → `tools/capas_ar_sol.py` (agrega al G1 los objetivos con sol
   de `RA/GS1/`; si se corre `capas_ar_nuevas.py` hay que volver a correrlo); recompilar `.mind` solo si cambian
   objetivos (`tools/servidor_ar.py` → `/_compilar.html?g=N`, con el SW de localhost desregistrado).
   MindAR solo reconoce con luz parecida a la de las fotos objetivo: el G1 tiene fotos nubladas (1–11) y con sol (12–19).

## Probar
`?sim=lat,lon` en la URL o `__simular(lat, lon)` en consola. RA en `docs/ar.html?g=N`.

## Trampas
- scipy y torch bloqueados por Application Control: usar OpenCV.
- El panel oculto no corre rAF (MindAR arranca recién con screenshot); su caché HTTP sirve JSON viejo.
- Leaflet: fijar la vista antes de agregar capas; los popups quedan bajo la leyenda (z-index 400).
- Comparte origen con otras PWAs de github.io: ver `reference-mismo-origen-dos-pwas-github-pages`.
- `publicar.ps1` es de la creación inicial del repo: para publicar cambios usar la skill `publicar-pwa`.
