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

## URL shapes (tasks 3.1/3.2)

- **Forvo**: `https://forvo.com/word/<word>/#<code>` — e.g.
  `https://forvo.com/word/hygge/#no` (user-corrected; an earlier pass
  guessed `#language-<code>` from a word page's section anchor id, but the
  real shared/bookmarked link format is the bare code fragment). Forvo's
  own language code for Norwegian is `no`, not `nb` — Forvo's language
  list predates the Bokmål/Nynorsk distinction smia uses internally, so
  `nb` is mapped to `no` here; other codes (`en`, `de`, ...) pass through
  unchanged.
- **filmot**: `https://filmot.com/search/<query>/1?gridView=1&lang=<code>`
  — e.g. `https://filmot.com/search/jeg+er+norsk/1?gridView=1&lang=no`
  (user-corrected; an earlier pass couldn't confirm this live after
  hitting filmot's CAPTCHA on the search UI and fell back to a bare
  `/search/<query>` path with no `/1?gridView=1&lang=` suffix). `<query>`
  is the text with spaces as `+` (`quote_plus`, not `quote`); `<code>` uses
  the same `nb`->`no` mapping as Forvo.
"""

from __future__ import annotations

from urllib.parse import quote, quote_plus

from registry import registry

# Both sites' language code predates the Bokmål/Nynorsk split; everything
# else (en, de, ...) is already the target site's own code and passes
# through unchanged.
_MANUAL_LINK_LANG_CODES = {"nb": "no"}


def _forvo_url(text: str, lang: str) -> str:
    code = _MANUAL_LINK_LANG_CODES.get(lang, lang)
    return f"https://forvo.com/word/{quote(text)}/#{code}"


def _filmot_url(text: str, lang: str) -> str:
    code = _MANUAL_LINK_LANG_CODES.get(lang, lang)
    return f"https://filmot.com/search/{quote_plus(text)}/1?gridView=1&lang={code}"


class ManualLinkAdapter:
    def __init__(self, url_fn):
        self._url_fn = url_fn

    def lookup(self, input_dict: dict) -> dict:
        url = self._url_fn(input_dict["text"], input_dict["lang"])
        return {"candidates": [], "url": url}


registry.register("tts", "forvo", ManualLinkAdapter(_forvo_url))
registry.register("tts", "filmot", ManualLinkAdapter(_filmot_url))
