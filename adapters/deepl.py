"""
adapters/deepl.py — the `deepl` /translations provider: DeepL's official
API (task 6.3), via the official `deepl` Python package (D-L2,
`provider-client-libraries`) rather than hand-rolled `requests` calls
against `api-free.deepl.com` — the client handles free-vs-pro host
selection and the auth-key header internally, so this adapter no longer
needs to know the API's base URL at all.

Still errors clearly (not silently) until a `DEEPL_TOKEN` is configured,
same spirit as `auth.py`'s own "server misconfigured" check.

`DEEPL_TOKEN`, not `DEEPL_API_KEY` (renamed by `provider-tokens-and-
manual-link-fallback`, D-T1): every provider credential env var ends in
`_TOKEN` (`HF_TOKEN`, `ELEVENLABS_TOKEN`) — this was the one adapter out
of step with that, and with the name the user already uses in `.env`.

Returns `{candidates: [{text}]}` (`translate-multi-candidate`): DeepL's
`/translate` returns exactly one translation per call with no sense
structure to recover, so exactly one candidate — not a shortcoming to fix,
it's what the API actually returns (D-TM3).
"""

from __future__ import annotations

import os

import deepl

from cache import ProviderLookupError
from registry import registry

# DeepL requires a region-qualified target for English/Portuguese ("EN" and
# "PT" alone raise a client-side DeepLException, confirmed live) — this
# adapter's callers pass plain "en"/"pt", so target_lang (only target, not
# source — bare "EN" is accepted as source) gets disambiguated here.
_TARGET_LANG_OVERRIDES = {"EN": "EN-US", "PT": "PT-PT"}


class DeeplAdapter:
    def lookup(self, input_dict: dict) -> dict:
        api_key = os.environ.get("DEEPL_TOKEN")
        if not api_key:
            raise ProviderLookupError("deepl is not configured yet: needs a DEEPL_TOKEN")

        target_lang = input_dict["to"].upper()
        target_lang = _TARGET_LANG_OVERRIDES.get(target_lang, target_lang)

        translator = deepl.Translator(api_key)
        try:
            result = translator.translate_text(
                input_dict["text"],
                source_lang=input_dict["from"].upper(),
                target_lang=target_lang,
            )
        except deepl.DeepLException as exc:
            raise ProviderLookupError(f"deepl request failed: {exc}") from exc

        # DeepL's /translate returns exactly one translation with no sense
        # structure — one candidate is correct and final here, not a
        # placeholder pending future work (translate-multi-candidate D-TM3).
        return {"candidates": [{"text": result.text}]}


registry.register("translations", "deepl", DeeplAdapter())
