## Context

Credential-bearing adapters (`hf_whisper`, `deepl`, soon `elevenlabs`) already read their token from `os.environ` correctly at the adapter level — the gap is one layer up: `docker-compose.yml` never forwards those host-level env vars into the `backend` container, so the same code that works when run natively (`.venv/bin/python ...` picking up a shell-exported `.env`) would find nothing under `docker compose up` unless the compose file explicitly passes each var through. Separately, Forvo and filmot.com were stubbed as `NotConfiguredAdapter` in `smia-service-foundation` for having no accessible free API — that's a permanent fact about those two providers, not a temporary gap to fill with a future key, so they need a real (non-stub, non-erroring) adapter shape instead.

## Goals / Non-Goals

**Goals:**
- Every provider token the codebase reads from `os.environ` is declared in `docker-compose.yml` and documented in `.env.example`, so `docker compose up` with a filled-in `.env` makes every keyed provider work with zero code changes.
- Consistent `*_TOKEN` naming across all provider credentials.
- Forvo and filmot become real, permanently-answering `/tts` adapters whose answer is "here's a link to check yourself," not an error.

**Non-Goals:**
- Finding a paid tier or alternate free access path for Forvo/filmot — out of scope; the user has explicitly chosen the manual-link approach instead.
- Changing how `SMIA_AUTH_TOKEN` (the service's own auth, unrelated to provider credentials) is handled — already correct.

## Decisions

### D-T1: `*_TOKEN` naming convention
**Decision**: every provider credential env var ends in `_TOKEN` (`HF_TOKEN`, `DEEPL_TOKEN`, `ELEVENLABS_TOKEN`). Non-credential config (`HF_WHISPER_MODEL`) keeps its existing, more specific name. (LibreTranslate's `LIBRETRANSLATE_API_KEY`/`LIBRETRANSLATE_URL` are moot — `provider-client-libraries` drops that provider entirely.)

**Why**: matches what the user already put in `.env` for HF/ElevenLabs/DeepL; `deepl.py`'s current `DEEPL_API_KEY` is the one adapter out of step with that.

### D-T2: Pass-through with empty defaults, not required
**Decision**: `docker-compose.yml` declares each token as `${VAR:-}` (empty string if unset on the host), not a hard requirement. A provider whose token is empty continues to fail at adapter-call time with the existing "needs a `*_TOKEN`" `ProviderLookupError` — compose itself never refuses to start over a missing provider key.

**Why**: matches the existing `SMIA_AUTH_TOKEN:-changeme` pattern; smia must stay startable with only some providers configured (D-S1/D-S7's premise that providers are independent, declarative config).

### D-T3: Manual-link is a distinct adapter shape, not a degraded stub
**Decision**: `forvo` and `filmot` get a dedicated small adapter (e.g. `ManualLinkAdapter`, parameterized by a URL-template function per provider) that always "succeeds" with `{candidates: [], url}` — never raises `ProviderLookupError` for "not configured," since there is nothing to configure. This is registered in place of, not alongside, the current `NotConfiguredAdapter` stub for these two.

**Why**: these two are permanently manual by the nature of having no accessible API, not temporarily unconfigured — the response should say so honestly rather than erroring forever. Caching per `lookup-cache` still applies normally since the URL is a pure function of `(text, lang)`.

**URL construction — final, confirmed shapes** (an implementation-time pass got both wrong on the first try; see `tasks.md` 3.1/3.2 for the detour and what corrected it):
- Forvo: `https://forvo.com/word/<url-encoded text>/#<code>` — bare language-code fragment (not `#language-<code>`, which is an on-page section anchor id, not the shareable link format). `<code>` uses Forvo's own scheme (`nb`->`no`, others pass through).
- filmot: `https://filmot.com/search/<url-encoded text, +-joined>/1?gridView=1&lang=<code>` — confirmed from a real shared filmot results link, not the public search page's client-rendered form (which CAPTCHA-blocked submission and couldn't be inspected directly). Same `nb`->`no` code mapping as Forvo.

## Risks / Trade-offs

- **[Risk]** filmot's exact public search URL shape was unconfirmed at design time (only its keyed API was probed in `smia-service-foundation`). → **Resolved**: confirmed from a real shared filmot results link (see `tasks.md` 3.2) — `https://filmot.com/search/<query>/1?gridView=1&lang=<code>`.
- **[Risk]** Renaming `DEEPL_API_KEY`→`DEEPL_TOKEN` is a breaking env-var rename for anyone who already set the old name. → **Mitigation**: low risk — this service isn't deployed yet; document the rename in this change's tasks so it's a deliberate, one-time cutover, not silent.

## Migration Plan

No data migration. Sequencing:
1. Rename the env var in `deepl.py`.
2. Update `docker-compose.yml` with all token pass-throughs.
3. Write `.env.example`.
4. Implement the manual-link adapter and register it for `forvo`/`filmot`, removing their `NotConfiguredAdapter` entries.
5. Update tests.

## Open Questions (resolved)

- ~~filmot's actual public search URL shape (needs live confirmation).~~ Confirmed: `https://filmot.com/search/<query>/1?gridView=1&lang=<code>`.
- ~~Whether Forvo's `#<lang>` fragment uses the same two-letter codes smia uses internally (`nb`, `en`, `de`) or Forvo's own language code scheme.~~ Confirmed: Forvo's own scheme (`nb`->`no`, others pass through), bare `#<code>` fragment.

## Related follow-up (not part of this change's scope)

Dynamic per-provider unregistration (`registry.register(..., available=lambda: bool(os.environ.get("X_TOKEN")))`, excluding a provider from `providers_for`/`resolve_provider`/`GET /providers` when its token isn't configured) was added afterward, wired up for `deepl`, `hf_whisper`, and `elevenlabs`. It builds on this change's token-naming/wiring work but is a `provider-catalog`-capability behavior, not scoped here — not tracked by this change's own tasks/spec delta.
