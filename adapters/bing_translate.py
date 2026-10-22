"""
adapters/bing_translate.py — the `bing` /translations provider.

Originally ported from hover-translate's `bing.ts` (a hand-rolled public
edge-auth-token exchange + Microsoft Cognitive Services call). Swapped to
the `translators` package's Bing engine (D-L4, `provider-client-
libraries`): unlike Google (see `google_translate.py`), this adapter never
extracted any structured sense/dictionary data from Bing — only one plain
translated string — so there was no data fidelity to lose by swapping, and
it fixes a live-confirmed reliability problem: the old hand-rolled flow
depended on `edge.microsoft.com/translate/auth`, an undocumented endpoint
that returned 404 when this adapter was first tested (Microsoft appears to
have moved or retired it). `translators` is actively maintained and
handles Bing's access path as someone else's maintenance burden instead of
this repo's hand-rolled auth exchange.

`translators` is GPL-3.0 — accepted as a non-issue for this private,
non-redistributed deployment (explicit user decision, recorded in
provider-client-libraries' design.md D-L4).

Two deployment notes found live while verifying this swap in the real
Docker image (not just mocked tests):
- The Bing engine shells out to a JS runtime for Bing's client-side
  signing logic — the container needs Node.js installed (see Dockerfile);
  without it this raises "Unable to find available javascript runtime".
- One single call failed with `OSError(90, 'Message too long')` right
  after a container restart (a transient HTTP/3-over-UDP hiccup from the
  `niquests`/`qh3` stack this library depends on, not reproducible on
  retry or on later calls) — if this recurs, it's a network-layer flake to
  retry, not a code bug; `ProviderLookupError`'s no-fallback contract means
  the caller sees it and can just ask again.

Returns `{candidates: [{text}]}` (`translate-multi-candidate`): `translators`
returns one plain string per call with no sense structure to recover, so
exactly one candidate — not a shortcoming to fix, it's what this access
path actually returns (D-TM3).
"""

from __future__ import annotations

import translators

from cache import ProviderLookupError
from registry import registry


class BingTranslateAdapter:
    def lookup(self, input_dict: dict) -> dict:
        try:
            text = translators.translate_text(
                input_dict["text"],
                translator="bing",
                from_language=input_dict["from"],
                to_language=input_dict["to"],
            )
        except Exception as exc:  # translators.server.TranslatorError, or any lower-level failure
            raise ProviderLookupError(f"bing translate request failed: {exc}") from exc

        # translators' Bing engine returns one plain string with no sense
        # structure (unlike Google's dict[] — see google_translate.py) —
        # one candidate is correct and final here, not a placeholder
        # pending future work (translate-multi-candidate D-TM3).
        return {"candidates": [{"text": text}]}


registry.register("translations", "bing", BingTranslateAdapter())
