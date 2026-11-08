"""
adapters/_form_expansion.py — shared helper for the two `/examples` corpus
adapters (`tatoeba`, `leipzig`): expands a queried word into every surface
form of its lemma(s), via `ordbank_fullform` (the same table
`adapters/ordbank.py` already walks for `/inflections`), per examples-api
design D3/D-task-3.1.

This is the load-bearing piece of the "simple config + ordbank-driven
expansion" decision: `corpus_sentence.tsv` is indexed with no stemming (see
`db/models.py`'s `CorpusSentence` docstring), so a query for `komme` would
otherwise never match a sentence containing `kom` — expansion is what
finds it instead.
"""

from __future__ import annotations

from sqlalchemy import text


def surface_forms(db, word: str) -> list[str]:
    """Every surface form sharing a lemma with `word`, including `word`
    itself. Falls back to `[word]` alone when `word` is absent from
    `ordbank_fullform` (proper nouns, loanwords, compounds Ordbank doesn't
    list) — a narrower result, never an error (design D3's fallback)."""
    lemma_ids = db.execute(
        text("SELECT DISTINCT lemma_id FROM ordbank_fullform WHERE oppslag = :word"),
        {"word": word},
    ).scalars().all()
    if not lemma_ids:
        return [word]

    forms = db.execute(
        text("SELECT DISTINCT oppslag FROM ordbank_fullform WHERE lemma_id = ANY(:lemma_ids)"),
        {"lemma_ids": list(lemma_ids)},
    ).scalars().all()
    return sorted(set(forms) | {word})


def to_tsquery_or(forms: list[str]) -> str:
    """Builds the `to_tsquery('simple', …)` input string as an OR of every
    form, each single-quoted and with embedded quotes doubled (to_tsquery's
    own string-literal escaping convention) so a form containing an
    apostrophe can't break out of its lexeme."""
    escaped = [f"""'{form.replace("'", "''")}'""" for form in forms]
    return " | ".join(escaped)
