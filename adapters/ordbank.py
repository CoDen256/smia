"""
adapters/ordbank.py — the `ordbank` /inflections provider: a reverse
lookup against the imported Norsk Ordbank tables (D-S4: a provider can be a
query against an imported dataset, not just a live call).

## Reverse lookup (task 3.2)

A surface form (`OPPSLAG`) can appear in `ordbank_fullform` under more than
one `(lemma_id, paradigme_id)` pair — e.g. `skinner` matches both a verb
lemma (two alternative paradigms, 021/204) and a noun lemma (masc./fem.
gender variants, paradigms 702/902). Each distinct pair becomes one
candidate; building a candidate means fetching *every* fullform row for
that pair (not just the one that matched the query) so e.g. a noun
candidate's `sg_indef`/`sg_def`/`pl_indef`/`pl_def` are all populated, not
only whichever slot `skinner` itself filled.

## Paradigm shape mapping (task 3.3)

`BOY_GRUPPE` (the inflection-class group on `ordbank_paradigme`) decides
both the candidate's `pos` and which of that group's slots (named by
`ordbank_boying.ordbok_tekst`) map onto the output shape's keys. This table
is hand-derived from the actual exported data (`boying.txt`/`paradigme.txt`
— see openspec's design.md and this change's exploration), not guessed:
every `BOY_GRUPPE`/`ORDBOK_TEKST` pair below was confirmed present in the
2022-02-01 export. Slots with no entry here (e.g. a noun's definite-plural-
article refinements, a verb's imperative/participle forms) are simply not
part of the required output shape and are dropped — matching the spec's
"exactly these keys" requirement for each pos.

`adjektiv, adverbtype` paradigms map to pos `adverb` (not `adjektiv`) per
the inflect-api spec: an adjective that also functions as its own adverb,
inflecting for degree (`fort`/`fortere`/`fortest`). Plain `adverb`-group
paradigms are invariable — shape has only `form`.
"""

from __future__ import annotations

from sqlalchemy import text

from db.session import session_scope
from registry import registry

# BOY_GRUPPE -> (pos, {ordbok_tekst: output_key})
_SLOT_MAPS: dict[str, tuple[str, dict[str, str]]] = {
    "substantiv": ("substantiv", {
        "entall_ubestemt": "sg_indef",
        "entall_bestemt": "sg_def",
        "flertall_ubestemt": "pl_indef",
        "flertall_bestemt": "pl_def",
    }),
    "verb, normal": ("verb", {
        "infinitiv": "infinitiv",
        "presens": "presens",
        "preteritum": "preteritum",
        "supinum": "perfektum",
    }),
    "verb, s-verb": ("verb", {
        "infinitiv": "infinitiv",
        "presens": "presens",
        "preteritum": "preteritum",
        "supinum": "perfektum",
    }),
    "adjektiv": ("adjektiv", {
        "entall_hanhun": "positiv",
        "entall_intet": "nøytrum",
        "flertall": "flertall",
        "grad_komparativ": "komparativ",
        "grad_superlativ": "superlativ",
    }),
    "adjektiv, ulik m/f": ("adjektiv", {
        "entall_han": "positiv",
        "entall_intet": "nøytrum",
        "flertall": "flertall",
        "grad_komparativ": "komparativ",
        "grad_sup": "superlativ",
    }),
    "adjektiv, adverbtype": ("adverb", {
        "grad_pos": "form",
        "grad_komparativ": "komparativ",
        "grad_superlativ": "superlativ",
    }),
    "adverb": ("adverb", {
        "adv": "form",
    }),
}

# ORDKLASSE substrings -> substantiv `article`, in priority order (checked
# before the plain "subst appell"/"subst prop" fallback).
_GENDER_ARTICLES = (
    ("mask", "en"),
    ("fem", "ei"),
    ("nøyt", "et"),
)


def _article_for(ordklasse: str) -> str:
    for marker, article in _GENDER_ARTICLES:
        if marker in ordklasse:
            return article
    return "en"  # unspecified/common gender (e.g. plain "subst appell", "subst prop")


def _pos_for(ordklasse: str) -> str:
    """Fallback `pos` label for word classes with no inflection shape
    (pronomen, determinativ, preposisjon, ...) — the first ORDKLASSE token,
    since there's no single canonical Norwegian name for most of these."""
    return ordklasse.split(" ")[0]


class OrdbankAdapter:
    def lookup(self, input_dict: dict) -> dict:
        word = input_dict["word"]
        with session_scope() as db:
            pairs = db.execute(
                text(
                    """
                    SELECT DISTINCT lemma_id, paradigme_id
                    FROM ordbank_fullform
                    WHERE oppslag = :word
                    """
                ),
                {"word": word},
            ).all()

            candidates = []
            for lemma_id, paradigme_id in pairs:
                candidate = self._build_candidate(db, lemma_id, paradigme_id)
                if candidate is not None:
                    candidates.append(candidate)

        return {"candidates": candidates}

    def _build_candidate(self, db, lemma_id, paradigme_id):
        lemma_row = db.execute(
            text("SELECT grunnform FROM ordbank_lemma WHERE lemma_id = :id"), {"id": lemma_id}
        ).first()
        paradigme_row = db.execute(
            text("SELECT boy_gruppe, ordklasse FROM ordbank_paradigme WHERE paradigme_id = :id"),
            {"id": paradigme_id},
        ).first()
        if lemma_row is None or paradigme_row is None:
            return None
        grunnform = lemma_row[0]
        boy_gruppe, ordklasse = paradigme_row

        mapping = _SLOT_MAPS.get(boy_gruppe)
        if mapping is None:
            return {"lemma": grunnform, "pos": _pos_for(ordklasse), "paradigm": {}}
        pos, slot_to_key = mapping

        form_rows = db.execute(
            text(
                """
                SELECT ff.boy_nummer, b.ordbok_tekst, ff.oppslag
                FROM ordbank_fullform ff
                JOIN ordbank_boying b ON b.boy_gruppe = :boy_gruppe AND b.boy_nummer = ff.boy_nummer
                WHERE ff.lemma_id = :lemma_id AND ff.paradigme_id = :paradigme_id
                """
            ),
            {"boy_gruppe": boy_gruppe, "lemma_id": lemma_id, "paradigme_id": paradigme_id},
        ).all()

        paradigm = {}
        for _boy_nummer, ordbok_tekst, oppslag in form_rows:
            key = slot_to_key.get(ordbok_tekst)
            if key is not None:
                paradigm[key] = oppslag

        if pos == "substantiv":
            paradigm = {"article": _article_for(ordklasse), **paradigm}

        return {"lemma": grunnform, "pos": pos, "paradigm": paradigm}


registry.register("inflections", "ordbank", OrdbankAdapter())
