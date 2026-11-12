"""
adapters/lexin_examples.py — the `lexin` /examples provider: the example
sentences LEXIN's lexicographers filed under each returned entry (a dictionary
provider, like `ordbokene` — lexin-provider design D5).

Returned in LEXIN's response order, no ranking. `sense` is the entry's
definition (several definitions are joined with `; `, since the source does not
say which one an example illustrates); an entry with no definition still
contributes its examples, just without `sense`. Fuzzy matches are kept. No
translation is ever emitted.
"""

from __future__ import annotations

from registry import registry

from ._lexin import find


class LexinExamplesAdapter:
    def lookup(self, input_dict: dict) -> dict:
        if input_dict.get("lang", "nb") != "nb":
            return {"candidates": []}
        limit = input_dict.get("limit", 3)

        candidates: list[dict] = []
        seen: set[tuple] = set()
        for entry in find(input_dict["text"], "bokmål"):
            sense = "; ".join(entry.definitions)
            for example in entry.examples:
                key = (example, sense)
                if key in seen:
                    continue
                seen.add(key)
                candidate = {"text": example}
                if sense:
                    candidate["sense"] = sense
                candidates.append(candidate)
        return {"candidates": candidates[:limit]}


registry.register("examples", "lexin", LexinExamplesAdapter())
