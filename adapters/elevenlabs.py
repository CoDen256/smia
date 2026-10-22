"""
adapters/elevenlabs.py — the `elevenlabs` provider for both `/tts`
(synthesis, replacing the `not_configured` stub it shipped as in
`smia-service-foundation`) and `/stt` (newly added here). One module, two
registrations (D-EL1): one `ELEVENLABS_TOKEN`, one SDK client, two
unrelated-but-adjacent capabilities from the same vendor — splitting into
two files would duplicate the client construction and token-missing error
for no benefit.

Uses the official `elevenlabs` Python SDK (`provider-client-policy`: a
legitimate maintained client exists), not raw HTTP.

## Voice selection (D-EL2)

`/tts`'s request shape (`{text, lang, provider}`) has no `voice` field, so
this adapter picks one: `client.voices.search(language=lang, page_size=1)`,
falling back to any voice at all if none match that language. `gender` is
included in the candidate only when ElevenLabs' voice metadata carries it
(it lives in `voice.labels["gender"]`, not a top-level field — confirmed
by reading the SDK's `Voice` model, not guessed).

## Error mapping (task 1.5)

The SDK raises `elevenlabs.core.api_error.ApiError` subclasses carrying an
HTTP `status_code`; mapped here into three distinguishable
`ProviderLookupError` messages so `/health` and manual debugging don't
read "quota exceeded" and "wrong token" as the same opaque failure:
401 -> credential rejected, 429 -> quota/rate-limited, anything else ->
a generic failure still carrying the real status code and body.

## Known gap: not live-verified (task 3.1)

No `ELEVENLABS_TOKEN` was available in this execution environment to test
against the real API (this repo's `.env`, if any, is outside this agent's
read access by policy) — implemented against the SDK's documented/
introspected method signatures and response models, covered by mocked
tests, but task 3.1's live verification needs to be run by whoever has the
real token.
"""

from __future__ import annotations

import base64
import os

from elevenlabs.client import ElevenLabs
from elevenlabs.core.api_error import ApiError

from audio_cache import store
from cache import ProviderLookupError
from db.session import session_scope
from registry import registry

_DEFAULT_TTS_MODEL = "eleven_multilingual_v2"
_DEFAULT_STT_MODEL = "scribe_v1"


def _client() -> ElevenLabs:
    token = os.environ.get("ELEVENLABS_TOKEN")
    if not token:
        raise ProviderLookupError("elevenlabs is not configured yet: needs an ELEVENLABS_TOKEN")
    return ElevenLabs(api_key=token)


def _map_error(exc: Exception) -> ProviderLookupError:
    if isinstance(exc, ApiError):
        if exc.status_code == 401:
            return ProviderLookupError(f"elevenlabs credential rejected (401): {exc.body}")
        if exc.status_code == 429:
            return ProviderLookupError(f"elevenlabs quota exceeded or rate-limited (429): {exc.body}")
        return ProviderLookupError(f"elevenlabs request failed ({exc.status_code}): {exc.body}")
    return ProviderLookupError(f"elevenlabs request failed: {exc}")


class ElevenLabsTtsAdapter:
    def lookup(self, input_dict: dict) -> dict:
        client = _client()
        text, lang = input_dict["text"], input_dict["lang"]

        try:
            result = client.voices.search(language=lang, page_size=1)
            if not result.voices:
                result = client.voices.search(page_size=1)
            if not result.voices:
                raise ProviderLookupError("elevenlabs: no voices available on this account")
            voice = result.voices[0]

            model = os.environ.get("ELEVENLABS_TTS_MODEL", _DEFAULT_TTS_MODEL)
            chunks = client.text_to_speech.convert(voice.voice_id, text=text, model_id=model)
            audio = b"".join(chunks)
        except ProviderLookupError:
            raise
        except Exception as exc:
            raise _map_error(exc) from exc

        with session_scope() as db:
            sha256 = store(db, audio, "audio/mpeg")

        candidate = {"sha256": sha256, "voice": voice.name or voice.voice_id}
        gender = (voice.labels or {}).get("gender")
        if gender:
            candidate["gender"] = gender
        return {"candidates": [candidate]}


class ElevenLabsSttAdapter:
    def lookup(self, input_dict: dict) -> dict:
        client = _client()
        audio = base64.b64decode(input_dict["audio_b64"])
        lang = input_dict.get("lang")
        model = os.environ.get("ELEVENLABS_STT_MODEL", _DEFAULT_STT_MODEL)

        kwargs = {"model_id": model, "file": audio}
        if lang:
            kwargs["language_code"] = lang

        try:
            result = client.speech_to_text.convert(**kwargs)
        except Exception as exc:
            raise _map_error(exc) from exc

        return {"text": result.text}


registry.register("tts", "elevenlabs", ElevenLabsTtsAdapter())
registry.register("stt", "elevenlabs", ElevenLabsSttAdapter())
