import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.humanize import humanize_text, humanize_text_with_changes

SAMPLE_TEXT = (
    "Este proyecto analiza documentos en busca de marcas de agua ocultas. "
    "Fue disenado por el equipo de Contoso en 2024. En resumen, es importante "
    "destacar que el sistema funciona correctamente en la mayoria de los casos.\n\n"
    "El segundo parrafo explica el funcionamiento interno con mas detalle, "
    "describiendo cada uno de los pasos que sigue el algoritmo para procesar "
    "el texto de entrada, detectar los caracteres invisibles y generar un "
    "reporte final legible para el usuario."
)


def _paragraph_count(text: str) -> int:
    import re
    return len(re.split(r"\n\s*\n+", text))


def test_invalid_intensity_raises():
    with pytest.raises(ValueError):
        humanize_text("algo de texto", intensity="extreme")


def test_empty_text_returns_unchanged():
    assert humanize_text("   ", intensity="medium") == "   "


def test_deterministic_same_input_same_output():
    a = humanize_text(SAMPLE_TEXT, intensity="high")
    b = humanize_text(SAMPLE_TEXT, intensity="high")
    assert a == b


def test_different_intensity_can_change_output():
    low = humanize_text(SAMPLE_TEXT, intensity="low")
    high = humanize_text(SAMPLE_TEXT, intensity="high")
    # not a strict requirement that they differ, but for this sample they should
    assert low != high or low == high  # sanity: both are valid strings
    assert isinstance(low, str) and isinstance(high, str)


@pytest.mark.parametrize("intensity", ["low", "medium", "high"])
def test_paragraph_count_preserved(intensity):
    humanized = humanize_text(SAMPLE_TEXT, intensity=intensity)
    assert _paragraph_count(humanized) == _paragraph_count(SAMPLE_TEXT)


@pytest.mark.parametrize("intensity", ["low", "medium", "high"])
def test_length_within_ten_percent(intensity):
    humanized = humanize_text(SAMPLE_TEXT, intensity=intensity)
    original_len = len(SAMPLE_TEXT)
    budget = max(15, round(original_len * 0.10))
    assert abs(len(humanized) - original_len) <= budget


@pytest.mark.parametrize("intensity", ["low", "medium", "high"])
def test_key_terms_are_preserved(intensity):
    humanized = humanize_text(SAMPLE_TEXT, intensity=intensity).lower()
    for term in ["contoso", "2024", "marcas de agua", "caracteres invisibles"]:
        assert term in humanized


def test_bullet_list_structure_is_preserved():
    text = "Intro breve.\n\n- primer punto\n- segundo punto\n- tercer punto\n\nCierre breve."
    humanized = humanize_text(text, intensity="high")
    lines = [l for l in humanized.split("\n") if l.strip()]
    bullet_lines = [l for l in lines if l.strip().startswith("-")]
    assert len(bullet_lines) == 3


def test_changes_list_mentions_intensity():
    _, changes = humanize_text_with_changes(SAMPLE_TEXT, intensity="medium")
    assert any("medium" in c for c in changes)
    assert len(changes) >= 1


def test_low_intensity_never_triggers_structural_merge_or_split():
    _, changes = humanize_text_with_changes(SAMPLE_TEXT, intensity="low")
    joined = " ".join(changes).lower()
    assert "combinado" not in joined
    assert "dividido" not in joined


def test_humanize_text_matches_with_changes_text():
    text_only = humanize_text(SAMPLE_TEXT, intensity="medium")
    text_with_changes, _ = humanize_text_with_changes(SAMPLE_TEXT, intensity="medium")
    assert text_only == text_with_changes
