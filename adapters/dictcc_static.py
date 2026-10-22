"""
adapters/dictcc_static.py — the `dictcc_static` /translations provider: a
direct lemma-pair lookup against the local import of dict.cc's NO-EN/
NO-DE/DE-EN dumps (task 2.2). No network call, no inflections, no audio
(D-DC5) — the dataset is `term1, term2, pos, tags` only.

No client library applies here at all (`provider-client-policy`) — this
isn't even a network call, just a lookup against a local import of a
dataset dict.cc doesn't publish any client for in the first place.

Returns every matching row for the lemma pair, grouped by `(pos, tags)`
(`translate-multi-candidate` D-TM1/D-TM2) — rows sharing the same
pos/tags are the same sense, joined into one candidate's `text` with `/`;
different pos/tags become separate candidates. Previously took only the
first matching row (`ORDER BY id LIMIT 1`), discarding every other sense
the dataset actually has for this lemma pair.
"""

from __future__ import annotations

from sqlalchemy import text

from cache import ProviderLookupError
from db.session import session_scope
from registry import registry

# {(from, to): (pair, query_clean_column, answer_column)} — the query
# matches against the *_clean column (grammar annotations like "{n}"
# stripped, see db/models.py's DictccStaticEntry docstring) but the
# answer returned is the raw, annotated column.
_PAIRS = {
    ("nb", "en"): ("no_en", "term1_clean", "term2"),
    ("en", "nb"): ("no_en", "term2_clean", "term1"),
    ("nb", "de"): ("no_de", "term1_clean", "term2"),
    ("de", "nb"): ("no_de", "term2_clean", "term1"),
    ("de", "en"): ("de_en", "term1_clean", "term2"),
    ("en", "de"): ("de_en", "term2_clean", "term1"),
}


class UnsupportedPairError(ProviderLookupError):
    pass


class DictccStaticAdapter:
    def lookup(self, input_dict: dict) -> dict:
        from_lang, to_lang = input_dict["from"], input_dict["to"]
        mapping = _PAIRS.get((from_lang, to_lang))
        if mapping is None:
            raise UnsupportedPairError(f"dictcc_static does not support the ({from_lang}, {to_lang}) pair")
        pair, query_col, answer_col = mapping

        with session_scope() as db:
            rows = db.execute(
                text(
                    f"""
                    SELECT {answer_col}, pos, tags FROM dictcc_static_entry
                    WHERE pair = :pair AND {query_col} = :word
                    ORDER BY id
                    """
                ),
                {"pair": pair, "word": input_dict["text"]},
            ).all()

        if not rows:
            return {"candidates": []}

        texts_by_sense: dict[tuple[str, str], list[str]] = {}
        for answer, pos, tags in rows:
            sense = (pos, tags)
            texts_by_sense.setdefault(sense, []).append(answer)

        candidates = []
        for (pos, tags), texts in texts_by_sense.items():
            candidate = {"text": "/".join(texts)}
            context = " ".join(p for p in (pos, tags) if p.strip())
            if context:
                candidate["context"] = context
            candidates.append(candidate)
        return {"candidates": candidates}


registry.register("translations", "dictcc_static", DictccStaticAdapter())
