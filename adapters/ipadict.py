"""adapters/ipadict.py — the `ipadict` /ipa provider: ipa-dict/nb, a thin
lemma-only local lookup (task 4.5)."""

from __future__ import annotations

from sqlalchemy import text

from db.session import session_scope
from registry import registry


class IpaDictAdapter:
    def lookup(self, input_dict: dict) -> dict:
        word = input_dict["text"]
        with session_scope() as db:
            rows = db.execute(
                text("SELECT ipa FROM ipa_dict_entry WHERE wordform = :word"), {"word": word}
            ).all()
        return {"candidates": [{"phonemic": ipa} for (ipa,) in rows]}


registry.register("ipa", "ipadict", IpaDictAdapter())
