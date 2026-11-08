"""
adapters/kaikki_examples.py — the `kaikki` `/examples` provider: reads the
imported `kaikki_entry.examples` jsonb (scripts/import_kaikki.py task 2.5),
a separate module from `adapters/kaikki.py`/`adapters/kaikki_ipa.py` per
the same-table/different-kind precedent those two already establish.

Looks up by the entry's headword directly — unlike the corpus providers,
a dictionary provider's examples are filed under the lemma itself, not
under every inflected surface form, so no `ordbank_fullform` expansion
applies here (examples-api design: "dictionary providers" vs "corpus
providers").

Filters out morphology/derivation fragments at query time (design D8):
anything containing `→` or ` + `, or with no whitespace at all (a single
token can't be a usage example). `translation`/`english` keys some kaikki
examples carry are discarded outright, per the no-translation rule — only
`text` is ever surfaced. No ranking: source order, like every dictionary
provider (task 5.6 / spec's "dictionary providers preserve source order").
"""

from __future__ import annotations

from sqlalchemy import text as sa_text

from db.session import session_scope
from registry import registry


def _is_usable_example(example_text: str) -> bool:
    if "→" in example_text:
        return False
    if " + " in example_text:
        return False
    if not any(ch.isspace() for ch in example_text):
        return False
    return True


class KaikkiExamplesAdapter:
    def lookup(self, input_dict: dict) -> dict:
        word = input_dict["text"]
        limit = input_dict.get("limit", 3)

        with session_scope() as db:
            rows = db.execute(
                sa_text("SELECT examples FROM kaikki_entry WHERE word = :word"), {"word": word}
            ).all()

        candidates = []
        for (examples,) in rows:
            for example in examples:
                example_text = example.get("text")
                if not example_text or not _is_usable_example(example_text):
                    continue
                candidates.append({"text": example_text})
                if len(candidates) >= limit:
                    return {"candidates": candidates}

        return {"candidates": candidates}


def _kaikki_examples_count(db) -> int:
    return db.execute(
        sa_text("SELECT count(*) FROM kaikki_entry WHERE jsonb_array_length(examples) > 0")
    ).scalar()


registry.register("examples", "kaikki", KaikkiExamplesAdapter(), count=_kaikki_examples_count)
