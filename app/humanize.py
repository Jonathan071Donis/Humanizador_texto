
from __future__ import annotations

import hashlib
import random
import re
from typing import Dict, List, Optional, Tuple

INTENSITIES = ("low", "medium", "high")

_INTENSITY_PARAMS: Dict[str, Dict[str, float]] = {
    "low":    {"synonym_p": 0.20, "connector_p": 0.12, "merge_p": 0.00, "split_p": 0.00, "passive_p": 0.00, "cliche_p": 0.70, "merge_threshold": 6, "split_threshold": 30},
    "medium": {"synonym_p": 0.45, "connector_p": 0.28, "merge_p": 0.18, "split_p": 0.10, "passive_p": 0.35, "cliche_p": 0.88, "merge_threshold": 7, "split_threshold": 26},
    "high":   {"synonym_p": 0.70, "connector_p": 0.42, "merge_p": 0.34, "split_p": 0.26, "passive_p": 0.55, "cliche_p": 0.98, "merge_threshold": 9, "split_threshold": 20},
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
    "sin embargo": ["aun así", "con todo"],
    "por ejemplo": ["a modo de ejemplo", "como muestra"],
    "finalmente": ["por último", "para terminar"],
    "actualmente": ["hoy en día", "en la actualidad"],
    "básicamente": ["esencialmente", "en esencia"],
}

# Stock phrases that read as "obviously AI-written" (the same family ai_score.py
# flags). Matched as whole phrases, case-insensitively. A None option means
# "just cut it out" rather than swap in another word - some of these add
# nothing and the sentence reads better with them gone.
CLICHE_PHRASES: Dict[str, List[Optional[str]]] = {
    "es importante destacar que": ["hay que decir que", "vale la pena decir que", None],
    "es importante destacar": ["hay que destacar", "vale la pena destacar"],
    "es importante señalar que": ["conviene señalar que", "vale la pena decir que", None],
    "es importante señalar": ["conviene señalar", "vale la pena señalar"],
    "es importante mencionar que": ["vale la pena mencionar que", None],
    "es importante mencionar": ["vale la pena mencionar", "conviene mencionar"],
    "vale la pena mencionar que": ["conviene decir que", None],
    "vale la pena mencionar": ["conviene mencionar", "no está de más decir"],
    "cabe destacar que": ["hay que decir que", None],
    "cabe destacar": ["hay que destacar", "conviene destacar"],
    "cabe mencionar que": ["vale mencionar que", None],
    "cabe mencionar": ["vale mencionar", "conviene mencionar"],
    "cabe resaltar que": ["hay que resaltar que", None],
    "cabe resaltar": ["hay que resaltar", "conviene resaltar"],
    "no cabe duda de que": ["está claro que", "sin duda,"],
    "es fundamental": ["es clave", "pesa muchísimo", "resulta clave"],
    "es crucial": ["es clave", "pesa muchísimo", "resulta decisivo"],
    "resulta crucial": ["resulta clave", "pesa muchísimo"],
    "juega un papel crucial": ["pesa muchísimo", "es clave"],
    "juega un papel fundamental": ["es clave", "pesa muchísimo"],
    "sumergirse en": ["meterse de lleno en", "adentrarse en"],
    "sumergirnos en": ["meternos de lleno en", "adentrarnos en"],
    "sumergirte en": ["meterte de lleno en", "adentrarte en"],
    "en resumen": ["en pocas palabras", "resumiendo", "total"],
    "en síntesis": ["en pocas palabras", "resumiendo"],
    "a modo de resumen": ["en pocas palabras"],
    "en conclusión": ["para cerrar", "al final"],
    "a modo de conclusión": ["para cerrar"],
    "en definitiva": ["al final", "total"],
    "en última instancia": ["al final", "a fin de cuentas"],
    "dicho esto": ["con todo", "aun así"],
    "en este sentido": ["por eso", "así que"],
    "a la hora de": ["al momento de", "cuando toca"],
    "por otro lado": ["por otra parte", "eso sí,", "en cambio,"],
    "no obstante": ["aun así", "con todo"],
    "en un mundo cada vez más": ["en un momento cada vez más", "hoy en día, cada vez más"],
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


def _cliche_pattern() -> re.Pattern:
    keys = sorted(CLICHE_PHRASES.keys(), key=len, reverse=True)
    alternation = "|".join(re.escape(k) for k in keys)
    return re.compile(rf"\b(?:{alternation})\b", re.IGNORECASE | re.UNICODE)


_CLICHE_PATTERN = _cliche_pattern()


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


def _apply_cliches(sentence: str, rng: random.Random, prob: float) -> Tuple[str, bool]:
    applied = False

    def repl(m: re.Match) -> str:
        nonlocal applied
        phrase = m.group(0)
        options = CLICHE_PHRASES.get(phrase.lower())
        if not options or rng.random() > prob:
            return phrase
        choice = rng.choice(options)
        applied = True
        if choice is None:
            return ""
        if phrase[:1].isupper():
            choice = choice[:1].upper() + choice[1:]
        return choice

    new_sentence = _CLICHE_PATTERN.sub(repl, sentence)
    if not applied:
        return sentence, False
    # a deleted phrase can leave double spaces or a leading space behind
    new_sentence = re.sub(r" {2,}", " ", new_sentence).strip()
    if new_sentence and sentence[:1].isupper():
        new_sentence = new_sentence[:1].upper() + new_sentence[1:]
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


def _maybe_merge_sentences(sentences: List[str], rng: random.Random, prob: float, word_threshold: int = 7) -> Tuple[List[str], bool]:
    if prob <= 0 or len(sentences) < 2:
        return sentences, False
    result: List[str] = []
    applied = False
    i = 0
    while i < len(sentences):
        current = sentences[i]
        if i + 1 < len(sentences) and _word_count(current) <= word_threshold and _word_count(sentences[i + 1]) <= word_threshold and rng.random() < prob:
            nxt = sentences[i + 1]
            current_stripped = current.rstrip()
            body = current_stripped[:-1] if current_stripped and current_stripped[-1] in ".!?" else current_stripped
            nxt_stripped = nxt.strip()
            nxt_body = (nxt_stripped[:1].lower() + nxt_stripped[1:]) if nxt_stripped else nxt_stripped
            # vary the joiner instead of always using a comma - a page full of
            # comma-spliced merges is its own kind of uniform/robotic pattern
            roll = rng.random()
            joiner = "; " if roll < 0.20 else (" y " if roll < 0.35 else ", ")
            result.append(f"{body}{joiner}{nxt_body}")
            applied = True
            i += 2
        else:
            result.append(current)
            i += 1
    return result, applied


def _maybe_split_sentences(sentences: List[str], rng: random.Random, prob: float, long_threshold: int = 28) -> Tuple[List[str], bool]:
    if prob <= 0:
        return sentences, False
    result: List[str] = []
    applied = False
    for s in sentences:
        if _word_count(s) > long_threshold and rng.random() < prob:
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
    applied = {"cliche": False, "synonym": False, "connector": False, "merge": False, "split": False, "passive": False}

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
                new_line, cli_applied = _apply_cliches(line, rng, params["cliche_p"])
                new_line, syn_applied = _apply_synonyms(new_line, rng, params["synonym_p"])
                applied["cliche"] = applied["cliche"] or cli_applied
                applied["synonym"] = applied["synonym"] or syn_applied
                new_lines.append(new_line)
            out_paragraphs.append("\n".join(new_lines))
            continue

        sentences = [s for s in _SENTENCE_SPLIT_RE.split(paragraph.strip()) if s]
        transformed = []
        for idx, sentence in enumerate(sentences):
            s, cli_applied = _apply_cliches(sentence, rng, params["cliche_p"])
            s, syn_applied = _apply_synonyms(s, rng, params["synonym_p"])
            s, con_applied = _maybe_insert_connector(s, rng, params["connector_p"], is_first=(idx == 0))
            s, pas_applied = _maybe_passive_to_active(s, rng, params["passive_p"])
            applied["cliche"] = applied["cliche"] or cli_applied
            applied["synonym"] = applied["synonym"] or syn_applied
            applied["connector"] = applied["connector"] or con_applied
            applied["passive"] = applied["passive"] or pas_applied
            transformed.append(s)

        transformed, merge_applied = _maybe_merge_sentences(
            transformed, rng, params["merge_p"], int(params.get("merge_threshold", 7))
        )
        applied["merge"] = applied["merge"] or merge_applied
        transformed, split_applied = _maybe_split_sentences(
            transformed, rng, params["split_p"], int(params.get("split_threshold", 28))
        )
        applied["split"] = applied["split"] or split_applied

        out_paragraphs.append(" ".join(transformed))

    return "\n\n".join(out_paragraphs), applied


def _describe_changes(applied: Dict[str, bool], intensity: str) -> List[str]:
    changes: List[str] = []
    if applied.get("cliche"):
        changes.append("Se han quitado o reformulado frases hechas típicas de IA (p. ej. «es importante destacar», «en resumen», «es crucial»).")
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


# ---------------------------------------------------------------------------
# Code comment humanizer. Rewrites ONLY comments - code, strings, identifiers
# and structure are byte-for-byte identical in the output. Anything the
# scanner can't confidently classify as a comment (e.g. a marker sequence
# sitting inside a multi-line string it doesn't track) is left untouched.
# ---------------------------------------------------------------------------

_LANGUAGE_COMMENT_SYNTAX: Dict[str, Dict[str, object]] = {
    "python":     {"line": "#",  "block": None},
    "ruby":       {"line": "#",  "block": None},
    "shell":      {"line": "#",  "block": None},
    "yaml":       {"line": "#",  "block": None},
    "javascript": {"line": "//", "block": ("/*", "*/")},
    "typescript": {"line": "//", "block": ("/*", "*/")},
    "java":       {"line": "//", "block": ("/*", "*/")},
    "c":          {"line": "//", "block": ("/*", "*/")},
    "cpp":        {"line": "//", "block": ("/*", "*/")},
    "csharp":     {"line": "//", "block": ("/*", "*/")},
    "go":         {"line": "//", "block": ("/*", "*/")},
    "php":        {"line": "//", "block": ("/*", "*/")},
    "rust":       {"line": "//", "block": ("/*", "*/")},
    "swift":      {"line": "//", "block": ("/*", "*/")},
    "kotlin":     {"line": "//", "block": ("/*", "*/")},
    "css":        {"line": None, "block": ("/*", "*/")},
    "sql":        {"line": "--", "block": ("/*", "*/")},
    "html":       {"line": None, "block": ("<!--", "-->")},
    "xml":        {"line": None, "block": ("<!--", "-->")},
}

_EXTENSION_TO_LANGUAGE: Dict[str, str] = {
    "py": "python", "rb": "ruby", "sh": "shell", "bash": "shell", "yml": "yaml", "yaml": "yaml",
    "js": "javascript", "jsx": "javascript", "mjs": "javascript", "cjs": "javascript",
    "ts": "typescript", "tsx": "typescript",
    "java": "java", "c": "c", "h": "c", "cpp": "cpp", "cc": "cpp", "hpp": "cpp",
    "cs": "csharp", "go": "go", "php": "php", "rs": "rust", "swift": "swift", "kt": "kotlin",
    "css": "css", "scss": "css", "sql": "sql", "html": "html", "htm": "html", "xml": "xml",
}

# Formal, textbook-y comment openers -> what an actual dev would jot down.
# Longest keys first so "esta función se encarga de" wins over "esta función".
_FORMAL_COMMENT_STARTERS: Dict[str, List[str]] = {
    # these three keep the infinitive that follows ("...se encarga de calcular X"),
    # so the replacement has to work as "REPLACEMENT calcular X" - keep it that way
    "esta función se encarga de": ["esto sirve para", "la idea es"],
    "este método se encarga de": ["esto sirve para", "la idea es"],
    "esta clase se encarga de": ["la idea de esta clase es", "esto sirve para"],
    "esta función": ["esto"],
    "este método": ["esto"],
    "nota importante:": ["ojo:"],
    "nota:": ["ojo:"],
    "observación:": ["ojo:"],
    "importante:": ["ojo:"],
    "atención:": ["ojo:"],
    "this function is responsible for": ["this"],
    "this method is responsible for": ["this"],
    "note:": ["heads up:"],
    "important:": ["heads up:"],
}
_FORMAL_STARTER_KEYS = sorted(_FORMAL_COMMENT_STARTERS.keys(), key=len, reverse=True)


def _guess_language(code: str) -> str:
    """Best-effort sniff for the 'auto' case. Falls back to javascript
    (curly-brace family) since that covers the most common ambiguous cases."""
    sample = code[:2000]
    if re.search(r"^\s*#!.*python", sample) or re.search(r"\bdef \w+\(.*\):", sample) or re.search(r"^\s*(import|from)\s+\w+", sample, re.MULTILINE):
        return "python"
    if re.search(r"<\?php", sample):
        return "php"
    if re.search(r"<!DOCTYPE html>|<html[\s>]", sample, re.IGNORECASE):
        return "html"
    if "public class" in sample or re.search(r"^\s*package\s+[\w.]+;", sample, re.MULTILINE):
        return "java"
    if re.search(r"\bfn \w+\(", sample) and "->" in sample:
        return "rust"
    if re.search(r"^\s*package\s+\w+", sample, re.MULTILINE) and re.search(r"\bfunc \w+\(", sample):
        return "go"
    if re.search(r"\b(SELECT|INSERT INTO|UPDATE|DELETE FROM)\b", sample, re.IGNORECASE):
        return "sql"
    return "javascript"


def resolve_language(language: Optional[str], filename: Optional[str], code: str) -> str:
    if language and language.lower() != "auto" and language.lower() in _LANGUAGE_COMMENT_SYNTAX:
        return language.lower()
    if filename and "." in filename:
        ext = filename.rsplit(".", 1)[-1].lower()
        if ext in _EXTENSION_TO_LANGUAGE:
            return _EXTENSION_TO_LANGUAGE[ext]
    return _guess_language(code)


def _scan_line_for_comment(line: str, line_marker: Optional[str], block_start: Optional[str]):
    """Walk a line (assumed to start OUTSIDE a comment) tracking string
    state, and report the first comment marker found outside any string.
    Returns (kind, index) with kind in {"line", "block", None}."""
    in_string: Optional[str] = None
    i, n = 0, len(line)
    while i < n:
        ch = line[i]
        if in_string:
            if ch == "\\":
                i += 2
                continue
            if ch == in_string:
                in_string = None
            i += 1
            continue
        if ch in ("'", '"', "`"):
            in_string = ch
            i += 1
            continue
        if line_marker and line[i:i + len(line_marker)] == line_marker:
            return "line", i
        if block_start and line[i:i + len(block_start)] == block_start:
            return "block", i
        i += 1
    return None, -1


def _humanize_comment_text(body: str, rng: random.Random, params: Dict[str, float]) -> Tuple[str, bool]:
    """Casualize the text of a single comment (marker already stripped)."""
    m = re.match(r"^(\s*)(.*?)(\s*)$", body, re.DOTALL)
    indent, core, trail = m.group(1), m.group(2), m.group(3)
    if not core:
        return body, False

    applied = False
    core, cli_applied = _apply_cliches(core, rng, params["cliche_p"])
    applied = applied or cli_applied
    core, syn_applied = _apply_synonyms(core, rng, params["synonym_p"] * 0.6)
    applied = applied or syn_applied

    core_lower = core.lower()
    for key in _FORMAL_STARTER_KEYS:
        if core_lower.startswith(key) and rng.random() < 0.6:
            choice = rng.choice(_FORMAL_COMMENT_STARTERS[key])
            rest = core[len(key):]
            if choice and rest and not rest.startswith((" ", ",", ":")):
                choice += " "
            core = choice + rest
            applied = True
            break

    # devs rarely end a quick comment with a period, and rarely bother
    # capitalizing it like a sentence out of a manual
    if core.endswith(".") and not core.endswith("..."):
        if rng.random() < 0.5:
            core = core[:-1]
            applied = True
    first_word = core.split(" ", 1)[0] if core else ""
    if core[:1].isupper() and first_word and not first_word.isupper() and rng.random() < 0.4:
        core = core[:1].lower() + core[1:]
        applied = True

    return f"{indent}{core}{trail}", applied


def _describe_code_changes(changed: bool, language: str, intensity: str) -> List[str]:
    changes: List[str] = []
    if changed:
        changes.append(
            "Se reescribieron algunos comentarios para que suenen a anotaciones rápidas de "
            "un desarrollador real, no a texto formal/genérico."
        )
    else:
        changes.append(
            "No se detectaron comentarios que modificar para el lenguaje usado, o el código no tenía comentarios."
        )
    changes.append(
        f"Lenguaje: {language}. Intensidad: {intensity}. El código en sí (lógica, nombres, arquitectura, "
        "funcionalidad) no se toca en ningún caso - solo se reescribe el texto dentro de los comentarios."
    )
    return changes


def humanize_code_comments(
    code: str,
    language: str = "auto",
    intensity: str = "medium",
    filename: Optional[str] = None,
) -> Tuple[str, List[str], str]:
    """Rewrite only the comments in a code snippet, leaving code lines,
    string literals, identifiers and structure byte-for-byte identical.
    Deterministic like humanize_text_with_changes."""
    if intensity not in INTENSITIES:
        raise ValueError(f"intensity must be one of {INTENSITIES}, got {intensity!r}")
    if not code.strip():
        return code, ["El código está vacío; no se aplicó ningún cambio."], "unknown"

    resolved_lang = resolve_language(language, filename, code)
    syntax = _LANGUAGE_COMMENT_SYNTAX.get(resolved_lang, {"line": "//", "block": ("/*", "*/")})
    line_marker = syntax.get("line")
    block = syntax.get("block")
    block_start, block_end = block if block else (None, None)

    seed = _seed_for(code, f"code::{intensity}")
    rng = random.Random(seed)
    params = _INTENSITY_PARAMS[intensity]
    changed = False

    out_lines: List[str] = []
    in_block = False

    for line in code.split("\n"):
        if in_block:
            end_idx = line.find(block_end) if block_end else -1
            if end_idx == -1:
                new_comment, did = _humanize_comment_text(line, rng, params)
                changed = changed or did
                out_lines.append(new_comment)
                continue
            comment_part, rest = line[:end_idx], line[end_idx + len(block_end):]
            new_comment, did = _humanize_comment_text(comment_part, rng, params)
            changed = changed or did
            out_lines.append(f"{new_comment}{block_end}{rest}")
            in_block = False
            continue

        kind, idx = _scan_line_for_comment(line, line_marker, block_start)
        if kind == "line":
            code_part, comment_part = line[:idx], line[idx + len(line_marker):]
            new_comment, did = _humanize_comment_text(comment_part, rng, params)
            changed = changed or did
            out_lines.append(f"{code_part}{line_marker}{new_comment}")
        elif kind == "block":
            code_part = line[:idx]
            after = line[idx + len(block_start):]
            end_idx = after.find(block_end) if block_end else -1
            if end_idx == -1:
                new_comment, did = _humanize_comment_text(after, rng, params)
                changed = changed or did
                out_lines.append(f"{code_part}{block_start}{new_comment}")
                in_block = True
            else:
                comment_part, rest = after[:end_idx], after[end_idx + len(block_end):]
                new_comment, did = _humanize_comment_text(comment_part, rng, params)
                changed = changed or did
                out_lines.append(f"{code_part}{block_start}{new_comment}{block_end}{rest}")
        else:
            out_lines.append(line)

    result = "\n".join(out_lines)
    changes = _describe_code_changes(changed, resolved_lang, intensity)
    return result, changes, resolved_lang
