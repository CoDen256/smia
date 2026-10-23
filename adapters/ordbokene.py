"""
adapters/ordbokene.py — the `ordbokene` /ipa provider: a live call against
the University of Bergen's ordbokene.no API (task 4.4), reading
`body.pronunciation` off each matching article.

Note: `pronunciation` entries are ordbokene's own stress-marked respelling
notation (e.g. `sjanˊger`, `jip(p)`), not IPA — there is no official
ordbokene->IPA conversion table (unlike NST's NOFABET table). Surfaced
under `ipa` as-is anyway (the one field name every `/ipa` provider uses);
this is the one `/ipa` provider whose `ipa` field doesn't contain real IPA
symbols, a limitation inherited from the source, not introduced here.
"""

from __future__ import annotations

import requests

from cache import ProviderLookupError
from registry import registry

_BASE_URL = "https://ord.uib.no"
_DICT_FOR_LANG = {"nb": "bm", "nn": "nn"}


class OrdbokeneAdapter:
    def lookup(self, input_dict: dict) -> dict:
        word = input_dict["text"]
        dict_code = _DICT_FOR_LANG.get(input_dict.get("lang"), "bm")

        try:
            resp = requests.get(
                f"{_BASE_URL}/api/articles",
                params={"w": word, "dict": dict_code, "include": "e"},
                timeout=5,
            )
            resp.raise_for_status()
            article_ids = resp.json().get("articles", {}).get(dict_code, [])

            candidates = []
            for article_id in article_ids:
                article_resp = requests.get(f"{_BASE_URL}/{dict_code}/article/{article_id}.json", timeout=5)
                article_resp.raise_for_status()
                pronunciations = article_resp.json().get("body", {}).get("pronunciation", [])
                for p in pronunciations:
                    content = p.get("content")
                    if content:
                        candidates.append({"ipa": content})
        except requests.RequestException as exc:
            raise ProviderLookupError(f"ordbokene.no request failed: {exc}") from exc

        return {"candidates": candidates}


registry.register("ipa", "ordbokene", OrdbokeneAdapter())
