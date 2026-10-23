"""
adapters/nst.py — the `nst` /ipa provider: the NST NOFABET lexicon, dialect-
aware (D-S7: "one provider per call", acknowledging a provider's own data
can be multi-valued — here, one candidate per dialect variety that has an
entry for the word, all under the single `nst` provider name, not five
separate provider names).

Every candidate carries its transcription under `ipa` (the one `/ipa`
field name every provider uses); `variety` distinguishes the standard
(Eastern-formal) lexicon's entry (`variety: "standard"`) from each
dialect-area/register variant (e.g. `southwestern_spoken`).
"""

from __future__ import annotations

from sqlalchemy import text

from db.session import session_scope
from registry import registry


class NstAdapter:
    def lookup(self, input_dict: dict) -> dict:
        word = input_dict["text"]
        candidates = []
        with session_scope() as db:
            # DISTINCT: the lexicon has one row per (wordform, pos, feats)
            # combination, and homograph entries (e.g. "hus" noun sg vs.
            # pl) frequently share one pronunciation — collapsing to
            # distinct ipa values avoids flooding candidates with
            # identical repeats.
            standard_rows = db.execute(
                text("SELECT DISTINCT ipa FROM nst_lexicon WHERE wordform = :word"), {"word": word}
            ).all()
            for (ipa,) in standard_rows:
                candidates.append({"ipa": ipa, "variety": "standard"})

            dialect_rows = db.execute(
                text(
                    "SELECT DISTINCT dialect_area, register, ipa FROM nst_dialect WHERE wordform = :word"
                ),
                {"word": word},
            ).all()
            for area, register, ipa in dialect_rows:
                candidates.append({"ipa": ipa, "variety": f"{area}_{register}"})

        return {"candidates": candidates}


registry.register("ipa", "nst", NstAdapter())
