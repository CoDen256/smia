## 1. Adapter implementation

- [x] 1.1 Add `elevenlabs` to `requirements.txt`
- [x] 1.2 Implement `adapters/elevenlabs.py`: construct one SDK client from `ELEVENLABS_TOKEN`, raising `ProviderLookupError` if the env var is absent (same pattern as `adapters/deepl.py`)
- [x] 1.3 Implement the `/tts` adapter: call ElevenLabs' text-to-speech endpoint, store resulting audio via `audio_cache.store`, return `{candidates: [{sha256, voice, gender?}]}`; pick a sensible default voice since the request has no `voice` field — `voices.search(language=lang)`, falling back to any voice if none match; `gender` read from `voice.labels["gender"]` (confirmed by reading the SDK's `Voice` model, not guessed)
- [x] 1.4 Implement the `/stt` adapter: call ElevenLabs' speech-to-text endpoint, return `{text}`
- [x] 1.5 Map ElevenLabs SDK exceptions to `ProviderLookupError`, distinguishing quota-exceeded from misconfigured-credential from transient failure — `ApiError.status_code`: 401 -> credential rejected, 429 -> quota/rate-limited, else -> generic failure with status code and body
- [x] 1.6 Remove the `elevenlabs` stub registration from `adapters/not_configured.py`

## 2. Tests

- [x] 2.1 Test the `/tts` adapter against a mocked SDK client, asserting candidate shape and audio storage
- [x] 2.2 Test the `/stt` adapter against a mocked SDK client, asserting `{provider, text}` shape
- [x] 2.3 Test missing-token behavior for both kinds
- [x] 2.4 Test quota-exceeded error mapping

## 3. Verify end-to-end

- [ ] 3.1 With a real `ELEVENLABS_TOKEN` (from `.env`), manually verify `POST /tts {provider: "elevenlabs", ...}` and `POST /stt {provider: "elevenlabs", ...}` against the live API — **blocked: no `ELEVENLABS_TOKEN` available in this execution environment** (this repo's `.env`, if any, is outside this agent's read access by policy); implemented against the SDK's documented/introspected method signatures and response models, covered by mocked tests only. Needs to be run by whoever holds the real token
- [x] 3.2 Confirm `GET /providers` lists `elevenlabs` for both `tts` and `stt` — verified live through the real Docker container
