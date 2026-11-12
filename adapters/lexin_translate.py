"""
adapters/lexin_translate.py — the `lexin` /translations provider: a live call
against LEXIN's findwords API (lexin-provider design D4, D5, D6).

Two pairs, selected by a table rather than code paths:
  nb→nb  LEXIN's plain-Norwegian definition of each entry. `context` names the
         headword (`avlyse, verb`), which is what makes a fuzzy hit — an entry
         LEXIN returned only because it contains the query — legible.
  nb→en  LEXIN's English dictionary. One call, no join back to the Norwegian
         entry (D4): `text` is the English headword and `context` is its part
         of speech and English definition, which tells apart same-headword
         senses (`hand`: the body part / a clock pointer / help).

Fuzzy matches are deliberately not filtered. Any other pair raises
`UnsupportedPairError`, like `dictcc_static`.
"""

from __future__ import annotations

from registry import registry

from ._lexin import UnsupportedPairError, find

_PAIRS = {("nb", "nb"): "bokmål", ("nb", "en"): "engelsk"}


def _dedupe(candidates: list[dict]) -> list[dict]:
    seen, out = set(), []
    for candidate in candidates:
        key = (candidate["text"], candidate.get("context"))
        if key not in seen:
            seen.add(key)
            out.append(candidate)
    return out


class LexinTranslateAdapter:
    def lookup(self, input_dict: dict) -> dict:
        pair = (input_dict["from"], input_dict["to"])
        select_lang = _PAIRS.get(pair)
        if select_lang is None:
            raise UnsupportedPairError(f"lexin does not support the {pair} pair")

        entries = find(input_dict["text"], select_lang)

        candidates: list[dict] = []
        for entry in entries:
            if pair == ("nb", "nb"):
                context = ", ".join(part for part in (entry.headword, entry.pos) if part)
                for definition in entry.definitions:
                    candidate = {"text": definition}
                    if context:
                        candidate["context"] = context
                    candidates.append(candidate)
            else:
                if not entry.headword:
                    continue
                candidate = {"text": entry.headword}
                context = ": ".join(part for part in (entry.pos, "; ".join(entry.definitions)) if part)
                if context:
                    candidate["context"] = context
                candidates.append(candidate)

        return {"candidates": _dedupe(candidates)}


registry.register("translations", "lexin", LexinTranslateAdapter())
