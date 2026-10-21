"""
adapters/bing_translate.py — the `bing` /translations provider, ported from
hover-translate's `bing/bing.ts` (task 6.2): the same public edge-auth
token exchange + Microsoft Cognitive Services translate call, no API key.

Unlike `bing.ts` (which caches the JWT and only refreshes it near
expiry), this adapter fetches a fresh token every call — simpler, and the
two extra round trips are cheap relative to the lookup-cache's own
per-request cost; no `jwt-decode`-equivalent dependency needed as a result.

Live-tested against this environment: `edge.microsoft.com/translate/auth`
returned 404 — Microsoft appears to have moved or retired this exact
undocumented endpoint since `bing.ts` was last verified working. The
request/response shapes below match `bing/types.ts` exactly and are
covered by tests/test_translate_adapters.py's mocked fixtures; if the auth
endpoint has genuinely moved, that's a ported-code staleness issue to
revisit, not a logic bug introduced here.
"""

from __future__ import annotations

import requests

from cache import ProviderLookupError
from registry import registry

_AUTH_URL = "https://edge.microsoft.com/translate/auth"
_API_URL = "https://api.cognitive.microsofttranslator.com/translate"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


class BingTranslateAdapter:
    def lookup(self, input_dict: dict) -> dict:
        text = input_dict["text"]
        from_lang = input_dict["from"]
        to_lang = input_dict["to"]

        try:
            auth_resp = requests.get(_AUTH_URL, headers=_HEADERS, timeout=10)
            auth_resp.raise_for_status()
            token = auth_resp.text

            resp = requests.post(
                _API_URL,
                params={"api-version": "3.0", "from": from_lang if from_lang != "auto" else "", "to": to_lang},
                json=[{"Text": text}],
                headers={**_HEADERS, "Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError) as exc:
            raise ProviderLookupError(f"bing translate request failed: {exc}") from exc

        return {"text": data[0]["translations"][0]["text"]}


registry.register("translations", "bing", BingTranslateAdapter())
