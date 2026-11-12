"""
adapters/lexin_ipa.py — the `lexin` /ipa provider (lexin-provider design D5).

Like `ordbokene`, the value is the source's own stress-marked respelling
(`'a:vly:se`, `sjine`), not IPA symbols — surfaced under `ipa` unchanged. That
is a limitation inherited from LEXIN, not introduced here.

An /ipa candidate carries no headword, so a pronunciation belonging to some
other entry LEXIN returned (`skinner` also returns `jernbane`) would just be a
wrong answer. Only entries for the requested word contribute: the headword
(marker-stripped, casefolded) or one of the forms in its inflection string must
equal the casefolded query. This is the one place the "keep fuzzy matches" rule
of /translations and /examples is narrowed.
"""

from __future__ import annotations

from registry import registry

from ._lexin import find, inflected_forms, prepare_query


class LexinIpaAdapter:
    def lookup(self, input_dict: dict) -> dict:
        if input_dict.get("lang", "nb") != "nb":
            return {"candidates": []}

        query = prepare_query(input_dict["text"])
        candidates: list[dict] = []
        seen: set[str] = set()
        for entry in find(input_dict["text"], "bokmål"):
            if query != entry.headword.casefold() and query not in inflected_forms(entry):
                continue
            for pronunciation in entry.pronunciations:
                if pronunciation not in seen:
                    seen.add(pronunciation)
                    candidates.append({"ipa": pronunciation})
        return {"candidates": candidates}


registry.register("ipa", "lexin", LexinIpaAdapter())
