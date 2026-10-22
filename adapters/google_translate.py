"""
adapters/google_translate.py — the `google` /translations provider, ported
from hover-translate's `TranslatorFactory`/`google/google.ts` (task 6.1):
the same undocumented `translate_a/single` endpoint, same query params.

## Response shape -> candidates (`translate-multi-candidate`)

`dict[]` groups translations by part-of-speech/sense — confirmed live
(not assumed from the old single-string-concatenation code) that each
`dict[]` entry is already the correct candidate boundary: querying
Norwegian "rett" returns three separate entries (`noun`/"court",
`adjective`/"straight", `adverb`/"straight"), each becoming its own
candidate; "lett" and "igjen" each return exactly one entry with multiple
`terms` ("easy"/"light", "again"/"over"), correctly joined into one
candidate's `text` with `/`. One candidate per `dict[]` entry is always
correct — no further sub-splitting needed within an entry.

`context` is that entry's `pos` (e.g. `"adjective"`) — Google's own sense
label, not a controlled vocabulary smia imposes.

When Google returns no `dict[]` at all (a plain translation with no
dictionary structure), `sentences[].trans` concatenated becomes the sole
candidate's `text`, with no `context`.

## Why this adapter stays on raw HTTP (`provider-client-policy`, D-L3)

Not "no library exists" — one does: the `translators` package (also used
by `bing_translate.py`) supports Google too. The swap was explored and
declined, not defaulted to: `translators.translate_text(..., translator=
"google")` returns one plain string per call, discarding the `dict[]`
part-of-speech/sense structure parsed above — `translate-multi-candidate`
depends on that structure. Google Cloud Translate's official SDK doesn't
apply either: it's a different, paid, documented product that doesn't
talk to this endpoint (`translate_a/single`) at all.

Live-tested against this environment hit Google's anti-automation block
from a plain `requests` call (HTTP 429 "Sorry...") regardless of
User-Agent — almost certainly an IP-reputation block on this sandbox's
egress, not a logic bug; a real browser's `fetch()` from the same sandbox
(different trust context/cookies) got a normal 200, which is how the
`dict[]` structure above was confirmed live rather than guessed. The
request shape and response parsing match hover-translate's working
production code, and are covered by tests/test_translate_adapters.py's
mocked response fixtures.
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

        dict_entries = data.get("dict") or []
        if dict_entries:
            candidates = [
                {"text": "/".join(entry["terms"]), "context": entry["pos"]}
                for entry in dict_entries
                if entry.get("terms")
            ]
        else:
            translated_text = "".join(s.get("trans", "") for s in data.get("sentences", []))
            candidates = [{"text": translated_text}]

        return {"candidates": candidates}


registry.register("translations", "google", GoogleTranslateAdapter())
