"""
Watermark detection engine.

Detects two categories of watermark:
  1. Invisible / zero-width Unicode characters commonly used to fingerprint
     text (zero-width space, zero-width joiner/non-joiner, BOM, Mongolian
     vowel separator, bidi control marks, invisible separator, tag
     characters used in Unicode "steganography", etc).
  2. User supplied keyword / phrase / regex watermarks, with optional
     case sensitivity.

Nothing here touches disk - it operates purely on in-memory strings.
"""
from __future__ import annotations

import re
from typing import List, Tuple

from .models import DetectionConfig, InvisibleCharMatch, KeywordMatch

# Map of suspicious invisible / zero-width codepoints to human readable names.
INVISIBLE_CHARS = {
    "\u200b": "ZERO WIDTH SPACE",
    "\u200c": "ZERO WIDTH NON-JOINER",
    "\u200d": "ZERO WIDTH JOINER",
    "\u200e": "LEFT-TO-RIGHT MARK",
    "\u200f": "RIGHT-TO-LEFT MARK",
    "\ufeff": "ZERO WIDTH NO-BREAK SPACE (BOM)",
    "\u2060": "WORD JOINER",
    "\u2061": "FUNCTION APPLICATION",
    "\u2062": "INVISIBLE TIMES",
    "\u2063": "INVISIBLE SEPARATOR",
    "\u2064": "INVISIBLE PLUS",
    "\u180e": "MONGOLIAN VOWEL SEPARATOR",
    "\u00ad": "SOFT HYPHEN",
    "\u2028": "LINE SEPARATOR",
    "\u2029": "PARAGRAPH SEPARATOR",
    "\u061c": "ARABIC LETTER MARK",
}
# Bidi override / embedding control characters (also used to disguise text)
_BIDI_RANGE = {chr(c): f"BIDI CONTROL U+{c:04X}" for c in range(0x202A, 0x202F)}
INVISIBLE_CHARS.update(_BIDI_RANGE)

# Unicode "tag" characters U+E0000..U+E007F are invisible and have been used
# to smuggle hidden ASCII payloads into text (a known LLM watermarking / GPT
# steganography trick).
_TAG_RANGE_START = 0xE0000
_TAG_RANGE_END = 0xE007F

# Non-breaking / unusual space variants that are visually confusable with a
# normal space and are sometimes used as low-entropy watermark bits.
SUSPICIOUS_SPACES = {
    "\u00a0": "NO-BREAK SPACE",
    "\u2000": "EN QUAD",
    "\u2001": "EM QUAD",
    "\u2002": "EN SPACE",
    "\u2003": "EM SPACE",
    "\u2004": "THREE-PER-EM SPACE",
    "\u2005": "FOUR-PER-EM SPACE",
    "\u2006": "SIX-PER-EM SPACE",
    "\u2007": "FIGURE SPACE",
    "\u2008": "PUNCTUATION SPACE",
    "\u2009": "THIN SPACE",
    "\u200a": "HAIR SPACE",
    "\u202f": "NARROW NO-BREAK SPACE",
    "\u205f": "MEDIUM MATHEMATICAL SPACE",
    "\u3000": "IDEOGRAPHIC SPACE",
}


def _line_col(text: str, position: int) -> Tuple[int, int]:
    """Return 1-indexed (line, column) for a character offset."""
    line = text.count("\n", 0, position) + 1
    last_nl = text.rfind("\n", 0, position)
    column = position - last_nl if last_nl != -1 else position + 1
    return line, column


def detect_invisible_unicode(text: str) -> List[InvisibleCharMatch]:
    """Scan text for zero-width / control / tag characters that are commonly
    abused as invisible watermarks. Ordinary regular spaces and newlines are
    never flagged."""
    findings: List[InvisibleCharMatch] = []

    for idx, ch in enumerate(text):
        cp = ord(ch)
        name = None

        if ch in INVISIBLE_CHARS:
            name = INVISIBLE_CHARS[ch]
        elif ch in SUSPICIOUS_SPACES:
            name = f"SUSPICIOUS SPACE ({SUSPICIOUS_SPACES[ch]})"
        elif _TAG_RANGE_START <= cp <= _TAG_RANGE_END:
            name = "UNICODE TAG CHARACTER (steganographic payload)"
        elif cp == 0xFFFE or cp == 0xFFFF:
            name = "NONCHARACTER"

        if name:
            line, col = _line_col(text, idx)
            findings.append(
                InvisibleCharMatch(
                    # Deterministic (not random) so the same detection run
                    # over the same text always yields the same id - the
                    # frontend echoes these ids back for selective removal.
                    id=f"inv:{idx}",
                    codepoint=f"U+{cp:04X}",
                    name=name,
                    position=idx,
                    line=line,
                    column=col,
                )
            )

    return findings


# use_regex lets an anonymous, unauthenticated caller supply an arbitrary
# pattern that we compile and run against arbitrary text - textbook ReDoS
# surface (Python's re has no built-in match timeout, and a catastrophic
# pattern like (a+)+$ can pin the process for every other request, not just
# the caller's own rate-limited quota). This is a heuristic denylist for the
# well-known nested-quantifier shapes, not a full safe-regex analyzer - it
# catches the common/naive cases; skip (don't crash) on anything that trips it.
_REDOS_SHAPE_RE = re.compile(
    r"\([^()]*[+*]\)[+*]"      # (a+)+  (a*)*  (a+)*  (a*)+
    r"|\([^()]*[+*]\)\{\d*,"   # (a+){2,}
    r"|(?:\.[+*]){3,}"         # .*.*.*  chained wildcards
)
_MAX_REGEX_PATTERN_LENGTH = 200
_MAX_REGEX_GROUPS = 20


def _is_unsafe_regex_pattern(pattern: str) -> bool:
    if len(pattern) > _MAX_REGEX_PATTERN_LENGTH:
        return True
    if pattern.count("(") > _MAX_REGEX_GROUPS:
        return True
    return bool(_REDOS_SHAPE_RE.search(pattern))


def detect_keywords(text: str, config: DetectionConfig) -> List[KeywordMatch]:
    """Find configured keyword / regex watermark matches."""
    findings: List[KeywordMatch] = []
    if not config.keywords:
        return findings

    flags = 0 if config.case_sensitive else re.IGNORECASE

    for kw in config.keywords:
        kw = kw.strip()
        if not kw:
            continue
        if config.use_regex and _is_unsafe_regex_pattern(kw):
            # Looks like it could blow up catastrophically - skip rather
            # than risk hanging the whole process for one bad pattern.
            continue
        try:
            pattern = kw if config.use_regex else re.escape(kw)
            for m in re.finditer(pattern, text, flags):
                line, col = _line_col(text, m.start())
                findings.append(
                    KeywordMatch(
                        id=f"kw:{m.start()}:{m.end()}",
                        matched_text=m.group(0),
                        keyword=kw,
                        position=m.start(),
                        line=line,
                        column=col,
                    )
                )
        except re.error:
            # Invalid regex from the user - skip this pattern rather than 500ing
            continue

    return findings


def run_detection(text: str, config: DetectionConfig):
    invisible = detect_invisible_unicode(text) if config.detect_invisible_unicode else []
    keywords = detect_keywords(text, config)
    return invisible, keywords
