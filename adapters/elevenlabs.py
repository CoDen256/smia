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

Live-verified (task 3.1) this listing step can itself fail even with a
valid token: a scoped API key can be authorized to synthesize speech but
not to list voices, confirmed live as a 401 with `missing_permissions:
voices_read` — distinct from an actually-invalid key. Rather than fail
`/tts` entirely over a listing permission it doesn't need to succeed,
`_pick_voice` falls back to ElevenLabs' well-known stable premade voice
id ("Rachel") on exactly that 401/403 case; any other failure (e.g. a
genuinely bad token) still propagates and is mapped by `_map_error` below.

## Error mapping (task 1.5)

The SDK raises `elevenlabs.core.api_error.ApiError` subclasses carrying an
HTTP `status_code`; mapped here into distinguishable `ProviderLookupError`
messages so `/health` and manual debugging don't read unrelated failures
as the same opaque error: 401 -> authorization error (ElevenLabs uses 401
for both a truly invalid token AND a valid-but-insufficiently-scoped one —
confirmed live, see above — so this message doesn't overclaim which one
happened), 402 -> payment required, 429 -> quota/rate-limited, anything
else -> a generic failure still carrying the real status code and body.

## Live-verified (task 3.1)

`/stt` works end-to-end against the real API, confirmed live (a non-speech
test clip correctly came back classified as a sound event rather than
hallucinated text). `/tts` surfaced a second real constraint on free-tier
accounts beyond the `voices_read` gap above: synthesizing with a shared/
library voice via the API (including this adapter's premade-voice
fallback) returns 402 `paid_plan_required` — "Free users cannot use
library voices via the API." This is an ElevenLabs account/billing-tier
restriction, not a bug here; the 402 mapping above exists specifically so
it reads as "needs a paid plan or your own voice," not a generic failure.
`/tts` synthesis itself was not confirmed to produce audio on a free-tier
account in this pass — re-verify once a paid plan or a voice added
directly to the account (not a library voice) is available to test with.
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

# ElevenLabs' "Rachel" — a stable, publicly documented premade voice id
# present on every account's library by default. Used only when voice
# *listing* isn't permitted for this API key (see _pick_voice).
_FALLBACK_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"
_FALLBACK_VOICE_NAME = "Rachel"


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
            # Live-confirmed: free-tier accounts get this when synthesizing
            # with a shared/library voice via the API — a billing-tier
            # limitation, not a bug here, but worth naming plainly rather
            # than falling into the generic branch below.
            return ProviderLookupError(
                f"elevenlabs requires a paid plan (or a voice already added to your own "
                f"account) to synthesize via the API (402): {exc.body}"
            )
        if exc.status_code == 429:
            return ProviderLookupError(f"elevenlabs quota exceeded or rate-limited (429): {exc.body}")
        return ProviderLookupError(f"elevenlabs request failed ({exc.status_code}): {exc.body}")
    return ProviderLookupError(f"elevenlabs request failed: {exc}")


def _pick_voice(client: ElevenLabs, lang: str) -> tuple[str, str, str | None]:
    """Returns `(voice_id, name, gender_or_None)`. Falls back to a known
    stable premade voice if listing isn't permitted for this API key —
    confirmed live as a 401 (`missing_permissions: voices_read`) on a key
    that could still synthesize speech just fine."""
    try:
        result = client.voices.search(language=lang, page_size=1)
        if not result.voices:
            result = client.voices.search(page_size=1)
    except ApiError as exc:
        if exc.status_code not in (401, 403):
            raise
        return _FALLBACK_VOICE_ID, _FALLBACK_VOICE_NAME, None

    if not result.voices:
        return _FALLBACK_VOICE_ID, _FALLBACK_VOICE_NAME, None
    voice = result.voices[0]
    return voice.voice_id, voice.name or voice.voice_id, (voice.labels or {}).get("gender")


class ElevenLabsTtsAdapter:
    def lookup(self, input_dict: dict) -> dict:
        client = _client()
        text, lang = input_dict["text"], input_dict["lang"]

        try:
            voice_id, voice_name, gender = _pick_voice(client, lang)
            model = os.environ.get("ELEVENLABS_TTS_MODEL", _DEFAULT_TTS_MODEL)
            chunks = client.text_to_speech.convert(voice_id, text=text, model_id=model)
            audio = b"".join(chunks)
        except Exception as exc:
            raise _map_error(exc) from exc

        with session_scope() as db:
            sha256 = store(db, audio, "audio/mpeg")

        candidate = {"sha256": sha256, "voice": voice_name}
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
