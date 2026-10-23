## Outcome (post-completion deviation)

`/tts` was implemented per D-EL2 below and live-tested (tasks.md 3.1): listing voices itself can 401 even with a valid token (missing `voices_read` scope), handled with a premade-voice ("Rachel") fallback. But synthesizing with *any* shared/library voice — including that fallback — returns 402 `paid_plan_required` on a free-tier account. Since `_pick_voice` can only ever select a shared/library voice (there's no account-owned voice to select instead), there is no voice this adapter can use on this account tier. `elevenlabs` was unregistered from `/tts` entirely afterward (`ElevenLabsTtsAdapter`, `_pick_voice`, and the voice-fallback constants deleted) — a permanent block on this tier, not a sometimes-failing provider worth leaving registered. `/stt` is unaffected by this and remains as designed below. This change's `tts-api` spec delta was removed accordingly; `tts-api`'s provider set no longer includes `elevenlabs` in any form.

## Context

ElevenLabs was scoped as a `/tts` provider from the start (`smia-service-foundation` D-S7) but left as a `NotConfiguredAdapter` stub because this environment couldn't probe its real API/credential shape at the time. The user now has a working `ELEVENLABS_TOKEN` for local testing and wants both `/tts` (as originally scoped) and `/stt` (newly identified — ElevenLabs also offers speech-to-text) implemented against the official SDK (per `provider-client-libraries`' `provider-client-policy`).

## Goals / Non-Goals

**Goals:**
- One `adapters/elevenlabs.py` module registering real adapters for both `/tts` and `/stt`, using the official `elevenlabs` SDK.
- Remove the `/tts` stub registration for `elevenlabs` from `adapters/not_configured.py`.

**Non-Goals:**
- Wiring `ELEVENLABS_TOKEN` through `docker-compose.yml` — that's `provider-tokens-and-manual-link-fallback`'s job. This change's adapter reads `os.environ["ELEVENLABS_TOKEN"]` (or equivalent via the SDK client constructor) and raises `ProviderLookupError` if absent, same pattern as `deepl.py`.
- Any response-shape changes beyond what the existing `tts-api`/`stt-api` contracts already define — this is "add a provider," not "change the contract."

## Decisions

### D-EL1: One adapter module, two registrations
**Decision**: a single `adapters/elevenlabs.py` constructs one SDK client and registers two adapter classes/instances — `registry.register("tts", "elevenlabs", ...)` and `registry.register("stt", "elevenlabs", ...)` — same pattern as `dictcc_api.py` backing three kinds from one module.

**Why**: one credential, one SDK client, two unrelated-but-adjacent capabilities from the same vendor. Splitting into two files would duplicate the client construction and token-missing error for no benefit.

### D-EL2: TTS candidate metadata
**Decision**: ElevenLabs' `/tts` candidates include whatever voice metadata the SDK's voice-listing/selection surface exposes (at minimum `voice`; `gender` where ElevenLabs' voice metadata provides it). If a specific voice isn't requested, the adapter selects a reasonable default (e.g. a stock multilingual voice) rather than requiring the caller to know ElevenLabs voice IDs — the `/tts` request contract (`{text, lang, provider}`) has no `voice` field per `tts-api`'s existing contract.

**Why**: keeps the `/tts` request shape unchanged across all providers; voice selection becomes an adapter-internal default, consistent with "candidates carry whatever metadata that provider can supply."

## Risks / Trade-offs

- **[Risk]** ElevenLabs' free tier has a monthly character/credit quota; exhausting it mid-testing looks like a provider failure. → **Mitigation**: map quota-exceeded errors to a clear `ProviderLookupError` message distinguishing "quota exceeded" from "misconfigured" from "transient failure," so `/health` and manual debugging aren't confused by an opaque error.
- **[Risk]** ElevenLabs' STT and TTS may have different authentication/initialization requirements despite sharing one API key. → **Mitigation**: verify both paths against the live API during implementation before assuming one client construction serves both.

## Migration Plan

No data migration. Sequencing:
1. Add `elevenlabs` to `requirements.txt`.
2. Implement `adapters/elevenlabs.py` with both registrations.
3. Remove the `elevenlabs` stub from `adapters/not_configured.py` and its registration from `adapters/__init__.py` import list stays (new module replaces the stub's role for that one provider).
4. Tests for both `/tts` and `/stt` paths, mocking the SDK client.

## Open Questions

- Exact ElevenLabs STT endpoint/model name and response shape (needs live probing against the user's token — not guessed here).
- Default voice choice for `/tts` when no voice is specified, and whether `gender` is reliably present in ElevenLabs' voice metadata for that default.
