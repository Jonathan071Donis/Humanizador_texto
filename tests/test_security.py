import os
import sys
import time

import pytest
from pydantic import ValidationError
from starlette.middleware.cors import CORSMiddleware

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.detector import _is_unsafe_regex_pattern, detect_keywords
from app.models import (
    MAX_CODE_LENGTH,
    MAX_KEYWORD_LENGTH,
    MAX_KEYWORDS,
    MAX_TEXT_LENGTH,
    DetectionConfig,
    HumanizeCodeRequest,
    HumanizeRequest,
    TextProcessRequest,
)


# ---------------------------------------------------------------------------
# ReDoS heuristic (app/detector.py)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("pattern", [
    "(a+)+$",
    "(a*)*b",
    "(\\w+)*$",
    "(a+){2,}",
    ".*.*.*x",
])
def test_catastrophic_patterns_are_flagged_unsafe(pattern):
    assert _is_unsafe_regex_pattern(pattern) is True


@pytest.mark.parametrize("pattern", [
    "confidencial",
    r"©\d{4}",
    r"watermark-[a-z0-9]+",
    r"\bZWSP\b",
    r"^Draft:",
    r"[A-Za-z]+@[A-Za-z]+\.com",
])
def test_benign_patterns_are_not_flagged(pattern):
    assert _is_unsafe_regex_pattern(pattern) is False


def test_overly_long_pattern_is_flagged():
    assert _is_unsafe_regex_pattern("a" * 500) is True


def test_too_many_groups_is_flagged():
    assert _is_unsafe_regex_pattern("(a)" * 25) is True


def test_detect_keywords_skips_unsafe_pattern_instead_of_hanging():
    config = DetectionConfig(keywords=["(a+)+$"], use_regex=True)
    start = time.time()
    findings = detect_keywords("a" * 40 + "!", config)
    elapsed = time.time() - start
    assert findings == []
    assert elapsed < 1.0  # would hang for a very long time if actually evaluated


def test_detect_keywords_still_works_for_safe_regex():
    config = DetectionConfig(keywords=[r"confi\w+"], use_regex=True)
    findings = detect_keywords("texto confidencial aqui", config)
    assert len(findings) == 1
    assert findings[0].matched_text == "confidencial"


# ---------------------------------------------------------------------------
# Request size limits (app/models.py)
# ---------------------------------------------------------------------------

def test_text_process_request_rejects_oversized_content():
    with pytest.raises(ValidationError):
        TextProcessRequest(content="x" * (MAX_TEXT_LENGTH + 1))


def test_text_process_request_accepts_content_at_the_limit():
    TextProcessRequest(content="x" * MAX_TEXT_LENGTH)


def test_humanize_request_rejects_oversized_text():
    with pytest.raises(ValidationError):
        HumanizeRequest(text="x" * (MAX_TEXT_LENGTH + 1))


def test_humanize_code_request_rejects_oversized_code():
    with pytest.raises(ValidationError):
        HumanizeCodeRequest(code="x" * (MAX_CODE_LENGTH + 1))


def test_detection_config_rejects_too_many_keywords():
    with pytest.raises(ValidationError):
        DetectionConfig(keywords=["x"] * (MAX_KEYWORDS + 1))


def test_detection_config_rejects_oversized_keyword():
    with pytest.raises(ValidationError):
        DetectionConfig(keywords=["x" * (MAX_KEYWORD_LENGTH + 1)])


def test_detection_config_accepts_normal_keywords():
    DetectionConfig(keywords=["confidencial", "marca-agua"])


# ---------------------------------------------------------------------------
# CORS (app/main.py) - allow_credentials must never be True with wildcard origins
# ---------------------------------------------------------------------------

def test_cors_credentials_disabled_with_wildcard_origin():
    from app.main import app

    cors = next(m for m in app.user_middleware if m.cls is CORSMiddleware)
    kwargs = getattr(cors, "kwargs", None) or getattr(cors, "options", {})
    if "*" in kwargs["allow_origins"]:
        assert kwargs["allow_credentials"] is False


# ---------------------------------------------------------------------------
# Security response headers (app/main.py)
# ---------------------------------------------------------------------------

def test_security_headers_present_on_every_response():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    res = client.get("/health")
    assert res.headers.get("x-content-type-options") == "nosniff"
    assert res.headers.get("x-frame-options") == "DENY"
    assert res.headers.get("referrer-policy") == "no-referrer"
