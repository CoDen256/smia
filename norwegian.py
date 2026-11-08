"""
norwegian.py — the service's Norwegian query-preparation layer. Lives at
the repo root, beside `cache.py`/`registry.py` (design D6), because it is
consumed by several adapters and, eventually, by a route — it registers no
provider of its own.

Preparation here is additive by contract: every function returns extra
variants or a derived form alongside the caller's original, never a
replacement. No function here decides what the caller "really" meant —
that decision is left to provider data (design.md D1).
"""

from __future__ import annotations

import re

_PREFIXES = {"en", "ei", "et", "å"}


def strip_article_prefix(text: str) -> str | None:
    """Strips the leading Norwegian indefinite article or infinitive
    marker, returning the remainder, when the input has 2+ whitespace
    tokens and the first token case-insensitively matches one of
    `en`/`ei`/`et`/`å` (design D2). Returns `None` otherwise — in
    particular, never strips a bare one-token input, since both `å` and
    `en` are themselves standalone Norwegian nouns."""
    tokens = text.split()
    if len(tokens) < 2:
        return None
    if tokens[0].lower() not in _PREFIXES:
        return None
    return text.split(maxsplit=1)[1]


def query_variants(text: str) -> list[str]:
    """The cross product of as-given/prefix-stripped x as-given/lowercased,
    flattened original-first and deduplicated preserving first occurrence
    (design D1/D3). The caller's original string is always the first
    element."""
    bases = [text]
    stripped = strip_article_prefix(text)
    if stripped is not None:
        bases.append(stripped)

    variants = []
    for base in bases:
        variants.append(base)
        lowered = base.lower()
        if lowered != base:
            variants.append(lowered)

    seen: set[str] = set()
    result = []
    for variant in variants:
        if variant not in seen:
            seen.add(variant)
            result.append(variant)
    return result


_TOKEN_PUNCT_RE = re.compile(r'^[.,!?:;\'"“”‘’()\[\]{}]+|[.,!?:;\'"“”‘’()\[\]{}]+$')


def tokenize(text: str) -> list[str]:
    """Splits a Norwegian phrase into lookup tokens (design D8): whitespace
    split, leading/trailing punctuation stripped per token, hyphenated
    compounds kept whole, digit-only and empty tokens dropped. Does **not**
    apply `strip_article_prefix` — composing the two is the caller's
    choice."""
    tokens = []
    for raw in text.split():
        cleaned = _TOKEN_PUNCT_RE.sub("", raw)
        if not cleaned or cleaned.isdigit():
            continue
        tokens.append(cleaned)
    return tokens


_ANNOTATION_RE = re.compile(r"[\{\[][^}\]]*[\}\]]")


def strip_infinitive_marker(phrase: str) -> str:
    """Strips the leading `å ` infinitive marker, if present. Re-expressed
    in terms of `strip_article_prefix` (design D7) and restricted to `å` so
    that dict.cc's non-infinitive article phrases (e.g. `"en gang"`) are
    left untouched by this dict.cc-facing helper."""
    stripped = strip_article_prefix(phrase)
    if stripped is None:
        return phrase
    if phrase.split()[0].lower() != "å":
        return phrase
    return stripped


def normalize_dictcc_phrase(phrase: str) -> str:
    """For comparing a dict.cc source-language field against the bare query
    word: strips grammar annotations dict.cc appends to the word itself
    (`"kalv {m}"` -> `"kalv"`) and the verb infinitive marker (`"å komme"`
    -> `"komme"`), so a direct word match isn't mistaken for a distinct
    phrase just because of that annotation/marker."""
    return strip_infinitive_marker(_ANNOTATION_RE.sub("", phrase).strip()).strip().lower()


def display_dictcc_phrase(phrase: str) -> str:
    """For showing a source phrase as context: only strips the infinitive
    marker (annotations like "{m}" are kept — they're part of what's
    actually being displayed, unlike in `normalize_dictcc_phrase`)."""
    return strip_infinitive_marker(phrase)
