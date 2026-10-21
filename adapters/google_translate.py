"""
adapters/google_translate.py — the `google` /translations provider, ported
from hover-translate's `TranslatorFactory`/`google/google.ts` (task 6.1):
the same undocumented `translate_a/single` endpoint, same query params.

Response shape per `google/types.ts`: `sentences[].trans` concatenated is
the translated text; `dict[]` (part-of-speech -> terms) becomes `context`
(the proposal's rename of hover-translate's `dictionary` field) — only
when Google actually returns dictionary entries for this input.

Live-tested against this environment hit Google's anti-automation block
(HTTP 429 "Sorry...") regardless of User-Agent — almost certainly an IP-
reputation block on this sandbox's egress, not a logic bug; the request
shape and response parsing match hover-translate's working production
code exactly, and are covered by tests/test_translate_adapters.py's mocked
response fixtures.
"""

from __future__ import annotations

import requests

from cache import ProviderLookupError
from registry import registry

_API_URL = "https://translate.googleapis.com/translate_a/single"


class GoogleTranslateAdapter:
    def lookup(self, input_dict: dict) -> dict:
        text = input_dict["text"]
        from_lang = input_dict["from"]
        to_lang = input_dict["to"]

        params = [
            ("client", "gtx"),
            ("q", text),
            ("sl", from_lang),
            ("tl", to_lang),
            ("hl", to_lang),
            ("dj", "1"),
            ("dt", "t"),
            ("dt", "bd"),
            ("dt", "rm"),
            ("dt", "rw"),
        ]

        try:
            resp = requests.get(_API_URL, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError) as exc:
            raise ProviderLookupError(f"google translate request failed: {exc}") from exc

        translated_text = "".join(s.get("trans", "") for s in data.get("sentences", []))

        context = ""
        for entry in data.get("dict", []) or []:
            context += f"{entry['pos']}: {', '.join(entry['terms'])};\n"

        result = {"text": translated_text}
        if context:
            result["context"] = context
        return result


registry.register("translations", "google", GoogleTranslateAdapter())
