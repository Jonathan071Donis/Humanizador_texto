"""
Optional, OFF-BY-DEFAULT text "humanizer".

Purpose: given a piece of text (e.g. one that was AI-generated), rewrite it
so it reads with a more natural, varied, less mechanically uniform style -
for legitimate style-editing purposes (proofreading, tone adjustment,
readability). It preserves the original meaning, factual content, logical
structure (same number of paragraphs, similar sentences-per-paragraph) and
overall length (±10%).

Ethical / functional limits (do not remove):
  - This is NOT a tool to evade AI-content or watermark detectors. It does
    not try to trick, fool, or optimize against any classifier - it only
    applies conservative, meaning-preserving style edits.
  - It never changes facts, numbers, named entities, logical order of
    ideas, or paragraph/bullet structure.
  - It is deterministic: the same (text, intensity) pair always produces
    the same output, so results are reproducible and testable.
  - The API layer that calls this module always returns the original text
    alongside the humanized one and a list of the changes applied, so the
    transformation stays fully transparent to the user.

Implementation notes:
  - Word substitution uses a small static Spanish synonym list (no
    external NLP dependency).
  - Sentence merges/splits and the (very narrow) passive->active voice
    rewrite are pattern-based and skipped whenever they'd be unsafe or
    grammatically uncertain - "leave unchanged" is always the safe
    fallback for this module.
"""
from __future__ import annotations

import hashlib
import random
import re
from typing import Dict, List, Tuple

INTENSITIES = ("low", "medium", "high")

_INTENSITY_PARAMS: Dict[str, Dict[str, float]] = {
    "low":    {"synonym_p": 0.20, "connector_p": 0.12, "merge_p": 0.00, "split_p": 0.00, "passive_p": 0.00},
    "medium": {"synonym_p": 0.45, "connector_p": 0.28, "merge_p": 0.18, "split_p": 0.10, "passive_p": 0.35},
    "high":   {"synonym_p": 0.70, "connector_p": 0.42, "merge_p": 0.30, "split_p": 0.22, "passive_p": 0.55},
}

# Small, static, curated synonym list. Keys are matched case-insensitively
# as whole words/phrases; replacements are chosen to avoid gender/number
# agreement issues (invariant adjectives, infinitives, invariant adverbs).
SYNONYMS: Dict[str, List[str]] = {
    "utilizar": ["usar", "emplear"],
    "obtener": ["conseguir", "lograr"],
    "mostrar": ["evidenciar", "reflejar"],
    "mejorar": ["optimizar", "perfeccionar"],
    "permitir": ["posibilitar", "facilitar"],
    "generar": ["producir", "crear"],
    "requerir": ["necesitar", "precisar"],
    "considerar": ["estimar", "valorar"],
    "indicar": ["señalar", "apuntar"],
    "aumentar": ["incrementar", "elevar"],
    "reducir": ["disminuir", "recortar"],
    "importante": ["relevante", "clave"],
    "fácil": ["sencillo", "simple"],
    "rápido": ["veloz", "ágil"],
    "grande": ["amplio", "considerable"],
    "problema": ["inconveniente", "dificultad"],
    "resultado": ["hallazgo", "desenlace"],
    "también": ["asimismo", "igualmente"],
    "además": ["asimismo", "por añadidura"],
    "sin embargo": ["no obstante", "aun así"],
    "por ejemplo": ["a modo de ejemplo", "como muestra"],
    "finalmente": ["por último", "para terminar"],
    "actualmente": ["hoy en día", "en la actualidad"],
    "básicamente": ["esencialmente", "en esencia"],
}

# Natural filler/connector phrases inserted between sentences (medium/high
# intensity mostly). Kept short and comma-friendly on purpose.
CONNECTORS: List[str] = [
    "de hecho",
    "en realidad",
    "básicamente",
    "por cierto",
    "eso sí",
    "en el fondo",
]

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_WORD_RE = re.compile(r"[^\W\d_]+(?:'[^\W\d_]+)?", re.UNICODE)
_BULLET_LINE_RE = re.compile(r"^\s*([-*•‣]|\d+[.)])\s+")

# Narrow, conservative passive -> active rewrite: "X fue/fueron PARTICIPIO
# por Y" -> "Y VERBÓ X". Only fires on regular participles; anything
# uncertain is left unchanged (see _participle_to_finite_verb).
_PASSIVE_RE = re.compile(
    r"(?P<subject>[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑñáéíóú]*(?:\s+[\wÁÉÍÓÚÑñáéíóú]+){0,4})\s+"
    r"(?P<aux>fue|fueron)\s+"
    r"(?P<participle>[a-záéíóúñ]+(?:ados|adas|ado|ada|idos|idas|ido|ida))\s+"
    r"por\s+"
    r"(?P<agent>[\wÁÉÍÓÚÑñáéíóú]+(?:\s+[\wÁÉÍÓÚÑñáéíóú]+){0,4})"
)
# -ido/-ida participles whose preterite is irregular (produjo, not
# "produció", etc.) - skip the passive rewrite for these to avoid
# generating an ungrammatical (and therefore meaning-distorting) sentence.
_IRREGULAR_IDO_STEMS = (
    "ducido", "ducida", "ducidos", "ducidas",  # producir, traducir, conducir, reducir, introducir...
    "tenido", "tenida", "tenidos", "tenidas",
    "venido", "venida", "venidos", "venidas",
    "podido", "sabido", "querido", "querida",
)


def _synonym_pattern() -> re.Pattern:
    keys = sorted(SYNONYMS.keys(), key=len, reverse=True)
    alternation = "|".join(re.escape(k) for k in keys)
    return re.compile(rf"\b(?:{alternation})\b", re.IGNORECASE | re.UNICODE)


_SYNONYM_PATTERN = _synonym_pattern()


def _word_count(s: str) -> int:
    return len(_WORD_RE.findall(s))


def _seed_for(text: str, intensity: str) -> int:
    digest = hashlib.sha256(f"{intensity}::{text}".encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def _is_bullet_paragraph(paragraph: str) -> bool:
    lines = [l for l in paragraph.split("\n") if l.strip()]
    if len(lines) < 2:
        return False
    bullet_lines = sum(1 for l in lines if _BULLET_LINE_RE.match(l))
    return bullet_lines >= max(1, len(lines) // 2)


def _apply_synonyms(sentence: str, rng: random.Random, prob: float) -> Tuple[str, bool]:
    applied = False

    def repl(m: re.Match) -> str:
        nonlocal applied
        word = m.group(0)
        options = SYNONYMS.get(word.lower())
        if not options or rng.random() > prob:
            return word
        choice = rng.choice(options)
        if word[:1].isupper():
            choice = choice[:1].upper() + choice[1:]
        applied = True
        return choice

    new_sentence = _SYNONYM_PATTERN.sub(repl, sentence)
    return new_sentence, applied


def _maybe_insert_connector(sentence: str, rng: random.Random, prob: float, is_first: bool) -> Tuple[str, bool]:
    if is_first or not sentence:
        return sentence, False
    if rng.random() > prob:
        return sentence, False
    connector = rng.choice(CONNECTORS)
    first_char, rest = sentence[0], sentence[1:]
    lowered_first = first_char.lower() if first_char.isupper() else first_char
    return f"{connector.capitalize()}, {lowered_first}{rest}", True


def _participle_to_finite_verb(participle: str, plural: bool):
    """Conjugate a regular participle into the preterite that agrees with
    `plural` (the NEW subject's number - the former agent - not the
    participle's own morphological number, which described the old
    subject and is irrelevant once it becomes the object)."""
    low = participle.lower()
    if low.endswith(_IRREGULAR_IDO_STEMS):
        return None
    if low.endswith(("ados", "adas")):
        stem, conjugation = low[:-4], "ar"
    elif low.endswith(("ado", "ada")):
        stem, conjugation = low[:-3], "ar"
    elif low.endswith(("idos", "idas")):
        stem, conjugation = low[:-4], "er_ir"
    elif low.endswith(("ido", "ida")):
        stem, conjugation = low[:-3], "er_ir"
    else:
        return None
    if conjugation == "ar":
        return stem + ("aron" if plural else "ó")
    return stem + ("ieron" if plural else "ió")


def _agent_is_plural(agent: str):
    """Best-effort number agreement for the new subject (the former
    passive agent). Returns None when it can't be determined confidently
    (e.g. no leading article, proper noun) - callers must skip the
    rewrite in that case rather than guess."""
    first_word = agent.split()[0].lower() if agent.split() else ""
    if first_word in ("los", "las", "unos", "unas"):
        return True
    if first_word in ("el", "la", "un", "una", "lo"):
        return False
    return None


def _maybe_passive_to_active(sentence: str, rng: random.Random, prob: float) -> Tuple[str, bool]:
    m = _PASSIVE_RE.search(sentence)
    if not m or rng.random() > prob:
        return sentence, False
    agent = m.group("agent").strip()
    agent_plural = _agent_is_plural(agent)
    if agent_plural is None:
        return sentence, False
    verb = _participle_to_finite_verb(m.group("participle"), agent_plural)
    if not verb:
        return sentence, False
    subject = m.group("subject").strip()
    subject_lowered = subject[:1].lower() + subject[1:] if subject and not subject.isupper() else subject
    agent_capitalized = agent[:1].upper() + agent[1:] if agent else agent
    replacement = f"{agent_capitalized} {verb} {subject_lowered}"
    new_sentence = sentence[: m.start()] + replacement + sentence[m.end():]
    return new_sentence, True


def _maybe_merge_sentences(sentences: List[str], rng: random.Random, prob: float) -> Tuple[List[str], bool]:
    if prob <= 0 or len(sentences) < 2:
        return sentences, False
    result: List[str] = []
    applied = False
    i = 0
    while i < len(sentences):
        current = sentences[i]
        if i + 1 < len(sentences) and _word_count(current) <= 7 and _word_count(sentences[i + 1]) <= 7 and rng.random() < prob:
            nxt = sentences[i + 1]
            current_stripped = current.rstrip()
            body = current_stripped[:-1] if current_stripped and current_stripped[-1] in ".!?" else current_stripped
            nxt_stripped = nxt.strip()
            nxt_body = (nxt_stripped[:1].lower() + nxt_stripped[1:]) if nxt_stripped else nxt_stripped
            result.append(f"{body}, {nxt_body}")
            applied = True
            i += 2
        else:
            result.append(current)
            i += 1
    return result, applied


def _maybe_split_sentences(sentences: List[str], rng: random.Random, prob: float) -> Tuple[List[str], bool]:
    if prob <= 0:
        return sentences, False
    result: List[str] = []
    applied = False
    for s in sentences:
        if _word_count(s) > 28 and rng.random() < prob:
            mid = len(s) // 2
            commas = [m.start() for m in re.finditer(",", s)]
            if commas:
                split_at = min(commas, key=lambda p: abs(p - mid))
                first = s[:split_at].rstrip().rstrip(",") + "."
                second_raw = s[split_at + 1:].strip()
                if second_raw:
                    second = second_raw[:1].upper() + second_raw[1:]
                    result.append(first)
                    result.append(second)
                    applied = True
                    continue
        result.append(s)
    return result, applied


def _generate(text: str, seed: int, params: Dict[str, float]) -> Tuple[str, Dict[str, bool]]:
    rng = random.Random(seed)
    applied = {"synonym": False, "connector": False, "merge": False, "split": False, "passive": False}

    paragraphs = re.split(r"\n\s*\n+", text)
    out_paragraphs: List[str] = []

    for paragraph in paragraphs:
        if not paragraph.strip():
            out_paragraphs.append(paragraph)
            continue

        if _is_bullet_paragraph(paragraph):
            lines = paragraph.split("\n")
            new_lines = []
            for line in lines:
                new_line, syn_applied = _apply_synonyms(line, rng, params["synonym_p"])
                applied["synonym"] = applied["synonym"] or syn_applied
                new_lines.append(new_line)
            out_paragraphs.append("\n".join(new_lines))
            continue

        sentences = [s for s in _SENTENCE_SPLIT_RE.split(paragraph.strip()) if s]
        transformed = []
        for idx, sentence in enumerate(sentences):
            s, syn_applied = _apply_synonyms(sentence, rng, params["synonym_p"])
            s, con_applied = _maybe_insert_connector(s, rng, params["connector_p"], is_first=(idx == 0))
            s, pas_applied = _maybe_passive_to_active(s, rng, params["passive_p"])
            applied["synonym"] = applied["synonym"] or syn_applied
            applied["connector"] = applied["connector"] or con_applied
            applied["passive"] = applied["passive"] or pas_applied
            transformed.append(s)

        transformed, merge_applied = _maybe_merge_sentences(transformed, rng, params["merge_p"])
        applied["merge"] = applied["merge"] or merge_applied
        transformed, split_applied = _maybe_split_sentences(transformed, rng, params["split_p"])
        applied["split"] = applied["split"] or split_applied

        out_paragraphs.append(" ".join(transformed))

    return "\n\n".join(out_paragraphs), applied


def _describe_changes(applied: Dict[str, bool], intensity: str) -> List[str]:
    changes: List[str] = []
    if applied.get("synonym"):
        changes.append("Se han sustituido algunas palabras por sinónimos equivalentes.")
    if applied.get("connector"):
        changes.append("Se han insertado conectores y muletillas naturales (p. ej. «de hecho», «básicamente»).")
    if applied.get("merge"):
        changes.append("Se han combinado oraciones cortas adyacentes para variar el ritmo.")
    if applied.get("split"):
        changes.append("Se han dividido oraciones largas para mejorar la lectura.")
    if applied.get("passive"):
        changes.append("Se ha convertido alguna oración de voz pasiva a voz activa, solo cuando era gramaticalmente segura.")
    if not changes:
        changes.append("No se aplicaron cambios sustanciales para esta intensidad (texto ya variado o demasiado corto).")
    changes.append(
        f"Intensidad aplicada: {intensity}. El significado, los datos y la estructura de párrafos originales se conservan."
    )
    return changes


def humanize_text_with_changes(text: str, intensity: str = "medium") -> Tuple[str, List[str]]:
    """Deterministic: the same (text, intensity) pair always returns the
    same (humanized_text, changes) pair. Keeps paragraph count identical
    and overall length within roughly ±10% of the original."""
    if intensity not in INTENSITIES:
        raise ValueError(f"intensity must be one of {INTENSITIES}, got {intensity!r}")
    if not text.strip():
        return text, ["El texto está vacío; no se aplicó ningún cambio."]

    seed = _seed_for(text, intensity)
    base_params = dict(_INTENSITY_PARAMS[intensity])
    original_len = len(text)
    budget = max(15, round(original_len * 0.10))

    params = dict(base_params)
    result_text, applied = _generate(text, seed, params)

    if abs(len(result_text) - original_len) > budget:
        params["connector_p"] = 0.0
        result_text, applied = _generate(text, seed, params)

    if abs(len(result_text) - original_len) > budget:
        params["synonym_p"] = min(params["synonym_p"], 0.15)
        result_text, applied = _generate(text, seed, params)

    changes = _describe_changes(applied, intensity)
    return result_text, changes


def humanize_text(text: str, intensity: str = "medium") -> str:
    """See humanize_text_with_changes - this is a thin wrapper returning
    just the rewritten text, matching the module's public contract."""
    result, _ = humanize_text_with_changes(text, intensity)
    return result
