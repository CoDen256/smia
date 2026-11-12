"""
adapters/pygmalion_tts.py — the `pygmalion` /tts provider: real human
recordings of ~180 Norwegian words in seven dialect areas, from NTNU's
Pygmalion / LearnNoW pronunciation course, imported once from the committed
corpus (`scripts/import_pygmalion.py`) into `pygmalion_audio` + the audio cache.

Candidate shape reuses what `dictcc_api` already returns — `{sha256, source,
voice}` — and invents no new field: `source` is `"human"` and `voice` carries
the speaker's dialect (`Oslo`, `Bergen`, `Sandnessjøen`, …). One candidate per
recording, never a pick (CLAUDE.md: candidates, not one answer).

Coverage is tiny and mostly minimal-pair words, so a miss is the normal
outcome: `{"candidates": []}`, not an error. Matching is exact on the
casefolded, trimmed text — no citation-form/variant fan-out and no inflection;
that is `/inflect`'s job, and other providers receive the caller's text
unchanged (tts-api spec).
"""

from __future__ import annotations

from sqlalchemy import func, select

from db.models import PygmalionAudio
from db.session import session_scope
from registry import registry

# Oslo is the reference variety (~86% of the data) so it leads; this is a
# deterministic display order, not a preference — every recording is returned.
_FIRST_DIALECT = "Oslo"


def pygmalion_audio_count(db) -> int:
    """Live recording count for `/providers` (provider-catalog spec)."""
    return db.execute(select(func.count()).select_from(PygmalionAudio)).scalar()


class PygmalionTtsAdapter:
    def lookup(self, input_dict: dict) -> dict:
        if input_dict.get("lang", "nb") != "nb":
            return {"candidates": []}
        word = input_dict["text"].strip().casefold()

        with session_scope() as db:
            rows = db.execute(
                select(PygmalionAudio.dialect, PygmalionAudio.take, PygmalionAudio.sha256).where(
                    PygmalionAudio.word == word
                )
            ).all()

        rows.sort(key=lambda r: (r.dialect != _FIRST_DIALECT, r.dialect, r.take))
        candidates, seen = [], set()
        for dialect, _take, sha256 in rows:
            if sha256 in seen:
                continue
            seen.add(sha256)
            candidates.append({"sha256": sha256, "source": "human", "voice": dialect})
        return {"candidates": candidates}


registry.register("tts", "pygmalion", PygmalionTtsAdapter(), count=pygmalion_audio_count)
