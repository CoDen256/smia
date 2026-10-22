## Why

ElevenLabs is currently registered as a `/tts` provider only as a `NotConfiguredAdapter` stub (`adapters/not_configured.py`) — it was deferred in `smia-service-foundation` because the credential/exact API shape needed live probing this environment couldn't finish at the time. The user now has an `ELEVENLABS_TOKEN` available for testing and wants it implemented for real — both as the `/tts` synthesis provider it was always scoped for, and, newly, as an `/stt` provider too, since ElevenLabs also offers a maintained speech-to-text endpoint.

## What Changes

- Implement a real `elevenlabs` adapter using the official `elevenlabs` Python SDK (per `provider-client-policy` — a legitimate maintained client exists), reading `ELEVENLABS_TOKEN` from the environment.
- Register `elevenlabs` for **`/tts`**: text-to-speech synthesis, returning one or more candidates with `sha256` and available voice metadata (e.g. `gender`), replacing the `NotConfiguredAdapter` stub.
- Register `elevenlabs` for **`/stt`**: speech-to-text, returning `{text}` alongside `hf_whisper` as a second selectable provider — **no change to `/stt`'s required-provider contract**, since `provider` was already mandatory regardless of how many providers are configured.
- No response-shape changes to either endpoint's general contract — this adds a provider, not a new field.

## Capabilities

### New Capabilities
_None._

### Modified Capabilities
- `tts-api`: provider set grows to include a real `elevenlabs` adapter (replacing the not-configured stub).
- `stt-api`: provider set grows from `{hf_whisper}` to `{hf_whisper, elevenlabs}`.

## Impact

- **Affected files**: new `adapters/elevenlabs.py` (registers for both kinds); `adapters/not_configured.py` loses its `elevenlabs` stub registration; `requirements.txt` gains the `elevenlabs` package; `docker-compose.yml`/`.env` need `ELEVENLABS_TOKEN` passed through (tracked in `provider-tokens-and-manual-link-fallback`, not duplicated here — this change assumes the token is available in the adapter's process environment however it gets there).
- **No impact** on `/translations`, `/inflections`, `/ipa`, or `lookup-cache`.
