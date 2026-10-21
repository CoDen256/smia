"""
adapters/not_configured.py — registered-but-unimplemented /tts providers
(Forvo, ElevenLabs, filmot.com, dict.cc), per explicit user direction: each
needs something this environment can't get on its own —

  - `forvo`: a Forvo API key (account signup required)
  - `elevenlabs`: an ElevenLabs API key (account signup required)
  - `filmot`: an apikey query param — confirmed required by probing
    `filmot.com/api/getstats` live, no free/anonymous tier found
  - `dictcc`: its audio delivery sits behind an obfuscated anti-bot JS
    loader (`audioserver_domain`/`audio_format` are set via a minified,
    packed script on the search results page) — reverse-engineering it
    reliably is real scraping work, not a quick API call

They're still registered (so `GET /providers` lists them honestly as
"configured" per this change's provider shortlist, and `provider` validation
treats `/tts` as a 5-provider kind) but calling one raises immediately
rather than pretending to work.
"""

from __future__ import annotations

from cache import ProviderLookupError
from registry import registry


class NotConfiguredAdapter:
    def __init__(self, name: str, reason: str):
        self._name = name
        self._reason = reason

    def lookup(self, input_dict: dict) -> dict:
        raise ProviderLookupError(f"{self._name} is not configured yet: {self._reason}")


registry.register("tts", "forvo", NotConfiguredAdapter("forvo", "needs a Forvo API key"))
registry.register("tts", "elevenlabs", NotConfiguredAdapter("elevenlabs", "needs an ElevenLabs API key"))
registry.register("tts", "filmot", NotConfiguredAdapter("filmot", "needs a filmot.com API key"))
registry.register(
    "tts", "dictcc", NotConfiguredAdapter("dictcc", "audio delivery is behind obfuscated anti-bot JS")
)
