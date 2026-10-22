"""
adapters/elevenlabs.py — the `elevenlabs` `/stt` provider.

Uses the official `elevenlabs` Python SDK (`provider-client-policy`: a
legitimate maintained client exists), not raw HTTP.

## `/tts` unregistered, not implemented-but-off

This module no longer registers an `elevenlabs` `/tts` adapter. It was
implemented and live-tested (task 3.1): synthesis itself worked, but
every voice this adapter could reach — both a language-matched search
result and the hardcoded "Rachel" premade-voice fallback used when voice
*listing* 401'd (`missing_permissions: voices_read`, confirmed live on a
key that could still synthesize) — is a shared/library voice, and
ElevenLabs' API rejects synthesizing with any shared/library voice on a
free-tier account with 402 `paid_plan_required`: "Free users cannot use
library voices via the API." There is no voice this adapter can select
that a free-tier account is actually able to use, so it isn't a
configured-but-sometimes-failing provider, it's a permanently-blocked one
on this account tier — removed rather than left registered to always 402.
Re-add once a paid plan or a voice added directly to the account (not a
library voice) is available to test and select by id.

## Error mapping (task 1.5)

The SDK raises `elevenlabs.core.api_error.ApiError` subclasses carrying an
HTTP `status_code`; mapped here into distinguishable `ProviderLookupError`
messages so `/health` and manual debugging don't read unrelated failures
as the same opaque error: 401 -> authorization error, 402 -> payment
required, 429 -> quota/rate-limited, anything else -> a generic failure
still carrying the real status code and body.

## Live-verified (task 3.1)

`/stt` works end-to-end against the real API, confirmed live (a non-speech
test clip correctly came back classified as a sound event rather than
hallucinated text).
"""

from __future__ import annotations

import base64
import os

from elevenlabs.client import ElevenLabs
from elevenlabs.core.api_error import ApiError

from cache import ProviderLookupError
from registry import registry

_DEFAULT_STT_MODEL = "scribe_v1"


def _client() -> ElevenLabs:
    token = os.environ.get("ELEVENLABS_TOKEN")
    if not token:
        raise ProviderLookupError("elevenlabs is not configured yet: needs an ELEVENLABS_TOKEN")
    return ElevenLabs(api_key=token)


def _map_error(exc: Exception) -> ProviderLookupError:
    if isinstance(exc, ApiError):
        if exc.status_code == 401:
            # Live-confirmed this is ElevenLabs' status for BOTH an
            # actually-invalid token AND a valid-but-insufficiently-scoped
            # one (e.g. missing the `voices_read` permission) — "rejected"
            # would overclaim which one happened.
            return ProviderLookupError(
                f"elevenlabs authorization error (401 — check token validity and API key "
                f"permissions): {exc.body}"
            )
        if exc.status_code == 402:
            return ProviderLookupError(f"elevenlabs requires a paid plan for this request (402): {exc.body}")
        if exc.status_code == 429:
            return ProviderLookupError(f"elevenlabs quota exceeded or rate-limited (429): {exc.body}")
        return ProviderLookupError(f"elevenlabs request failed ({exc.status_code}): {exc.body}")
    return ProviderLookupError(f"elevenlabs request failed: {exc}")


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


registry.register(
    "stt", "elevenlabs", ElevenLabsSttAdapter(), available=lambda: bool(os.environ.get("ELEVENLABS_TOKEN"))
)
