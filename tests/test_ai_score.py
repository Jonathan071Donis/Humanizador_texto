import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.ai_score import score_text


def test_score_is_within_bounds():
    result = score_text("Un texto cualquiera con algo de contenido para analizar aqui.")
    assert 0.0 <= result.score <= 100.0
    assert isinstance(result.signals, list)
    assert result.signals


def test_disclaimer_present_and_not_a_verdict():
    result = score_text("Texto de ejemplo.")
    assert "heur" in result.disclaimer.lower()
    assert "no es" in result.disclaimer.lower() or "no debe" in result.disclaimer.lower()


def test_detects_stock_ai_connector_phrases():
    text = (
        "En resumen, el proyecto avanza bien. Es importante destacar que los "
        "resultados son positivos. Cabe mencionar que el equipo esta motivado."
    )
    result = score_text(text)
    joined = " ".join(result.signals).lower()
    assert "conector" in joined or "muletilla" in joined


def test_low_sentence_variance_scores_higher_than_high_variance():
    uniform = (
        "El sistema procesa los datos correctamente. El sistema genera un reporte final. "
        "El sistema notifica al usuario final. El sistema guarda el resultado obtenido."
    )
    varied = (
        "Corrio. Despues de una larga espera bajo la lluvia, decidio finalmente entrar al "
        "edificio para preguntar, con cierta timidez, si todavia quedaban entradas disponibles."
    )
    uniform_score = score_text(uniform).score
    varied_score = score_text(varied).score
    assert uniform_score >= varied_score


def test_repetitive_vocabulary_flagged_as_low_lexical_diversity():
    text = " ".join(["dato dato dato analisis analisis resultado resultado"] * 4) + "."
    result = score_text(text)
    joined = " ".join(result.signals).lower()
    assert "diversidad" in joined


def test_empty_text_does_not_crash():
    result = score_text("")
    assert result.score == 0.0
    assert result.signals


def test_custom_connector_phrases_list():
    result = score_text("Esto contiene mi-frase-rara de prueba.", connector_phrases=["mi-frase-rara"])
    joined = " ".join(result.signals).lower()
    assert "mi-frase-rara" in joined
