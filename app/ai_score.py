"""
Heuristic, non-ML estimate of how likely a text is to be AI-generated.

IMPORTANT — scope and limits:
  - This is a STATISTICAL/HEURISTIC signal based on surface style features
    (sentence-length variance, lexical diversity, stock AI connector
    phrases, punctuation uniformity). It is NOT a trained machine-learning
    classifier, it does not call any external detector, and it is NOT a
    tool for evading AI or watermark detectors.
  - It only ever produces a percentage plus a plain-language explanation of
    which signals fired. It never rewrites, paraphrases, or otherwise
    modifies the analyzed text.
  - It can have false positives and false negatives, especially on short
    texts, non-Spanish text, or text with an unusual style. Treat the
    result as an inconclusive estimate, not a verdict.
"""
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from typing import List, Optional

# Configurable list of connector/filler phrases that show up disproportionately
# often in AI-generated Spanish text. Feel free to extend/tune this list.
DEFAULT_AI_CONNECTOR_PHRASES: List[str] = [
    "en resumen",
    "es importante destacar",
    "en conclusión",
    "cabe mencionar",
    "cabe destacar",
    "en definitiva",
    "por otro lado",
    "en este sentido",
    "es fundamental",
    "en última instancia",
    "no obstante",
    "vale la pena mencionar",
    "es importante señalar",
    "en síntesis",
    "dicho esto",
    "en un mundo cada vez más",
    "es crucial",
    "a la hora de",
    "por lo tanto",
    "en el panorama actual",
]

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_WORD_RE = re.compile(r"[^\W\d_]+(?:'[^\W\d_]+)?", re.UNICODE)


@dataclass
class AIScoreResult:
    score: float
    signals: List[str] = field(default_factory=list)
    disclaimer: str = (
        "Estimación heurística basada en el estilo superficial del texto "
        "(longitud de oraciones, diversidad léxica, conectores típicos y "
        "puntuación). No es un modelo de machine learning entrenado ni un "
        "detector forense, y puede tener falsos positivos y falsos "
        "negativos. No debe interpretarse como una conclusión definitiva."
    )


def _split_sentences(text: str) -> List[str]:
    return [s.strip() for s in _SENTENCE_SPLIT_RE.split(text.strip()) if s.strip()]


def _split_words(text: str) -> List[str]:
    return [w.lower() for w in _WORD_RE.findall(text)]


def score_text(text: str, connector_phrases: Optional[List[str]] = None) -> AIScoreResult:
    """Compute a 0-100 heuristic "AI-generated style" score plus the list of
    signals that contributed to it. Deterministic and side-effect free."""
    connector_phrases = connector_phrases if connector_phrases is not None else DEFAULT_AI_CONNECTOR_PHRASES

    text = text or ""
    sentences = _split_sentences(text)
    words = _split_words(text)

    signals: List[str] = []
    points = 0.0
    max_points = 0.0

    # 1. Sentence-length variance: very uniform sentence lengths are a common
    #    fingerprint of AI-generated prose.
    if len(sentences) >= 3:
        max_points += 25
        lengths = [len(_split_words(s)) for s in sentences]
        mean_len = statistics.mean(lengths) if lengths else 0
        stdev = statistics.pstdev(lengths) if len(lengths) > 1 else 0
        coeff_var = (stdev / mean_len) if mean_len else 0
        if coeff_var < 0.35:
            points += 25
            signals.append(
                f"Baja varianza en la longitud de las oraciones (coeficiente de variación "
                f"{coeff_var:.2f}), un patrón frecuente en texto generado por IA."
            )
        elif coeff_var < 0.55:
            points += 12
            signals.append(f"Varianza moderada en la longitud de las oraciones (cv={coeff_var:.2f}).")

    # 2. Lexical diversity (type-token ratio): low diversity => repetitive
    #    vocabulary, another common AI fingerprint.
    if len(words) >= 20:
        max_points += 25
        ttr = len(set(words)) / len(words)
        if ttr < 0.4:
            points += 25
            signals.append(f"Diversidad léxica baja (type-token ratio={ttr:.2f}), vocabulario repetitivo.")
        elif ttr < 0.55:
            points += 12
            signals.append(f"Diversidad léxica moderada (type-token ratio={ttr:.2f}).")

    # 3. Stock AI connector/filler phrases.
    max_points += 30
    text_lower = text.lower()
    found_phrases = [p for p in connector_phrases if p in text_lower]
    if found_phrases:
        points += min(30, 10 * len(found_phrases))
        signals.append(
            "Uso de conectores o muletillas típicas de texto generado por IA: "
            + ", ".join(f'"{p}"' for p in found_phrases) + "."
        )

    # 4. Punctuation uniformity: sentences that (almost) always end in a
    #    period, with a very even comma distribution, read as mechanically
    #    regular.
    if len(sentences) >= 3:
        max_points += 20
        end_marks = [s.rstrip()[-1] for s in sentences if s.rstrip()]
        period_ratio = end_marks.count(".") / len(end_marks) if end_marks else 0
        commas_per_sentence = [s.count(",") for s in sentences]
        comma_stdev = statistics.pstdev(commas_per_sentence) if len(commas_per_sentence) > 1 else 0
        if period_ratio > 0.9 and comma_stdev < 1.0:
            points += 20
            signals.append(
                "Puntuación muy uniforme: casi todas las oraciones terminan en punto y la "
                "distribución de comas es homogénea entre oraciones."
            )
        elif period_ratio > 0.75:
            points += 10
            signals.append("Puntuación relativamente uniforme entre oraciones.")

    score = round((points / max_points) * 100, 1) if max_points else 0.0
    score = min(100.0, max(0.0, score))

    if not signals:
        signals.append(
            "No se detectaron señales estilísticas destacadas, o el texto es demasiado "
            "corto para una estimación fiable."
        )

    return AIScoreResult(score=score, signals=signals)
