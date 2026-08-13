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
    Body,
    Cookie,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import auth
from .cleaner import clean_and_diff
from .detector import run_detection
from .extractors import ExtractionError, extract_content
from .models import (
    BatchFileResult,
    CleanRequest,
    CleanResult,
    DetectionConfig,
    DetectionResult,
    LoginRequest,
    RegisterRequest,
    TextProcessRequest,
    TokenResponse,
)
from .rate_limit import RateLimitMiddleware

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("watermark-detector")

APP_NAME = os.getenv("APP_NAME", "Watermark Detector")
MAX_BATCH_FILES = int(os.getenv("MAX_BATCH_FILES", "20"))
MAX_BATCH_TOTAL_MB = int(os.getenv("MAX_BATCH_TOTAL_MB", "50"))
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = FastAPI(
    title=APP_NAME,
    description="Detecci\u00f3n y eliminaci\u00f3n de marcas de agua en texto, c\u00f3digo, PDF y Word \u2014 en tiempo real, sin base de datos.",
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

def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        max_age=auth.TOKEN_TTL_SECONDS,
    )


def _record_history(username: str, filename: str, findings: int) -> None:
    entry = {"filename": filename, "findings": findings, "ts": time.time()}
    auth.USER_HISTORY.setdefault(username, []).append(entry)
    logger.info("user=%s processed file=%s findings=%s", username, filename, findings)


def _detect_text(filename: str, text: str, config: DetectionConfig) -> DetectionResult:
    invisible, keywords = run_detection(text, config)
    return DetectionResult(
        filename=filename,
        file_type=filename.rsplit(".", 1)[-1] if "." in filename else "text",
        original_length=len(text),
        invisible_chars=invisible,
        keyword_matches=keywords,
        total_findings=len(invisible) + len(keywords),
        clean=(len(invisible) + len(keywords) == 0),
        extracted_text=text,
    )


# ---------------------------------------------------------------------------
# Public pages
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index(request: Request, access_token: Optional[str] = Cookie(default=None)):
    user = auth.get_current_user_optional(access_token)
    return templates.TemplateResponse("index.html", {"request": request, "app_name": APP_NAME, "user": user})


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "app_name": APP_NAME})


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request, "app_name": APP_NAME})


@app.get("/health")
async def health():
    return {"status": "ok", "time": time.time(), "users_in_memory": len(auth.USERS)}


# ---------------------------------------------------------------------------
# Auth API
# ---------------------------------------------------------------------------

@app.post("/api/auth/register", response_model=TokenResponse)
async def register(payload: RegisterRequest, response: Response):
    try:
        auth.create_user(payload.username, payload.password)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    token = auth.create_access_token(payload.username)
    _set_session_cookie(response, token)
    logger.info("new user registered: %s", payload.username)
    return TokenResponse(access_token=token, username=payload.username)


@app.post("/api/auth/login", response_model=TokenResponse)
async def login(payload: LoginRequest, response: Response):
    if not auth.verify_user(payload.username, payload.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = auth.create_access_token(payload.username)
    _set_session_cookie(response, token)
    return TokenResponse(access_token=token, username=payload.username)


@app.post("/api/auth/logout")
async def logout(response: Response):
    response.delete_cookie("access_token")
    return {"detail": "logged out"}


# ---------------------------------------------------------------------------
# Protected pages
# ---------------------------------------------------------------------------

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, user: str = Depends(auth.get_current_user)):
    history = auth.USER_HISTORY.get(user, [])
    prefs = auth.USER_PREFS.get(user, {"favorite_keywords": []})
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "app_name": APP_NAME, "user": user, "history": list(reversed(history))[:25], "prefs": prefs},
    )


@app.get("/process", response_class=HTMLResponse)
async def process_page(request: Request, user: str = Depends(auth.get_current_user)):
    return templates.TemplateResponse("process.html", {"request": request, "app_name": APP_NAME, "user": user})


@app.get("/batch", response_class=HTMLResponse)
async def batch_page(request: Request, user: str = Depends(auth.get_current_user)):
    return templates.TemplateResponse(
        "batch.html",
        {"request": request, "app_name": APP_NAME, "user": user, "max_files": MAX_BATCH_FILES, "max_mb": MAX_BATCH_TOTAL_MB},
    )


# ---------------------------------------------------------------------------
# Detection / cleaning API (protected)
# ---------------------------------------------------------------------------

@app.post("/api/detect/text", response_model=DetectionResult)
async def detect_text(payload: TextProcessRequest, background_tasks: BackgroundTasks, user: str = Depends(auth.get_current_user)):
    result = _detect_text(payload.filename, payload.content, payload.config)
    background_tasks.add_task(_record_history, user, payload.filename, result.total_findings)
    return result


@app.post("/api/detect/file", response_model=DetectionResult)
async def detect_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    keywords: str = Form(""),
    use_regex: bool = Form(False),
    case_sensitive: bool = Form(False),
    detect_invisible_unicode: bool = Form(True),
    user: str = Depends(auth.get_current_user),
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

    invisible, kw_matches = run_detection(text, config)
    result = DetectionResult(
        filename=file.filename,
        file_type=file_type,
        original_length=len(text),
        invisible_chars=invisible,
        keyword_matches=kw_matches,
        total_findings=len(invisible) + len(kw_matches),
        clean=(len(invisible) + len(kw_matches) == 0),
        extracted_text=text,
    )
    background_tasks.add_task(_record_history, user, file.filename, result.total_findings)
    return result


@app.post("/api/clean", response_model=CleanResult)
async def clean(payload: CleanRequest, user: str = Depends(auth.get_current_user)):
    return clean_and_diff(
        payload.content,
        payload.filename,
        payload.config,
        payload.remove_invisible_ids,
        payload.remove_keyword_ids,
    )


@app.post("/api/clean/download")
async def clean_download(payload: CleanRequest, user: str = Depends(auth.get_current_user)):
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
# Batch API (protected)
# ---------------------------------------------------------------------------

@app.post("/api/batch/detect")
async def batch_detect(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    keywords: str = Form(""),
    use_regex: bool = Form(False),
    case_sensitive: bool = Form(False),
    detect_invisible_unicode: bool = Form(True),
    user: str = Depends(auth.get_current_user),
):
    if len(files) > MAX_BATCH_FILES:
        raise HTTPException(status_code=400, detail=f"M\u00e1ximo {MAX_BATCH_FILES} archivos por lote")

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
            results.append(BatchFileResult(filename=f.filename, status="error", message="L\u00edmite de tama\u00f1o de lote excedido"))
            continue
        try:
            text, file_type = extract_content(f.filename, data)
            invisible, kw_matches = run_detection(text, config)
            detection = DetectionResult(
                filename=f.filename,
                file_type=file_type,
                original_length=len(text),
                invisible_chars=invisible,
                keyword_matches=kw_matches,
                total_findings=len(invisible) + len(kw_matches),
                clean=(len(invisible) + len(kw_matches) == 0),
                extracted_text=text,
            )
            results.append(BatchFileResult(filename=f.filename, status="ok", detection=detection))
            background_tasks.add_task(_record_history, user, f.filename, detection.total_findings)
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
    user: str = Depends(auth.get_current_user),
):
    if len(files) > MAX_BATCH_FILES:
        raise HTTPException(status_code=400, detail=f"M\u00e1ximo {MAX_BATCH_FILES} archivos por lote")

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


# ---------------------------------------------------------------------------
# User preferences (favorite keywords) - in-memory per session
# ---------------------------------------------------------------------------

@app.post("/api/prefs/keywords")
async def save_favorite_keywords(keywords: List[str] = Body(...), user: str = Depends(auth.get_current_user)):
    auth.USER_PREFS.setdefault(user, {"favorite_keywords": []})["favorite_keywords"] = keywords
    return {"favorite_keywords": keywords}


@app.get("/api/prefs/keywords")
async def get_favorite_keywords(user: str = Depends(auth.get_current_user)):
    return {"favorite_keywords": auth.USER_PREFS.get(user, {}).get("favorite_keywords", [])}


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=os.getenv("ENV") == "development")
