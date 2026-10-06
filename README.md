# GeoParquemet · Geo-Ruta 1 Pío Nono – Tupahue

PWA de geotour con GPS por los 8 geositios de la Geo-Ruta 1 del Parque Metropolitano de Santiago (proyecto GEOPARQUEMET, Unidad de Geopatrimonio, Sernageomin).

App desarrollada por Carlos Venegas.

- **En terreno:** guía con GPS y brújula hacia el siguiente geositio. Al llegar (a 35 m o menos) sella el pasaporte, vibra y reproduce la narración.
- **Virtual:** fichas con fotos original/interpretada en comparador deslizante, narración con resaltado del párrafo, modelos 3D (Sketchfab), videos, Street View y glosario (41 términos).
- **Mapa:** imagen satelital o de calles, trazado de la Geo-Ruta 1 y capa de unidades geológicas.
- **Sin señal:** el botón "Descargar para usar sin señal" guarda fotos, narraciones y teselas del recorrido (z14–18).

## Datos

`tools/construir.py` arma `docs/data/*.json` y `docs/img/*.webp` a partir de `fuentes/`:

- `earth_tour.json`: textos del geotour de Google Earth, más la posición de Street View de cada geositio.
- `geositio-N.html` y `terms/`: sitio geoparquemet.netlify.app (textos interpretativos, pares de fotos, 3D, videos y glosario).
- `*.geojson`: capas de ArcGIS Online de Geopatrimonio (Geo_Sitios_ParqueMet, Georuta1_v2, c04 Formación Abanico, c05 Rocas intrusivas).

`tools/voces.py` genera la narración con edge-tts (es-CL-CatalinaNeural) en `docs/audio/`.

Para probar el GPS en local, agrega `?sim=lat,lon` a la URL. Desde la consola también se puede llamar `__simular(lat, lon)`.

## Licencia y cita

El código, la realidad aumentada, las traducciones y el cuestionario son © 2026 Carlos Venegas Benavides y Felipe Fuentes, bajo licencia [CC BY-NC 4.0](LICENSE): se pueden compartir y adaptar citando a los autores, sin fines comerciales. El contenido geológico (textos, fotografías, videos, modelos 3D y capas) es del proyecto GEOPARQUEMET, Unidad de Geopatrimonio, Sernageomin, y conserva sus derechos. El detalle y la forma de citar están en [LICENCIA.md](LICENCIA.md) y [CITATION.cff](CITATION.cff).
