from __future__ import annotations

import re
import unicodedata


# Common BiH/HR/SR + English stopwords ignored when comparing headlines.
_STOPWORDS = {
    "u", "i", "na", "je", "su", "se", "za", "od", "do", "o", "a", "da", "ne", "li", "s", "sa",
    "ka", "ko", "te", "ali", "pa", "ili", "nije", "bi", "po", "uz", "iz", "kao", "sto", "the",
    "of", "in", "to", "and", "jos", "vec", "si", "ce", "sve", "koji", "koja", "koje", "nakon",
}

# Crude case/verb suffixes, longest first, stripped to fold inflected forms together.
_SUFFIXES = (
    "ovima", "evima", "anje", "enje", "ima", "ama", "oga", "ega", "iju",
    "eo", "ao", "la", "le", "li", "lo", "og", "eg", "om", "em", "im", "ih", "ju",
    "a", "e", "i", "o", "u",
)


def normalize(text: str | None) -> str:
    if not text:
        return ""
    folded = (
        unicodedata.normalize("NFKD", text)
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )
    return re.sub(r"\s+", " ", folded).strip()


def _stem(word: str) -> str:
    for suffix in _SUFFIXES:
        if len(word) - len(suffix) >= 3 and word.endswith(suffix):
            return word[: len(word) - len(suffix)]
    return word


def title_tokens(title: str) -> set[str]:
    """Reduce a headline to a set of significant stems for fuzzy comparison."""
    parts = [p for p in re.split(r"[^a-z0-9]+", normalize(title)) if p]
    tokens: set[str] = set()
    for part in parts:
        if part in _STOPWORDS:
            continue
        if len(part) < 3 and not part.isdigit():
            continue
        tokens.add(part if part.isdigit() else _stem(part))
    return tokens


def is_duplicate(tokens: set[str], seen: list[set[str]], threshold: float = 0.4) -> bool:
    """True if these tokens overlap any already-seen headline by >= threshold (Jaccard)."""
    if not tokens:
        return False
    for other in seen:
        if not other:
            continue
        intersection = len(tokens & other)
        union = len(tokens) + len(other) - intersection
        if union > 0 and intersection / union >= threshold:
            return True
    return False
