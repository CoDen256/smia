"""adapters/wikipron.py — the `wikipron` /ipa provider: wikipron's bundled
`nob_latn_broad.tsv`, another thin local lookup (task 4.5)."""

from __future__ import annotations

from sqlalchemy import text

from db.session import session_scope
from registry import registry


class WikipronAdapter:
    def lookup(self, input_dict: dict) -> dict:
        word = input_dict["text"]
        with session_scope() as db:
            rows = db.execute(
                text("SELECT ipa FROM wikipron_entry WHERE wordform = :word"), {"word": word}
            ).all()
        return {"candidates": [{"phonemic": ipa} for (ipa,) in rows]}


registry.register("ipa", "wikipron", WikipronAdapter())
