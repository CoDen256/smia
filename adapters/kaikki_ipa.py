"""
adapters/kaikki_ipa.py — the `kaikki` /ipa provider: reads the same
`kaikki_entry.sounds` jsonb imported once for `/inflections` (D-S4), this
time extracting `sounds[].ipa` entries instead of `forms`. One candidate
per `sounds[]` item that has an `ipa` key (a kaikki entry can list several —
e.g. a letter-name reading vs. a phoneme reading); `variety` is the comma-
joined `tags` list when present, otherwise omitted.

Registered under the provider name `kaikki` for kind `ipa` — a distinct
module from `adapters/kaikki.py` (the `/inflections` `kaikki` provider)
because the two have unrelated per-kind output shapes, but both query the
one shared `kaikki_entry` table.
"""

from __future__ import annotations

from sqlalchemy import text

from db.session import session_scope
from registry import registry


class KaikkiIpaAdapter:
    def lookup(self, input_dict: dict) -> dict:
        word = input_dict["text"]
        with session_scope() as db:
            rows = db.execute(
                text("SELECT sounds FROM kaikki_entry WHERE word = :word"), {"word": word}
            ).all()

        candidates = []
        for (sounds,) in rows:
            for sound in sounds:
                ipa = sound.get("ipa")
                if not ipa:
                    continue
                candidate = {"ipa": ipa}
                tags = sound.get("tags")
                if tags:
                    candidate["variety"] = ",".join(tags)
                candidates.append(candidate)

        return {"candidates": candidates}


registry.register("ipa", "kaikki", KaikkiIpaAdapter())
