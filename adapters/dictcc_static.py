"""
adapters/dictcc_static.py — the `dictcc_static` /translations provider: a
direct lemma-pair lookup against the local import of dict.cc's NO-EN/
NO-DE/DE-EN dumps (task 2.2). No network call, no inflections, no audio
(D-DC5) — the dataset is `term1, term2, pos, tags` only.
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
            row = db.execute(
                text(
                    f"""
                    SELECT {answer_col}, pos, tags FROM dictcc_static_entry
                    WHERE pair = :pair AND {query_col} = :word
                    ORDER BY id LIMIT 1
                    """
                ),
                {"pair": pair, "word": input_dict["text"]},
            ).first()

        if row is None:
            return {"text": ""}

        answer, pos, tags = row
        result = {"text": answer}
        context = " ".join(p for p in (pos, tags) if p.strip())
        if context:
            result["context"] = context
        return result


registry.register("translations", "dictcc_static", DictccStaticAdapter())
