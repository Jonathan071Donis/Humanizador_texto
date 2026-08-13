"""
Removes detected watermarks from text while preserving everything else
byte-for-byte: indentation, line breaks, syntax, ordering. We only ever
delete the exact character spans that were flagged - nothing is
re-formatted or re-encoded.
"""
from __future__ import annotations

import difflib
import html
from typing import List, Optional, Tuple

from .detector import detect_invisible_unicode, detect_keywords
from .models import CleanResult, DetectionConfig


def _spans_to_remove(
    text: str,
    config: DetectionConfig,
    remove_invisible_ids: Optional[List[str]],
    remove_keyword_ids: Optional[List[str]],
) -> Tuple[List[Tuple[int, int]], int, int]:
    """Return a list of (start, end) spans to delete, plus counts."""
    spans: List[Tuple[int, int]] = []

    invisible = detect_invisible_unicode(text) if config.detect_invisible_unicode else []
    keywords = detect_keywords(text, config)

    removed_invisible = 0
    for m in invisible:
        if remove_invisible_ids is None or m.id in remove_invisible_ids:
            spans.append((m.position, m.position + 1))
            removed_invisible += 1

    removed_keyword = 0
    for m in keywords:
        if remove_keyword_ids is None or m.id in remove_keyword_ids:
            spans.append((m.position, m.position + len(m.matched_text)))
            removed_keyword += 1

    return spans, removed_invisible, removed_keyword


def clean_text(
    text: str,
    config: DetectionConfig,
    remove_invisible_ids: Optional[List[str]] = None,
    remove_keyword_ids: Optional[List[str]] = None,
) -> Tuple[str, int, int]:
    """Return (cleaned_text, removed_invisible_count, removed_keyword_count)."""
    spans, removed_invisible, removed_keyword = _spans_to_remove(
        text, config, remove_invisible_ids, remove_keyword_ids
    )

    if not spans:
        return text, 0, 0

    # Merge/sort spans, delete from the end so earlier offsets stay valid.
    spans.sort(key=lambda s: s[0])
    merged: List[Tuple[int, int]] = []
    for start, end in spans:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    out = text
    for start, end in reversed(merged):
        out = out[:start] + out[end:]

    return out, removed_invisible, removed_keyword


def build_diff_html(original: str, cleaned: str) -> str:
    """Build a compact inline HTML diff: removed spans wrapped in <del>,
    used to render a before/after preview in the UI."""
    sm = difflib.SequenceMatcher(a=original, b=cleaned, autojunk=False)
    parts: List[str] = []
    for opcode, a0, a1, b0, b1 in sm.get_opcodes():
        chunk_orig = html.escape(original[a0:a1])
        if opcode == "equal":
            parts.append(chunk_orig)
        elif opcode == "delete":
            parts.append(f'<del class="wm-removed">{chunk_orig}</del>')
        elif opcode == "replace":
            parts.append(f'<del class="wm-removed">{chunk_orig}</del>')
            parts.append(f'<ins class="wm-added">{html.escape(cleaned[b0:b1])}</ins>')
        elif opcode == "insert":
            parts.append(f'<ins class="wm-added">{html.escape(cleaned[b0:b1])}</ins>')
    return "".join(parts)


def clean_and_diff(
    text: str,
    filename: str,
    config: DetectionConfig,
    remove_invisible_ids: Optional[List[str]] = None,
    remove_keyword_ids: Optional[List[str]] = None,
) -> CleanResult:
    cleaned, n_inv, n_kw = clean_text(text, config, remove_invisible_ids, remove_keyword_ids)
    diff_html = build_diff_html(text, cleaned)
    return CleanResult(
        filename=filename,
        original_content=text,
        cleaned_content=cleaned,
        removed_invisible_count=n_inv,
        removed_keyword_count=n_kw,
        diff_html=diff_html,
    )
