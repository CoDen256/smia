"""
adapters/tatoeba.py — the `tatoeba` `/examples` provider: a corpus lookup
(examples-api design, "CORPUS half") against the imported Tatoeba Norwegian
Bokmål sentence export (`corpus_sentence` rows with `corpus='tatoeba'`).

Query shape is identical to `adapters/leipzig.py`'s (shared form expansion
+ ranking helpers) — the two differ only in which `corpus` values they
filter to, per `CorpusSentence`'s "one table, one discriminator" design.
"""

from __future__ import annotations

from sqlalchemy import text

from adapters._form_expansion import surface_forms, to_tsquery_or
from adapters._ranking import PRE_RANK_FETCH_CAP, rank_candidates
from db.session import session_scope
from registry import registry


class TatoebaAdapter:
    def lookup(self, input_dict: dict) -> dict:
        word = input_dict["text"]
        limit = input_dict.get("limit", 3)

        with session_scope() as db:
            forms = surface_forms(db, word)
            tsquery = to_tsquery_or(forms)

            # Pre-fetch ordered by a hash of (id, query), not row order —
            # the corpus is roughly alphabetically ordered, and sampling
            # by row order would bias the bounded fetch the same way
            # unbiased tie-breaking guards against downstream (design D5).
            rows = db.execute(
                text(
                    """
                    SELECT id, corpus, text, word_count
                    FROM corpus_sentence
                    WHERE corpus = 'tatoeba'
                      AND tsv @@ to_tsquery('simple', :tsquery)
                    ORDER BY md5(id::text || :word)
                    LIMIT :cap
                    """
                ),
                {"tsquery": tsquery, "word": word, "cap": PRE_RANK_FETCH_CAP},
            ).all()

        candidates = rank_candidates(rows, word, limit)
        return {"candidates": candidates}


def _tatoeba_count(db) -> int:
    return db.execute(text("SELECT count(*) FROM corpus_sentence WHERE corpus = 'tatoeba'")).scalar()


registry.register("examples", "tatoeba", TatoebaAdapter(), count=_tatoeba_count)
