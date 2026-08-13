"""
Pydantic models used across the API. No database - these are pure
in-memory / wire-format schemas.
"""
from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=6, max_length=128)


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str


# ---------------------------------------------------------------------------
# Detection configuration
# ---------------------------------------------------------------------------

class DetectionConfig(BaseModel):
    keywords: List[str] = Field(default_factory=list)
    use_regex: bool = False
    case_sensitive: bool = False
    detect_invisible_unicode: bool = True


class TextProcessRequest(BaseModel):
    content: str
    filename: str = "pasted_text.txt"
    config: DetectionConfig = Field(default_factory=DetectionConfig)


# ---------------------------------------------------------------------------
# Detection results
# ---------------------------------------------------------------------------

class InvisibleCharMatch(BaseModel):
    id: str
    codepoint: str          # e.g. "U+200B"
    name: str                # e.g. "ZERO WIDTH SPACE"
    position: int             # character offset in the original text
    line: int
    column: int


class KeywordMatch(BaseModel):
    id: str
    matched_text: str
    keyword: str
    position: int
    line: int
    column: int


class DetectionResult(BaseModel):
    filename: str
    file_type: str
    original_length: int
    invisible_chars: List[InvisibleCharMatch]
    keyword_matches: List[KeywordMatch]
    total_findings: int
    clean: bool
    extracted_text: str
    error: Optional[str] = None


class CleanRequest(BaseModel):
    content: str
    filename: str = "pasted_text.txt"
    config: DetectionConfig = Field(default_factory=DetectionConfig)
    remove_invisible_ids: Optional[List[str]] = None   # None = remove all found
    remove_keyword_ids: Optional[List[str]] = None     # None = remove all found


class CleanResult(BaseModel):
    filename: str
    original_content: str
    cleaned_content: str
    removed_invisible_count: int
    removed_keyword_count: int
    diff_html: str


class BatchFileResult(BaseModel):
    filename: str
    status: str  # "ok" | "error"
    detection: Optional[DetectionResult] = None
    message: Optional[str] = None
