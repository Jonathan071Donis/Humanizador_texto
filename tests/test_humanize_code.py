import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.humanize import humanize_code_comments, resolve_language


def test_invalid_intensity_raises():
    with pytest.raises(ValueError):
        humanize_code_comments("print(1)", intensity="extreme")


def test_empty_code_returns_unchanged():
    code, changes, language = humanize_code_comments("   ", intensity="medium")
    assert code == "   "
    assert language == "unknown"


def test_deterministic_same_input_same_output():
    code = "def foo():\n    # Es importante destacar que esto es crucial\n    return 1\n"
    a, _, _ = humanize_code_comments(code, "python", "high")
    b, _, _ = humanize_code_comments(code, "python", "high")
    assert a == b


def test_code_lines_are_never_touched():
    code = (
        "def calcular_total(items):\n"
        "    # Es importante destacar que aqui se suman los items validos\n"
        "    total = 0\n"
        "    for item in items:\n"
        "        if item < 0:\n"
        "            continue\n"
        "        total += item\n"
        "    return total\n"
    )
    out, _, _ = humanize_code_comments(code, "python", "high")
    code_lines = [l for l in code.split("\n") if not l.strip().startswith("#")]
    out_lines = out.split("\n")
    for line in code_lines:
        assert line in out_lines


def test_hash_inside_string_is_not_treated_as_comment():
    code = 'url = "https://example.com/#fragment"\nvalue = 1  # nota rapida\n'
    out, _, _ = humanize_code_comments(code, "python", "high")
    assert 'url = "https://example.com/#fragment"' in out


def test_double_slash_inside_js_string_is_not_treated_as_comment():
    code = 'const url = "https://example.com"; // Es importante destacar que esto es una nota\n'
    out, _, _ = humanize_code_comments(code, "javascript", "high")
    assert 'const url = "https://example.com";' in out


def test_multiline_block_comment_is_humanized():
    code = (
        "function foo() {\n"
        "  /* Es importante destacar que\n"
        "     esto abarca varias lineas */\n"
        "  return 1;\n"
        "}\n"
    )
    out, changes, _ = humanize_code_comments(code, "javascript", "high")
    assert "es importante destacar que" not in out.lower()
    assert "return 1;" in out


def test_language_auto_detection_python():
    code = "import os\n\ndef foo():\n    return os.getcwd()\n"
    assert resolve_language("auto", None, code) == "python"


def test_language_auto_detection_html():
    code = "<!DOCTYPE html>\n<html><body></body></html>\n"
    assert resolve_language("auto", None, code) == "html"


def test_language_resolved_from_filename_extension():
    assert resolve_language("auto", "script.rs", "fn main() {}") == "rust"


def test_explicit_language_overrides_auto():
    assert resolve_language("python", "script.rs", "fn main() {}") == "python"


def test_unknown_language_falls_back_gracefully():
    lang = resolve_language("not-a-real-language", None, "x = 1")
    assert lang in ("javascript", "python")  # any sane fallback, never crashes


def test_changes_list_mentions_language_and_intensity():
    code = "x = 1  # es crucial\n"
    _, changes, language = humanize_code_comments(code, "python", "medium")
    joined = " ".join(changes)
    assert language in joined
    assert "medium" in joined
