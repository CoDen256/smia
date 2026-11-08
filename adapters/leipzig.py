"""
adapters/leipzig.py — the `leipzig` `/examples` provider: ONE provider
spanning its three constituent corpora (`web_2020`, `news_2013`,
`wikipedia_2014`), per examples-api design D2 — the same "one provider,
several varieties tagged per-candidate" pattern `adapters/nst.py` already
uses for its five dialect areas. A single lookup queries all three corpora
in **one SQL statement** (design D2's explicit consequence), not three,
and ranks across them together — the returned candidates may come from
different corpora, chosen by rank rather than by corpus precedence.
"""

from __future__ import annotations

from sqlalchemy import text

from adapters._form_expansion import surface_forms, to_tsquery_or
from adapters._ranking import PRE_RANK_FETCH_CAP, rank_candidates
from db.session import session_scope
from registry import registry

_CORPORA = ("web_2020", "news_2013", "wikipedia_2014")


class LeipzigAdapter:
    def lookup(self, input_dict: dict) -> dict:
        word = input_dict["text"]
        limit = input_dict.get("limit", 3)

        with session_scope() as db:
            forms = surface_forms(db, word)
            tsquery = to_tsquery_or(forms)

            rows = db.execute(
                text(
                    """
                    SELECT id, corpus, text, word_count
                    FROM corpus_sentence
                    WHERE corpus = ANY(:corpora)
                      AND tsv @@ to_tsquery('simple', :tsquery)
                    ORDER BY md5(id::text || :word)
                    LIMIT :cap
                    """
                ),
                {"tsquery": tsquery, "word": word, "cap": PRE_RANK_FETCH_CAP, "corpora": list(_CORPORA)},
            ).all()

        candidates = rank_candidates(rows, word, limit)
        return {"candidates": candidates}


def _leipzig_count(db) -> int:
    return db.execute(
        text("SELECT count(*) FROM corpus_sentence WHERE corpus = ANY(:corpora)"),
        {"corpora": list(_CORPORA)},
    ).scalar()


registry.register("examples", "leipzig", LeipzigAdapter(), count=_leipzig_count)
