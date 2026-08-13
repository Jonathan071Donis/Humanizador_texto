import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.cleaner import clean_and_diff, clean_text
from app.detector import detect_invisible_unicode, detect_keywords, run_detection
from app.models import DetectionConfig


def test_detect_zero_width_space():
    text = "hello\u200bworld"
    findings = detect_invisible_unicode(text)
    assert len(findings) == 1
    assert findings[0].codepoint == "U+200B"
    assert findings[0].position == 5


def test_detect_multiple_invisible_chars():
    text = "a\u200bb\ufeffc\u2060d"
    findings = detect_invisible_unicode(text)
    assert len(findings) == 3
    codepoints = {f.codepoint for f in findings}
    assert codepoints == {"U+200B", "U+FEFF", "U+2060"}


def test_no_false_positive_on_normal_text():
    text = "This is completely normal text.\nWith a newline and a\ttab."
    findings = detect_invisible_unicode(text)
    assert findings == []


def test_detect_keyword_case_insensitive():
    config = DetectionConfig(keywords=["confidential"], case_sensitive=False)
    text = "This document is CONFIDENTIAL and internal."
    matches = detect_keywords(text, config)
    assert len(matches) == 1
    assert matches[0].matched_text == "CONFIDENTIAL"


def test_detect_keyword_case_sensitive_no_match():
    config = DetectionConfig(keywords=["Secret"], case_sensitive=True)
    text = "this is a secret, not Secret... wait it is Secret"
    matches = detect_keywords(text, config)
    assert len(matches) == 2


def test_detect_keyword_regex():
    config = DetectionConfig(keywords=[r"WM-\d{4}"], use_regex=True)
    text = "Report tagged WM-1029 and also WM-8842."
    matches = detect_keywords(text, config)
    assert len(matches) == 2
    assert matches[0].matched_text == "WM-1029"


def test_invalid_regex_does_not_crash():
    config = DetectionConfig(keywords=["("], use_regex=True)
    matches = detect_keywords("some (text)", config)
    assert matches == []


def test_clean_removes_invisible_chars_and_preserves_rest():
    text = "def foo():\u200b\n    return 1\ufeff\n"
    config = DetectionConfig()
    cleaned, n_inv, n_kw = clean_text(text, config)
    assert n_inv == 2
    assert n_kw == 0
    assert cleaned == "def foo():\n    return 1\n"


def test_clean_preserves_code_structure():
    code = "def add(a, b):\n\u200b    return a + b\n"
    config = DetectionConfig()
    cleaned, n_inv, _ = clean_text(code, config)
    assert n_inv == 1
    # indentation and logic must be untouched
    assert "    return a + b" in cleaned
    assert cleaned.count("\n") == code.count("\n")


def test_clean_selective_removal_by_id():
    text = "a\u200bb\u200cc"
    config = DetectionConfig()
    invisible = detect_invisible_unicode(text)
    keep_first_only = [invisible[0].id]
    cleaned, n_inv, _ = clean_text(text, config, remove_invisible_ids=keep_first_only)
    assert n_inv == 1
    assert cleaned == "ab\u200cc"


def test_clean_keyword_removal():
    config = DetectionConfig(keywords=["WATERMARK-X"])
    text = "start WATERMARK-X end"
    cleaned, n_inv, n_kw = clean_text(text, config)
    assert n_kw == 1
    assert cleaned == "start  end"


def test_run_detection_combined():
    config = DetectionConfig(keywords=["secret"])
    text = "top \u200bsecret file"
    invisible, keywords = run_detection(text, config)
    assert len(invisible) == 1
    assert len(keywords) == 1


def test_clean_and_diff_produces_html():
    config = DetectionConfig()
    result = clean_and_diff("clean\u200btext", "f.txt", config)
    assert result.removed_invisible_count == 1
    assert "wm-removed" in result.diff_html
    assert result.cleaned_content == "cleantext"


def test_clean_text_no_findings_returns_original():
    config = DetectionConfig()
    text = "nothing suspicious here"
    cleaned, n_inv, n_kw = clean_text(text, config)
    assert cleaned == text
    assert n_inv == 0
    assert n_kw == 0
