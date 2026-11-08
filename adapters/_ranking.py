"""
adapters/_ranking.py — shared candidate ranking for the two `/examples`
corpus adapters (`tatoeba`, `leipzig`), per examples-api design D5.

A query like `komme` can match 38,130 Leipzig rows while at most 10 are
ever returned, so which few come back is the whole capability. The rule,
in descending weight: sentence length (peaking around 8 words, usable in
5-15 — the single strongest signal, see design D5's measured before/after);
looking syntactically complete (capital start, sentence-final punctuation);
fewer capitalised tokens after the first (named-entity proxy); fewer
digits (strips embedded timestamps). Two things are rejected outright
rather than merely penalised: a URL, or an internal sentence boundary
(the corpora's 0.7-1.7% multi-sentence lines).

Tie-breaking is a hash of `(sentence_id, query)`, deliberately NOT row
order — the corpora are roughly alphabetically ordered, and row-order
tie-breaking was directly observed to return all-same-initial-letter
top-3 sets. The same hash also orders the SQL pre-fetch (see
`PRE_RANK_FETCH_CAP` below and its callers), so the bounded sample handed
to this module is itself already free of alphabetical bias, not just the
final tie-break.
"""

from __future__ import annotations

import hashlib
import re

# Bounds how many matching rows the adapters pull into Python before
# ranking — large enough that a common word's ranking still has real
# choice (design task 4.7), small enough that a 38k-row match (e.g.
# "komme") doesn't pull every row across the wire on every request.
PRE_RANK_FETCH_CAP = 2000

_URL_RE = re.compile(r"https?://|www\.", re.IGNORECASE)
# "internal sentence boundary": [.!?] + whitespace + a capital letter,
# indicating the line actually holds more than one sentence. A sentence's
# own trailing punctuation never matches this (nothing follows it).
_INTERNAL_BOUNDARY_RE = re.compile(r"[.!?]\s+[A-ZÆØÅ]")
_SENTENCE_FINAL_RE = re.compile(r"[.!?]\s*$")
_DIGIT_RE = re.compile(r"\d")


def _is_excluded(text: str) -> bool:
    return bool(_URL_RE.search(text) or _INTERNAL_BOUNDARY_RE.search(text))


def _length_score(word_count: int) -> float:
    # Peaks at 8 words; a mild slope inside the 5-15 "usable" band, a much
    # steeper one outside it — this is what separates a 7-word sentence
    # from a 19-29 word one, the gap design D5 measured as decisive.
    if 5 <= word_count <= 15:
        return -abs(word_count - 8) * 1.0
    return -abs(word_count - 8) * 3.0


def _shape_score(text: str) -> float:
    score = 0.0
    if text[:1].isupper():
        score += 3.0
    if _SENTENCE_FINAL_RE.search(text):
        score += 3.0
    return score


def _penalty_score(text: str) -> float:
    tokens = text.split()
    capital_penalty = sum(1 for t in tokens[1:] if t[:1].isupper()) * 2.0
    digit_penalty = sum(1 for t in tokens if _DIGIT_RE.search(t)) * 3.0
    return -(capital_penalty + digit_penalty)


def _tie_break(sentence_id: int, query: str) -> str:
    return hashlib.sha256(f"{sentence_id}:{query}".encode("utf-8")).hexdigest()


def rank_candidates(rows, query: str, limit: int) -> list[dict]:
    """`rows` is an iterable of `(id, corpus, text, word_count)`. Returns at
    most `limit` `{text, source}` candidates, highest-ranked first."""
    scored = []
    for sentence_id, corpus, text, word_count in rows:
        if _is_excluded(text):
            continue
        score = _length_score(word_count) + _shape_score(text) + _penalty_score(text)
        scored.append((score, _tie_break(sentence_id, query), corpus, text))

    scored.sort(key=lambda c: (-c[0], c[1]))
    return [{"text": text, "source": corpus} for _score, _tie, corpus, text in scored[:limit]]
