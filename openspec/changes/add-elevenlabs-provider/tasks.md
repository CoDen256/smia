## 1. Adapter implementation

- [ ] 1.1 Add `elevenlabs` to `requirements.txt`
- [ ] 1.2 Implement `adapters/elevenlabs.py`: construct one SDK client from `ELEVENLABS_TOKEN`, raising `ProviderLookupError` if the env var is absent (same pattern as `adapters/deepl.py`)
- [ ] 1.3 Implement the `/tts` adapter: call ElevenLabs' text-to-speech endpoint, store resulting audio via `audio_cache.store`, return `{candidates: [{sha256, voice, gender?}]}`; pick a sensible default voice since the request has no `voice` field
- [ ] 1.4 Implement the `/stt` adapter: call ElevenLabs' speech-to-text endpoint, return `{text}`
- [ ] 1.5 Map ElevenLabs SDK exceptions to `ProviderLookupError`, distinguishing quota-exceeded from misconfigured-credential from transient failure
- [ ] 1.6 Remove the `elevenlabs` stub registration from `adapters/not_configured.py`

## 2. Tests

- [ ] 2.1 Test the `/tts` adapter against a mocked SDK client, asserting candidate shape and audio storage
- [ ] 2.2 Test the `/stt` adapter against a mocked SDK client, asserting `{provider, text}` shape
- [ ] 2.3 Test missing-token behavior for both kinds
- [ ] 2.4 Test quota-exceeded error mapping

## 3. Verify end-to-end

- [ ] 3.1 With a real `ELEVENLABS_TOKEN` (from `.env`), manually verify `POST /tts {provider: "elevenlabs", ...}` and `POST /stt {provider: "elevenlabs", ...}` against the live API
- [ ] 3.2 Confirm `GET /providers` lists `elevenlabs` for both `tts` and `stt`
