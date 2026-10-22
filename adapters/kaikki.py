"""
adapters/kaikki.py — the `kaikki` /inflections provider, reading the
imported kaikki.org/Wiktionary dump (`kaikki_entry.forms`, already filtered
of `imperative`/`passive`-tagged entries at import time — see
scripts/import_kaikki.py). Secondary to `ordbank`; the two providers are
never merged (open question in design.md resolved: each provider returns
its own candidates independently per the lookup-cache "one provider per
request" contract).

Tag-to-shape mapping is derived from inspecting the actual dump (`forms[]`
tag combinations really present in the Norwegian Bokmål export), same
spirit as `adapters/ordbank.py`'s `_SLOT_MAPS`. `positiv`/`sg_indef`/
`infinitiv`/adverb `form` default to the entry's bare `word` — kaikki only
lists forms[] entries for *deviations* from the headword, so the
indefinite-singular/infinitive/positive/base form is implicit, not a
separate forms[] row, except for a few irregular entries.
"""

from __future__ import annotations

from sqlalchemy import text

from db.session import session_scope
from registry import registry

_ARTICLE_FOR_GENDER = {"m": "en", "f": "ei", "n": "et"}


def _matching_forms(forms: list[dict], *, has_all: set[str] = frozenset(), has_none: set[str] = frozenset()) -> str | None:
    """Joins every form matching the given tags with " / " — kaikki can
    legitimately list more than one surface form under the same tag set
    (e.g. "hus"'s definite plural has both "husa" and "husene", two forms
    both tagged definite+plural). Taking only the first silently dropped
    the second until this was reported; " / " matches dict.cc's own
    convention for the same kind of same-slot alternate (see
    adapters/dictcc_api.py)."""
    values = []
    for f in forms:
        tags = set(f.get("tags", []))
        if has_all <= tags and not (has_none & tags):
            value = f.get("form")
            if value and value not in values:
                values.append(value)
    return " / ".join(values) if values else None


def _build_noun(word: str, gender: str | None, forms: list[dict]) -> dict:
    paradigm = {"article": _ARTICLE_FOR_GENDER.get(gender, "en")}
    sg_indef = _matching_forms(forms, has_all={"indefinite", "singular"}) or word
    paradigm["sg_indef"] = sg_indef
    sg_def = _matching_forms(forms, has_all={"definite", "singular"}, has_none={"plural"})
    if sg_def:
        paradigm["sg_def"] = sg_def
    pl_indef = _matching_forms(forms, has_all={"indefinite", "plural"})
    if pl_indef:
        paradigm["pl_indef"] = pl_indef
    pl_def = _matching_forms(forms, has_all={"definite", "plural"})
    if pl_def:
        paradigm["pl_def"] = pl_def
    return paradigm


def _build_verb(word: str, forms: list[dict]) -> dict:
    paradigm = {"infinitiv": word}
    presens = _matching_forms(forms, has_all={"present"})
    if presens:
        paradigm["presens"] = presens
    preteritum = _matching_forms(forms, has_all={"past"}, has_none={"participle"})
    if preteritum:
        paradigm["preteritum"] = preteritum
    perfektum = _matching_forms(forms, has_all={"participle", "past"})
    if perfektum:
        paradigm["perfektum"] = perfektum
    return paradigm


def _build_adjektiv(word: str, forms: list[dict]) -> dict:
    paradigm = {"positiv": word}
    noeytrum = _matching_forms(forms, has_all={"neuter"})
    if noeytrum:
        paradigm["nøytrum"] = noeytrum
    flertall = _matching_forms(forms, has_all={"definite"})
    if flertall:
        paradigm["flertall"] = flertall
    komparativ = _matching_forms(forms, has_all={"comparative"})
    if komparativ:
        paradigm["komparativ"] = komparativ
    superlativ = _matching_forms(forms, has_all={"superlative"})
    if superlativ:
        paradigm["superlativ"] = superlativ
    return paradigm


def _build_adverb(word: str, forms: list[dict]) -> dict:
    paradigm = {"form": word}
    komparativ = _matching_forms(forms, has_all={"comparative"})
    if komparativ:
        paradigm["komparativ"] = komparativ
    superlativ = _matching_forms(forms, has_all={"superlative"})
    if superlativ:
        paradigm["superlativ"] = superlativ
    return paradigm


_BUILDERS = {
    "noun": ("substantiv", _build_noun),
    "verb": ("verb", _build_verb),
    "adj": ("adjektiv", _build_adjektiv),
    "adv": ("adverb", _build_adverb),
}


class KaikkiAdapter:
    def lookup(self, input_dict: dict) -> dict:
        word = input_dict["word"]
        # Reverse lookup must match either the headword itself or any
        # inflected surface form kaikki lists under it — kaikki only
        # records forms[] entries that *differ* from the headword, so a
        # plain `word = :word` would miss every inflected query (e.g.
        # "skinner" only shows up inside "skinne"'s forms[], never as its
        # own kaikki_entry.word).
        with session_scope() as db:
            rows = db.execute(
                text(
                    """
                    SELECT e.word, e.pos, e.gender, e.forms
                    FROM kaikki_entry e
                    WHERE e.word = :word
                       OR EXISTS (
                           SELECT 1 FROM jsonb_array_elements(e.forms) f
                           WHERE f->>'form' = :word
                       )
                    """
                ),
                {"word": word},
            ).all()

        candidates = []
        for w, pos, gender, forms in rows:
            mapping = _BUILDERS.get(pos)
            if mapping is None:
                candidates.append({"lemma": w, "pos": pos, "paradigm": {}})
                continue
            shape_pos, builder = mapping
            paradigm = builder(w, gender, forms) if pos == "noun" else builder(w, forms)
            candidates.append({"lemma": w, "pos": shape_pos, "paradigm": paradigm})

        return {"candidates": candidates}


registry.register("inflections", "kaikki", KaikkiAdapter())
