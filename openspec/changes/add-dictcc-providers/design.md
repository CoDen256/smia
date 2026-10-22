## Context

`smia-service-foundation` (archived) shipped `/translations` and `/tts` with dict.cc stubbed out: its public website serves audio and translation data behind an obfuscated anti-bot JS loader, confirmed blocked during implementation. `providers/dict/api.md` documents a different access path entirely — dict.cc's own mobile-app backend (`app_translations.php`, `speak.audio.v2.php`), which is a plain unauthenticated HTTP API keyed by an `appversioncode` query param, not a scraped page. Three static vocabulary dumps (`NO-EN`, `NO-DE`, `DE-EN`, tab-separated: `term1, term2, pos, tags`) were also provided, requested directly from dict.cc under its "private use" license.

Inspecting the API response shape shows one call returns translation entries, an inflection table, and (via a follow-up call keyed by the translation entry's id) both a human recording and a synthesized voice — the same "one adapter backs several kinds" shape already established for kaikki.org.

## Goals / Non-Goals

**Goals:**
- Add `dictcc_api` as a provider for `/translations`, `/tts`, and `/inflections`, replacing the dict.cc stub.
- Add `dictcc_static` as a separate `/translations`-only provider backed by the local dataset import.
- Define how `{from, to}` maps onto dict.cc's `lp`/`dir` request parameters.
- Document the static dataset's license constraint and how the import respects it.

**Non-Goals:**
- Making `dictcc_api` a comprehensive `/inflections` source — `ordbank` remains the authoritative, full-coverage provider; dict.cc is best-effort.
- Supporting language pairs beyond what the static dumps and the user's stated need cover (Norwegian↔English, Norwegian↔German).
- Building a general-purpose dict.cc crawler or mirroring its full dictionary.

## Decisions

### D-DC1: Two separate providers, not one
**Decision**: `dictcc_api` (live) and `dictcc_static` (local import) are registered as distinct provider names, each independently selectable.

**Why**: explicit user direction, and the two have materially different capabilities (API: translations + inflections + audio; static: translations only) and operational profiles (API is a live network dependency with unknown rate limits; static is offline-safe but goes stale until re-imported). Collapsing them into one provider would hide which one actually answered a given request — the same reasoning that ruled out fallback chains in `smia-service-foundation`.

### D-DC2: Language pair mapping is a fixed table, not computed
**Decision**: the `dictcc_api` and `dictcc_static` adapters support only the language pairs smia actually has data for (Norwegian↔English, Norwegian↔German), via an explicit `{(from, to): lp_code}` table with a `dir` computed from which side is `from`. Unsupported pairs return a clear "unsupported pair" error, not a best-effort guess.

**Why**: dict.cc doesn't support arbitrary pairs — only the sub-dictionaries it hosts — and the exact `lp` code per pair needs confirming against the live API (only `DEEN` and `ENNO` are shown in `api.md`'s examples; the `NO-DE` pair's code is unconfirmed — tracked as an open question).

### D-DC3: `dictcc_api`'s `/tts` is a two-step internal flow
**Decision**: fetching dict.cc audio requires the word's dict.cc entry id, which only comes from a prior `app_translations.php` call. The `dictcc_api` `/tts` adapter performs both calls internally; this does not change `/tts`'s one-request contract.

**Why**: `speak.audio.v2.php` is keyed by `id`, not by the word text directly (confirmed in `api.md`'s example, where the audio call's `id=528676` matches the translation entry's `id`).

### D-DC4: Static dataset stays private, per its license
**Decision**: the `dictcc_static` import loads data into smia's own database only; no endpoint ever serves the raw dump files or a bulk export of the imported table.

**Why**: the dataset's license is explicit — "private use is allowed as long as the data... are not published or given away." smia's existing `/translations` response (single-word-pair lookups) is consistent with private use; a bulk-export endpoint would not be.

### D-DC5: `dictcc_static` has no inflections or audio
**Decision**: `dictcc_static` is registered for `/translations` only.

**Why**: confirmed by inspecting the static files directly — columns are `term1, term2, pos, tags`, nothing else. Inflections and audio are `dictcc_api`-only, per D-DC1.

## Risks / Trade-offs

- **[Risk]** `dictcc_api` is an unofficial, reverse-engineered mobile-app backend keyed by `appversioncode` — it could break on a dict.cc app update with no notice. → **Mitigation**: treated like any other scrape-adjacent provider; `/health` tracks its failures, and per `lookup-cache`'s no-fallback rule a `dictcc_api` failure never silently degrades another provider's availability.
- **[Risk]** Hitting the mobile API from a server (not the app) may be against dict.cc's terms even though it's technically open. → **Mitigation**: out of scope for this design to resolve; flagged for the user's own judgment before enabling `dictcc_api` in a shared/public deployment.
- **[Risk]** The static dataset goes stale (snapshot from 2026-10-22) with no automatic refresh. → **Mitigation**: acceptable for now — `dictcc_api` is the live, current source; `dictcc_static` is explicitly the offline-safe fallback, not the primary.

## Migration Plan

Additive only — no existing provider, route, or response contract changes. New adapters register alongside existing ones; the dict.cc stub registration is removed once `dictcc_api` is live.

## Open Questions

- Exact `lp` code for the Norwegian↔German pair (only `DEEN`/`ENNO` are confirmed in `api.md`) — confirm against the live API before implementing that pair.
- Whether dict.cc's mobile backend rate-limits non-app clients, and what `appversioncode` values stay valid over time.
- Whether synthesized voice names (e.g. `Liv`) are stable per language or need per-pair discovery.
