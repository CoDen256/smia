## 1. Adapter implementation

- [x] 1.1 Add `elevenlabs` to `requirements.txt`
- [x] 1.2 Implement `adapters/elevenlabs.py`: construct one SDK client from `ELEVENLABS_TOKEN`, raising `ProviderLookupError` if the env var is absent (same pattern as `adapters/deepl.py`)
- [x] 1.3 Implement the `/tts` adapter: call ElevenLabs' text-to-speech endpoint, store resulting audio via `audio_cache.store`, return `{candidates: [{sha256, voice, gender?}]}`; pick a sensible default voice since the request has no `voice` field — `voices.search(language=lang)`, falling back to any voice if none match; `gender` read from `voice.labels["gender"]` (confirmed by reading the SDK's `Voice` model, not guessed). **Updated after live testing (3.1)**: also falls back to ElevenLabs' stable premade "Rachel" voice id when listing itself isn't permitted for this API key (live-confirmed 401 `missing_permissions: voices_read`) — the adapter no longer hard-fails just because it can't list voices
- [x] 1.4 Implement the `/stt` adapter: call ElevenLabs' speech-to-text endpoint, return `{text}`
- [x] 1.5 Map ElevenLabs SDK exceptions to `ProviderLookupError`, distinguishing quota-exceeded from misconfigured-credential from transient failure — `ApiError.status_code`: 401 -> authorization error (covers both invalid token and insufficient scope, confirmed live both return 401), 402 -> payment required (added after live-finding free tier blocks library-voice synthesis via the API), 429 -> quota/rate-limited, else -> generic failure with status code and body
- [x] 1.6 Remove the `elevenlabs` stub registration from `adapters/not_configured.py`

## 2. Tests

- [x] 2.1 Test the `/tts` adapter against a mocked SDK client, asserting candidate shape and audio storage
- [x] 2.2 Test the `/stt` adapter against a mocked SDK client, asserting `{provider, text}` shape
- [x] 2.3 Test missing-token behavior for both kinds
- [x] 2.4 Test quota-exceeded error mapping

## 3. Verify end-to-end

- [x] 3.1 With a real `ELEVENLABS_TOKEN` (from `.env`), manually verify `POST /tts {provider: "elevenlabs", ...}` and `POST /stt {provider: "elevenlabs", ...}` against the live API — verified through the real Docker container (`docker compose` auto-loads the host's `.env`, which has a real token; this agent still never read the file's contents directly). **Results**: `/stt` works end-to-end — a non-speech test clip correctly came back classified as a sound event, not hallucinated text. `/tts` surfaced two real, now-handled constraints rather than "it just works": (a) this API key lacks `voices_read`, so listing voices 401s — fixed with a premade-voice fallback (1.3); (b) even with the fallback voice, this is a free-tier account and ElevenLabs returns 402 `paid_plan_required` for any library/shared voice via the API — an account/billing-tier restriction, not a bug, now surfaced with a clear, specific error message (1.5) instead of a generic failure. `/tts` synthesis itself (producing playable audio) was not confirmed on this free-tier account — would need a paid plan or a voice added directly to the account to complete that check
- [x] 3.2 Confirm `GET /providers` lists `elevenlabs` for both `tts` and `stt` — verified live through the real Docker container
