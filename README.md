# Watermark Detector

Detección y eliminación de marcas de agua en texto, código fuente, PDF y
Word — en tiempo real, sin base de datos y sin cuentas de usuario. Toda
la aplicación es de acceso libre: no hace falta iniciar sesión para usar
ninguna funcionalidad.

## Características

- **Sin cuentas ni login**: no hay registro, contraseñas ni sesiones
  autenticadas. Todas las páginas y la API son públicas.
- **Detección de marcas invisibles**: espacios de ancho cero (`U+200B`),
  BOM (`U+FEFF`), marcas bidireccionales, caracteres "tag" Unicode usados
  para esteganografía, y espacios Unicode sospechosos — todos localizados
  con su posición exacta (línea/columna).
- **Detección configurable**: palabras/frases clave, coincidencia exacta o
  expresión regular, con o sin distinción de mayúsculas.
- **Soporta**: `.txt`, `.md`, código fuente (`.py`, `.js`, `.java`, `.cpp`,
  `.go`, `.rs`, `.php`, etc.), `.pdf` (pdfplumber / PyPDF2) y `.docx`
  (python-docx).
- **Eliminación segura**: elimina solo los caracteres exactos marcados,
  preservando indentación, saltos de línea y sintaxis. Vista previa de
  diferencias antes/después.
- **Modo batch**: hasta 20 archivos / 50 MB, con progreso en vivo y
  descarga en ZIP.
- **Probabilidad de texto generado por IA** *(informativo, no concluyente)*:
  ver [más abajo](#indicador-de-probabilidad-de-texto-generado-por-ia).
- **Humanización de texto** *(opcional, desactivada por defecto)*: ver
  [más abajo](#humanización-de-texto-opcional).
- **Sin base de datos**: no hay usuarios ni sesiones autenticadas; el
  historial que ves en `/dashboard` se guarda en memoria del proceso,
  asociado a una cookie anónima de navegador (no a una cuenta). Todo el
  procesamiento de archivos ocurre en memoria (`io.BytesIO`), nunca en
  disco.
- Rate limiting simple (10 peticiones/min por IP), CORS, health check en
  `/health`, documentación automática en `/docs`.

## Ejecutar en local

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env            # ajusta valores si hace falta

uvicorn app.main:app --reload --port 8000
```

Abre `http://localhost:8000`.

## Ejecutar con Docker

```bash
docker build -t watermark-detector .
docker run -p 8000:8000 --env-file .env watermark-detector
```

## Pruebas

```bash
pip install -r requirements.txt
pytest tests/ -v
```

## Deploy en Render

El repo incluye `render.yaml` y `Dockerfile` listos para usar:

1. Sube el repo a GitHub.
2. En Render, "New +" → "Blueprint" → selecciona el repo (usa `render.yaml`).
3. Render usará el `Dockerfile` automáticamente.
4. El health check apunta a `/health`.

El puerto se toma de la variable de entorno `PORT` que Render inyecta en
tiempo de ejecución.

## Indicador de probabilidad de texto generado por IA

`/api/detect/text` y `/api/detect/file` (y el batch) devuelven, junto a
los hallazgos de marcas de agua, un campo `ai_score` con:

- `score`: un porcentaje 0-100.
- `signals`: la lista de señales de estilo que lo justifican (varianza de
  longitud de oraciones, diversidad léxica, conectores típicos de IA como
  "en resumen" o "cabe destacar", uniformidad de puntuación).
- `disclaimer`: recuerda que es una estimación.

**Es una heurística estadística sobre el estilo del texto, no un modelo de
machine learning entrenado ni una herramienta forense.** Puede tener falsos
positivos y falsos negativos, especialmente en textos cortos. En la UI de
`/process` se muestra como una tarjeta aparte con el aviso "Estimación
heurística, no concluyente" para que no se confunda con un veredicto. La
lógica vive en [`app/ai_score.py`](app/ai_score.py) y la lista de
conectores es configurable. **No es, ni pretende ser, una herramienta de
evasión de detectores** — solo informa, nunca modifica el texto analizado.

## Humanización de texto (opcional)

`/process` incluye un interruptor **desactivado por defecto**, "Mostrar
versión humanizada", que llama a `POST /api/humanize` para reescribir el
texto analizado con un estilo más natural y variado: sustitución de
algunas palabras por sinónimos, inserción de conectores/muletillas
naturales, combinación o división de oraciones cortas/largas, y —de forma
muy conservadora— algún cambio puntual de voz pasiva a activa cuando es
gramaticalmente seguro.

Límites por diseño (ver [`app/humanize.py`](app/humanize.py)):

- **No es una herramienta para evadir detectores de IA ni de marcas de
  agua.** Su único objetivo es mejorar estilo/legibilidad para usos
  legítimos (corrección de estilo, adaptación de tono, fluidez).
- Conserva el significado, los datos y el número de párrafos originales,
  y mantiene la longitud dentro de un ±10% aproximado.
- Es determinista: el mismo texto con la misma intensidad siempre produce
  el mismo resultado.
- La UI siempre muestra el texto original junto al humanizado (nunca lo
  reemplaza) y la lista de cambios aplicados, con un badge "humanizado"
  visible. Si editas el texto original, el interruptor se desactiva y la
  versión humanizada se limpia automáticamente para evitar
  inconsistencias.
- Intensidad configurable (`low` / `medium` / `high`): a mayor intensidad,
  más sustituciones y reestructuración, siempre dentro de los límites
  anteriores.

## Notas importantes

- **Sin base de datos ni cuentas**: reiniciar el servidor borra todo el
  historial de sesión — es intencional (modo desarrollo/demo).
- En producción, define `CORS_ORIGINS` según corresponda.

## Estructura del proyecto

```
app/
  main.py           FastAPI: páginas públicas, detección, batch, IA-score, humanización
  session.py          Cookie de sesión anónima (sin cuentas) para el historial en memoria
  detector.py         Motor de detección (Unicode invisible + keywords/regex)
  cleaner.py           Eliminación de marcas + diff HTML antes/después
  extractors.py        Extracción de texto: txt/code, PDF, DOCX
  ai_score.py           Indicador heurístico de "probabilidad de texto generado por IA"
  humanize.py            Humanización de texto opcional (desactivada por defecto)
  models.py               Esquemas Pydantic
  rate_limit.py            Middleware de rate limiting en memoria
  templates/                Jinja2 + Bootstrap 5 (index, dashboard, process, batch)
  static/css/style.css       Tema oscuro personalizado
  static/js/                  Lógica de front (análisis individual, batch)
tests/
  test_detector.py     Pruebas unitarias (detección y limpieza)
  test_ai_score.py       Pruebas del indicador heurístico de IA
  test_humanize.py         Pruebas de la humanización de texto
requirements.txt
Dockerfile
render.yaml
.env.example
```
