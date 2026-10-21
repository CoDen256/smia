"""
adapters/libretranslate.py — the `libretranslate` /translations provider
(task 6.4). LibreTranslate's API is simple, documented, and self-hostable;
`LIBRETRANSLATE_URL` picks which instance to call (official hosted
instance by default — libretranslate.com now requires `LIBRETRANSLATE_API_KEY`
too, confirmed live; other public mirrors probed during implementation were
all down or blocking, a known instability of community-run instances, not
something fixable from here). Self-hosting one's own instance (`docker run
libretranslate/libretranslate`) is the reliable option in production.
"""

from __future__ import annotations

import os

import requests

from cache import ProviderLookupError
from registry import registry

_DEFAULT_URL = "https://libretranslate.com/translate"


class LibreTranslateAdapter:
    def lookup(self, input_dict: dict) -> dict:
        url = os.environ.get("LIBRETRANSLATE_URL", _DEFAULT_URL)
        body = {
            "q": input_dict["text"],
            "source": input_dict["from"],
            "target": input_dict["to"],
            "format": "text",
        }
        api_key = os.environ.get("LIBRETRANSLATE_API_KEY")
        if api_key:
            body["api_key"] = api_key

        try:
            resp = requests.post(url, json=body, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError) as exc:
            raise ProviderLookupError(f"libretranslate request failed: {exc}") from exc

        if "error" in data:
            raise ProviderLookupError(f"libretranslate error: {data['error']}")

        return {"text": data["translatedText"]}


registry.register("translations", "libretranslate", LibreTranslateAdapter())
