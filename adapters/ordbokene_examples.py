"""
adapters/ordbokene_examples.py — the `ordbokene` `/examples` provider: a
live call against ord.uib.no, reusing the same two-step flow
`adapters/ordbokene.py` already proves out for `/ipa`
(`/api/articles?w=…` -> `/{dict}/article/{id}.json`). A separate module
from the `/ipa` one, per the `kaikki.py`/`kaikki_ipa.py` precedent — same
source, unrelated per-kind output shape (examples-api design D7, task 5.1).

`body.definitions[]` is walked recursively: `example` nodes nest inside
`definition` elements, which can themselves nest (task 5.2). `sense` is
taken from the nearest enclosing `explanation` element's `content`, so a
nested sub-definition's examples still pick up its own, more specific
explanation when it has one, and its ancestor's otherwise.

`quote.content`'s `$` placeholders are substituted in order from
`quote.items[].text`; a quote with no `$` is used verbatim; an example
whose placeholder count doesn't match its items is skipped rather than
emitted with a literal `$` (task 5.3).

Examples are returned in source (API) order — no ranking (task 5.5,
spec's "dictionary providers preserve source order").
"""

from __future__ import annotations

import requests

from cache import ProviderLookupError
from registry import registry

_BASE_URL = "https://ord.uib.no"
_DICT_FOR_LANG = {"nb": "bm", "nn": "nn"}


def _resolve_placeholders(content: str, items: list[dict]) -> str | None:
    parts = content.split("$")
    n_placeholders = len(parts) - 1
    if n_placeholders == 0:
        return content
    texts = [item.get("text", "") for item in items]
    if len(texts) != n_placeholders:
        return None
    resolved = parts[0]
    for text, tail in zip(texts, parts[1:]):
        resolved += text + tail
    return resolved


def _collect_examples(elements: list[dict], inherited_sense: str | None, out: list[dict]) -> None:
    sense = inherited_sense
    for el in elements:
        el_type = el.get("type_")
        if el_type == "explanation":
            content = el.get("content")
            if content:
                sense = content
        elif el_type == "example":
            quote = el.get("quote") or {}
            resolved = _resolve_placeholders(quote.get("content", ""), quote.get("items", []))
            if resolved is not None:
                candidate = {"text": resolved}
                if sense:
                    candidate["sense"] = sense
                out.append(candidate)
        elif el_type == "definition":
            _collect_examples(el.get("elements", []), sense, out)


class OrdbokeneExamplesAdapter:
    def lookup(self, input_dict: dict) -> dict:
        word = input_dict["text"]
        dict_code = _DICT_FOR_LANG.get(input_dict.get("lang"), "bm")
        limit = input_dict.get("limit", 3)

        try:
            resp = requests.get(
                f"{_BASE_URL}/api/articles",
                params={"w": word, "dict": dict_code, "include": "e"},
                timeout=5,
            )
            resp.raise_for_status()
            article_ids = resp.json().get("articles", {}).get(dict_code, [])

            examples: list[dict] = []
            for article_id in article_ids:
                article_resp = requests.get(f"{_BASE_URL}/{dict_code}/article/{article_id}.json", timeout=5)
                article_resp.raise_for_status()
                definitions = article_resp.json().get("body", {}).get("definitions", [])
                for definition in definitions:
                    _collect_examples(definition.get("elements", []), None, examples)
        except requests.RequestException as exc:
            raise ProviderLookupError(f"ordbokene.no request failed: {exc}") from exc

        return {"candidates": examples[:limit]}


registry.register("examples", "ordbokene", OrdbokeneExamplesAdapter())
