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

## Why this adapter stays on raw HTTP (`provider-client-policy`, D-L3)

Not "no library exists" — one does: the `translators` package (also used
by `bing_translate.py`) supports Google too. The swap was explored and
declined, not defaulted to: `translators.translate_text(..., translator=
"google")` returns one plain string per call, discarding the `dict[]`
part-of-speech/sense structure parsed directly above (`sentences[].trans`
+ `dict[]` → `context`). `translate-multi-candidate` depends on that
structure to distinguish Norwegian `igjen`'s "again" sense from its
"back"/"left" sense — a wrapper library that only returns a string can't
carry that. Google Cloud Translate's official SDK doesn't apply either:
it's a different, paid, documented product that doesn't talk to this
endpoint (`translate_a/single`) at all.
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
