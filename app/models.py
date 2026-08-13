"""
Pydantic models used across the API. No database, no accounts - these are
pure in-memory / wire-format schemas.
"""
from __future__ import annotations

from typing import List, Literal, Optional
from pydantic import BaseModel, Field


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


class AIScoreResult(BaseModel):
    """Heuristic, non-ML estimate of how likely a text is to be AI-generated.

    Purely statistical/informational - not a trained classifier and not a
    verdict. See ai_score.py for the signals used and their weights.
    """
    score: float                # 0-100, higher = more heuristic signals of AI-generated style
    signals: List[str]          # human-readable explanation of what triggered the score
    disclaimer: str


class DetectionResult(BaseModel):
    filename: str
    file_type: str
    original_length: int
    invisible_chars: List[InvisibleCharMatch]
    keyword_matches: List[KeywordMatch]
    total_findings: int
    clean: bool
    extracted_text: str
    ai_score: Optional[AIScoreResult] = None
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


# ---------------------------------------------------------------------------
# Text humanization (optional, off by default, purely stylistic - see
# humanize.py for the scope and ethical limits of this feature)
# ---------------------------------------------------------------------------

class HumanizeRequest(BaseModel):
    text: str = Field(..., min_length=1)
    intensity: Literal["low", "medium", "high"] = "medium"


class HumanizeResponse(BaseModel):
    original: str
    humanized: str
    changes: List[str]
