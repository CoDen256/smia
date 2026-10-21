"""
adapters/deepl.py — the `deepl` /translations provider: DeepL's official
free-tier API (task 6.3). Unlike Forvo/ElevenLabs/filmot (whose APIs
needed live probing this environment couldn't finish), DeepL's API is
public, stable, documented, and needs nothing probed — only a
`DEEPL_API_KEY` env var this environment doesn't have. Implemented fully;
errors clearly (not silently) until a key is configured, same spirit as
`auth.py`'s own "server misconfigured" check.
"""

from __future__ import annotations

import os

import requests

from cache import ProviderLookupError
from registry import registry

_API_URL = "https://api-free.deepl.com/v2/translate"


class DeeplAdapter:
    def lookup(self, input_dict: dict) -> dict:
        api_key = os.environ.get("DEEPL_API_KEY")
        if not api_key:
            raise ProviderLookupError("deepl is not configured yet: needs a DEEPL_API_KEY")

        try:
            resp = requests.post(
                _API_URL,
                headers={"Authorization": f"DeepL-Auth-Key {api_key}"},
                data={
                    "text": input_dict["text"],
                    "source_lang": input_dict["from"].upper(),
                    "target_lang": input_dict["to"].upper(),
                },
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError) as exc:
            raise ProviderLookupError(f"deepl request failed: {exc}") from exc

        return {"text": data["translations"][0]["text"]}


registry.register("translations", "deepl", DeeplAdapter())
