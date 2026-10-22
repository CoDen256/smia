"""
adapters/not_configured.py — registered-but-unimplemented /tts providers
(Forvo, filmot.com), per explicit user direction: each needs something
this environment can't get on its own —

  - `forvo`: a Forvo API key (account signup required)
  - `filmot`: an apikey query param — confirmed required by probing
    `filmot.com/api/getstats` live, no free/anonymous tier found

dict.cc's web scrape was stubbed here too in `smia-service-foundation`
(blocked by an obfuscated anti-bot JS loader) — un-stubbed by
`add-dictcc-providers` (task 1.5/1.6), which found a different access path
entirely (dict.cc's own mobile-app backend) and registered the real
`dictcc_api` adapter instead; see `adapters/dictcc_api.py`.

ElevenLabs' stub (`/tts` only) is un-stubbed by `add-elevenlabs-provider`
— see `adapters/elevenlabs.py`, which also adds it as an `/stt` provider.

They're still registered (so `GET /providers` lists them honestly as
"configured" per this change's provider shortlist, and `provider` validation
treats `/tts` as a multi-provider kind) but calling one raises immediately
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
registry.register("tts", "filmot", NotConfiguredAdapter("filmot", "needs a filmot.com API key"))
