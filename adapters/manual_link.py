"""
adapters/manual_link.py — the `forvo` and `filmot` `/tts` providers
(task 3.3/3.4, `provider-tokens-and-manual-link-fallback`), replacing the
`not_configured.py` stubs they shipped as in `smia-service-foundation`.

Neither Forvo nor filmot.com has a free, accessible API (confirmed
earlier), and that's permanent — not a temporary gap a future key fills.
Rather than erroring forever, these adapters always "succeed" with
`{candidates: [], url}` (D-T3): a link to that provider's own site with
the word/language pre-filled, for the caller to open and check by hand.
This is cached normally per `lookup-cache` like any other result, since the
URL is a pure function of `(text, lang)` — no network call happens here at
all.

## URL shapes (tasks 3.1/3.2, confirmed/attempted live, not guessed)

- **Forvo**: `https://forvo.com/word/<word>/#language-<code>` — confirmed
  live by loading a real word page (`forvo.com/word/hus/`) and reading its
  actual per-language section anchor ids (`<article id="language-no">`,
  not a bare `#no` fragment, which was the original guess). Forvo's own
  language code for Norwegian is `no`, not `nb` (confirmed via its
  `/languages/no/` link and `no.forvo.com` subdomain on that same page) —
  Forvo's language list predates the Bokmål/Nynorsk distinction smia uses
  internally, so `nb` is mapped to `no` here; other codes (`en`, `de`, ...)
  pass through unchanged.
- **filmot**: its public search UI is a client-rendered SPA whose search
  box has no inspectable `name`/query-param wiring, and submitting a
  search live redirected to `filmot.com/captcha-verify` — a CAPTCHA this
  agent will not attempt to solve or bypass (policy), so the exact
  results-page query-param shape could not be confirmed. Per design.md's
  own anticipated fallback for exactly this case, this uses filmot's
  generic public search path instead: `https://filmot.com/search/<query>`.
"""

from __future__ import annotations

from urllib.parse import quote

from registry import registry

# Forvo's language code predates the Bokmål/Nynorsk split; everything else
# (en, de, ...) is already Forvo's own code and passes through unchanged.
_FORVO_LANG_CODES = {"nb": "no"}


def _forvo_url(text: str, lang: str) -> str:
    code = _FORVO_LANG_CODES.get(lang, lang)
    return f"https://forvo.com/word/{quote(text)}/#language-{code}"


def _filmot_url(text: str, lang: str) -> str:
    return f"https://filmot.com/search/{quote(text)}"


class ManualLinkAdapter:
    def __init__(self, url_fn):
        self._url_fn = url_fn

    def lookup(self, input_dict: dict) -> dict:
        url = self._url_fn(input_dict["text"], input_dict["lang"])
        return {"candidates": [], "url": url}


registry.register("tts", "forvo", ManualLinkAdapter(_forvo_url))
registry.register("tts", "filmot", ManualLinkAdapter(_filmot_url))
