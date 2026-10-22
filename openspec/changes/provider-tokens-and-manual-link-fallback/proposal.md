## Why

Two separate gaps exist in how provider credentials are handled:

1. **Tokens aren't wired through to the running container.** `docker-compose.yml`'s `backend` service only passes `SMIA_AUTH_TOKEN` through; `HF_TOKEN`, `DEEPL_TOKEN`/`DEEPL_API_KEY`, and the upcoming `ELEVENLABS_TOKEN` exist in the user's local `.env` for testing but are never forwarded into the container's environment, so a provider that works when run natively would silently fail to find its credential under `docker compose up`. The naming is also inconsistent (`DEEPL_API_KEY` in code vs. `DEEPL_TOKEN` in the user's `.env`). (`LibreTranslate` was originally in scope for this same token-naming cleanup, but `provider-client-libraries` drops that provider entirely — nothing to wire a token for anymore.)
2. **Forvo and filmot.com have no free tier**, so they can never be made to "just work" with an env var the way DeepL/ElevenLabs/HF can. Rather than leave them as permanently-failing `NotConfiguredAdapter` stubs, `/tts` should degrade gracefully for these two: return no candidates, but include a `url` the user can open themselves to check that provider's audio for the given word/language by hand.

## What Changes

- Standardize every provider credential env var on a `*_TOKEN` suffix: rename `adapters/deepl.py`'s `DEEPL_API_KEY` → `DEEPL_TOKEN`. `HF_TOKEN` and the upcoming `ELEVENLABS_TOKEN` already match.
- Add every provider token (`HF_TOKEN`, `DEEPL_TOKEN`, `ELEVENLABS_TOKEN`) to `docker-compose.yml`'s `backend.environment`, passed through from the host via `${VAR:-}` (empty default — compose works with or without them set, same spirit as the existing `SMIA_AUTH_TOKEN:-changeme` pattern).
- Add a `.env.example` documenting every token var smia's providers can use, with a one-line comment per var on what it's for and where to get one.
- Replace the `forvo` and `filmot` `NotConfiguredAdapter` `/tts` stubs with real "manual link" adapters: given `{text, lang}`, they SHALL return `{candidates: [], url}` where `url` opens that provider's website with the query/language pre-filled, rather than raising an error — **this is a response-shape addition for `/tts`** (a new `url` field, only present on this adapter type).
- No change to how Forvo/filmot would behave *if* a paid key were ever added later — that would be a future adapter upgrade, not addressed here.

## Capabilities

### New Capabilities
_None._

### Modified Capabilities
- `tts-api`: adds the manual-link response shape (`{provider, candidates: [], url}`) for providers with no accessible API, and updates the `forvo`/`filmot` entries in the provider set to describe this behavior instead of "not configured."

## Impact

- **Affected files**: `docker-compose.yml`, new `.env.example`, `adapters/deepl.py` (env var rename), `adapters/not_configured.py` (forvo/filmot stubs removed), new `adapters/manual_link.py` (or similar) for the forvo/filmot adapters.
- **No impact** on `/inflections`, `/ipa`, `/translations`, `/stt`, or `lookup-cache`.
- Independent of `add-elevenlabs-provider` and `provider-client-libraries` — touches different adapters, though all three touch `/tts`'s provider set and should be sequenced so their spec deltas don't collide (apply this change's `tts-api` delta and `add-elevenlabs-provider`'s separately; neither touches the same requirement text).
