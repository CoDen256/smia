"""
adapters/deepl.py — the `deepl` /translations provider: DeepL's official
API (task 6.3), via the official `deepl` Python package (D-L2,
`provider-client-libraries`) rather than hand-rolled `requests` calls
against `api-free.deepl.com` — the client handles free-vs-pro host
selection and the auth-key header internally, so this adapter no longer
needs to know the API's base URL at all.

Still errors clearly (not silently) until a `DEEPL_API_KEY` is configured,
same spirit as `auth.py`'s own "server misconfigured" check.
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
        api_key = os.environ.get("DEEPL_API_KEY")
        if not api_key:
            raise ProviderLookupError("deepl is not configured yet: needs a DEEPL_API_KEY")

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

        return {"text": result.text}


registry.register("translations", "deepl", DeeplAdapter())
