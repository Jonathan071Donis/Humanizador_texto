# Watermark Detector

Detección y eliminación de marcas de agua en texto, código fuente, PDF y
Word — en tiempo real, sin base de datos.

## Características

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
- **Sin base de datos**: usuarios y sesiones viven en memoria del proceso
  (JWT sin estado); todo el procesamiento de archivos ocurre en memoria
  (`io.BytesIO`), nunca en disco.
- Rate limiting simple (10 peticiones/min por IP), CORS, health check en
  `/health`, documentación automática en `/docs`.

## Ejecutar en local

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env            # ajusta SECRET_KEY, etc.

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
3. Render generará `SECRET_KEY` automáticamente y usará el `Dockerfile`.
4. El health check apunta a `/health`.

El puerto se toma de la variable de entorno `PORT` que Render inyecta en
tiempo de ejecución.

## Notas importantes

- **Sin base de datos**: reiniciar el servidor borra todas las cuentas y el
  historial de sesión — es intencional (modo desarrollo/demo). Si necesitas
  persistencia ligera entre reinicios, define `USERS_JSON_FILE=users.json`
  en `.env` para guardar los usuarios (no las sesiones) en un archivo JSON.
- En producción, define `SECRET_KEY` a un valor aleatorio largo y
  `COOKIE_SECURE=true` (requiere HTTPS).

## Estructura del proyecto

```
app/
  main.py           FastAPI: rutas públicas, auth, protegidas, batch
  auth.py           Usuarios en memoria + JWT + rate-limit-friendly deps
  detector.py        Motor de detección (Unicode invisible + keywords/regex)
  cleaner.py          Eliminación de marcas + diff HTML antes/después
  extractors.py       Extracción de texto: txt/code, PDF, DOCX
  models.py           Esquemas Pydantic
  rate_limit.py       Middleware de rate limiting en memoria
  templates/           Jinja2 + Bootstrap 5 (index, login, register, dashboard, process, batch)
  static/css/style.css Tema oscuro personalizado
  static/js/           Lógica de front (auth, análisis individual, batch)
tests/
  test_detector.py     Pruebas unitarias (detección y limpieza)
requirements.txt
Dockerfile
render.yaml
.env.example
```
