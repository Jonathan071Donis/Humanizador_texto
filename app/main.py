from __future__ import annotations

import io
import logging
import os
import time
import zipfile
from typing import List, Optional

from dotenv import load_dotenv

load_dotenv()

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import ai_score as ai_score_engine
from . import session
from .cleaner import clean_and_diff
from .detector import run_detection
from .extractors import ExtractionError, extract_content
from .humanize import humanize_text_with_changes
from .models import (
    AIScoreResult,
    BatchFileResult,
    CleanRequest,
    CleanResult,
    DetectionConfig,
    DetectionResult,
    HumanizeRequest,
    HumanizeResponse,
    TextProcessRequest,
)
from .rate_limit import RateLimitMiddleware

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("watermark-detector")

APP_NAME = os.getenv("APP_NAME", "Watermark Detector")
MAX_BATCH_FILES = int(os.getenv("MAX_BATCH_FILES", "20"))
MAX_BATCH_TOTAL_MB = int(os.getenv("MAX_BATCH_TOTAL_MB", "50"))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = FastAPI(
    title=APP_NAME,
    description="Detección y eliminación de marcas de agua en texto, código, PDF y Word — en tiempo real, sin base de datos ni cuentas de usuario.",
    version="1.0.0",
)

app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _record_history(session_id: str, filename: str, findings: int) -> None:
    session.record_history(session_id, filename, findings)
    logger.info("session=%s processed file=%s findings=%s", session_id, filename, findings)


def _build_detection_result(filename: str, text: str, config: DetectionConfig, file_type: Optional[str] = None) -> DetectionResult:
    invisible, keywords = run_detection(text, config)
    score = ai_score_engine.score_text(text)
    return DetectionResult(
        filename=filename,
        file_type=file_type or (filename.rsplit(".", 1)[-1] if "." in filename else "text"),
        original_length=len(text),
        invisible_chars=invisible,
        keyword_matches=keywords,
        total_findings=len(invisible) + len(keywords),
        clean=(len(invisible) + len(keywords) == 0),
        extracted_text=text,
        ai_score=AIScoreResult(score=score.score, signals=score.signals, disclaimer=score.disclaimer),
    )


# ---------------------------------------------------------------------------
# Public pages (no login required - the whole app is public)
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "app_name": APP_NAME})


@app.get("/health")
async def health():
    return {"status": "ok", "time": time.time(), "sessions_in_memory": len(session.SESSION_HISTORY)}


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, session_id: str = Depends(session.get_or_create_session_id)):
    history = session.get_history(session_id)
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "app_name": APP_NAME, "history": list(reversed(history))[:25]},
    )


@app.get("/process", response_class=HTMLResponse)
async def process_page(request: Request):
    return templates.TemplateResponse("process.html", {"request": request, "app_name": APP_NAME})


@app.get("/batch", response_class=HTMLResponse)
async def batch_page(request: Request):
    return templates.TemplateResponse(
        "batch.html",
        {"request": request, "app_name": APP_NAME, "max_files": MAX_BATCH_FILES, "max_mb": MAX_BATCH_TOTAL_MB},
    )


# ---------------------------------------------------------------------------
# Detection / cleaning API - all public, no login required
# ---------------------------------------------------------------------------

@app.post("/api/detect/text", response_model=DetectionResult)
async def detect_text(
    payload: TextProcessRequest,
    background_tasks: BackgroundTasks,
    session_id: str = Depends(session.get_or_create_session_id),
):
    result = _build_detection_result(payload.filename, payload.content, payload.config)
    background_tasks.add_task(_record_history, session_id, payload.filename, result.total_findings)
    return result


@app.post("/api/detect/file", response_model=DetectionResult)
async def detect_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    keywords: str = Form(""),
    use_regex: bool = Form(False),
    case_sensitive: bool = Form(False),
    detect_invisible_unicode: bool = Form(True),
    session_id: str = Depends(session.get_or_create_session_id),
):
    data = await file.read()
    config = DetectionConfig(
        keywords=[k for k in keywords.split(",") if k.strip()],
        use_regex=use_regex,
        case_sensitive=case_sensitive,
        detect_invisible_unicode=detect_invisible_unicode,
    )
    try:
        text, file_type = extract_content(file.filename, data)
    except ExtractionError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    result = _build_detection_result(file.filename, text, config, file_type=file_type)
    background_tasks.add_task(_record_history, session_id, file.filename, result.total_findings)
    return result


@app.post("/api/clean", response_model=CleanResult)
async def clean(payload: CleanRequest):
    return clean_and_diff(
        payload.content,
        payload.filename,
        payload.config,
        payload.remove_invisible_ids,
        payload.remove_keyword_ids,
    )


@app.post("/api/clean/download")
async def clean_download(payload: CleanRequest):
    result = clean_and_diff(
        payload.content,
        payload.filename,
        payload.config,
        payload.remove_invisible_ids,
        payload.remove_keyword_ids,
    )
    buf = io.BytesIO(result.cleaned_content.encode("utf-8"))
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="clean_{payload.filename}"'},
    )


# ---------------------------------------------------------------------------
# "Probabilidad de texto generado por IA" - heuristic, informational only
# ---------------------------------------------------------------------------

@app.post("/api/humanize", response_model=HumanizeResponse)
async def humanize(payload: HumanizeRequest):
    if not payload.text.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El texto no puede estar vacío")
    humanized, changes = humanize_text_with_changes(payload.text, payload.intensity)
    return HumanizeResponse(original=payload.text, humanized=humanized, changes=changes)


# ---------------------------------------------------------------------------
# Batch API - public, no login required
# ---------------------------------------------------------------------------

@app.post("/api/batch/detect")
async def batch_detect(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    keywords: str = Form(""),
    use_regex: bool = Form(False),
    case_sensitive: bool = Form(False),
    detect_invisible_unicode: bool = Form(True),
    session_id: str = Depends(session.get_or_create_session_id),
):
    if len(files) > MAX_BATCH_FILES:
        raise HTTPException(status_code=400, detail=f"Máximo {MAX_BATCH_FILES} archivos por lote")

    config = DetectionConfig(
        keywords=[k for k in keywords.split(",") if k.strip()],
        use_regex=use_regex,
        case_sensitive=case_sensitive,
        detect_invisible_unicode=detect_invisible_unicode,
    )

    total_bytes = 0
    results: List[BatchFileResult] = []

    for f in files:
        data = await f.read()
        total_bytes += len(data)
        if total_bytes > MAX_BATCH_TOTAL_MB * 1024 * 1024:
            results.append(BatchFileResult(filename=f.filename, status="error", message="Límite de tamaño de lote excedido"))
            continue
        try:
            text, file_type = extract_content(f.filename, data)
            detection = _build_detection_result(f.filename, text, config, file_type=file_type)
            results.append(BatchFileResult(filename=f.filename, status="ok", detection=detection))
            background_tasks.add_task(_record_history, session_id, f.filename, detection.total_findings)
        except ExtractionError as e:
            results.append(BatchFileResult(filename=f.filename, status="error", message=str(e)))
        except Exception as e:
            logger.exception("batch detect failed for %s", f.filename)
            results.append(BatchFileResult(filename=f.filename, status="error", message=f"Error inesperado: {e}"))

    return {"results": results}


@app.post("/api/batch/clean-zip")
async def batch_clean_zip(
    files: List[UploadFile] = File(...),
    keywords: str = Form(""),
    use_regex: bool = Form(False),
    case_sensitive: bool = Form(False),
    detect_invisible_unicode: bool = Form(True),
):
    if len(files) > MAX_BATCH_FILES:
        raise HTTPException(status_code=400, detail=f"Máximo {MAX_BATCH_FILES} archivos por lote")

    config = DetectionConfig(
        keywords=[k for k in keywords.split(",") if k.strip()],
        use_regex=use_regex,
        case_sensitive=case_sensitive,
        detect_invisible_unicode=detect_invisible_unicode,
    )

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            data = await f.read()
            try:
                text, _ = extract_content(f.filename, data)
            except ExtractionError:
                continue
            result = clean_and_diff(text, f.filename, config)
            zf.writestr(f"clean_{f.filename}", result.cleaned_content)

    zip_buffer.seek(0)
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="cleaned_files.zip"'},
    )


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=os.getenv("ENV") == "development")
