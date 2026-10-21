## Context

smia is unimplemented. `tun/docs/06-smia.md` sketches five endpoints as "chain with fallback" provider lists, but that design predates two things now on hand: (1) a working-through of the actual use cases (hover's fast-then-enrich flow, stabbur's triage UI) that showed no endpoint ever needs smia to pick a winner among providers, and (2) a `providers/` directory in this repo containing real downloaded data — a full Norsk Ordbank export, an NST pronunciation lexicon with dialect variants, a kaikki.org/Wiktionary dump, and the ordbokene.no API spec — that resolves what was previously an open question (`tun/docs/09-open-questions.md` Q10) and substantially changes the `/ipa` and `/tts` provider shortlists documented in `06-smia.md`.

This design covers the service skeleton, the shared provider-execution/cache model all five endpoints build on, the REST shape, and the concrete first-provider set per endpoint.

## Goals / Non-Goals

**Goals:**
- Define a single, reusable provider-execution + cache mechanism used by all five endpoints.
- Define the REST resource shape (content-addressed, idempotent `POST`, fetch-by-id `GET`).
- Pin down the first real provider(s) per endpoint, grounded in the data already in `providers/`.
- Define auth simple enough not to need rework when hover-translate/stabbur arrive as callers.

**Non-Goals:**
- Implementing fallback chains, fan-out, or any provider-ranking logic (explicitly dropped — see Decisions).
- Building the full Norsk Ordbank → Postgres import pipeline in detail (scoped to tasks.md as an implementation step, using the schema established here).
- Resolving filmot.com's exact API contract (its docs page is JS-rendered; needs hands-on probing — tracked as an open question).
- STT segment-level timestamps (deferred; `/stt` ships text-only in this change).
- Resolving dict.cc's and ElevenLabs free tier's exact API contracts in full detail (tracked as implementation-time work in tasks.md).

## Decisions

### D-S1: No fallback chains; caller names exactly one provider
**Decision**: every endpoint requires a `provider` field (optional only when a kind has a single configured provider). smia calls exactly that provider, cache-first, and returns one object. No endpoint tries a second provider on failure.

**Why**: all providers in use are free (no API costs to economize), so "try cheapest first" has no basis. The two real callers — hover's tooltip (fast-local-then-enrich, async, not latency-sensitive to smia) and stabbur's triage UI (wants to compare specific providers) — both already decide which provider(s) they want; smia doing its own picking would be redundant and would hide information from callers that want it.

**Alternatives considered**:
- *Fallback-until-success* (the original `06-smia.md` design): rejected — not needed without cost pressure, and hides which providers were tried/failed from the caller.
- *Fan-out to all providers, return array*: rejected per explicit user direction — adds concurrency/timeout handling for no benefit once "one provider per call" is accepted; the caller can issue N requests if it wants N answers.

### D-S2: REST resources addressed by content hash
**Decision**: `POST /<kind>` creates-or-fetches a resource whose id is `sha256(kind, provider, input)`; `GET /<kind>/{id}` fetches it without recomputation. Paths stay close to `06-smia.md`'s originals: `/ipa`, `/tts`, `/stt` (acronyms kept as-is), `/inflections`, `/translations` (pluralized nouns).

**Why**: the cache key already needed to be content-addressed (naob/Forvo/cost-sensitive providers in the original design). Making that id the actual resource id gets idempotent retries and direct-link fetch (useful for stabbur triage, `/ui` manual try-it) for free, and gives `/ui`'s "database exploration" (D46) a natural collection to browse.

**Alternatives considered**: pure RPC-style verb endpoints (`POST /inflect` returning a result with no addressable id) — simpler but throws away the idempotency and linkability benefits for no real savings.

### D-S3: One shared provider-runner, not five
**Decision**: implement the cache-check → call-provider → store → return flow once; every endpoint handler is a thin wrapper that supplies its kind, its provider registry, and its input-normalization/output-shape logic.

**Why**: all five endpoints have the mechanically identical shape per D-S1/D-S2. The only per-endpoint variation is the input schema, the provider adapter interface, and the output shape.

### D-S4: A provider can be "a query against an imported dataset," not just a network call
**Decision**: the provider abstraction covers both live calls (scrape, API) and lookups against a locally-imported table (Norsk Ordbank, NST lexicon, kaikki.org dump). The kaikki.org dataset in particular backs three different kinds (`/inflect` via `forms`, `/ipa` via `sounds[].ipa`, `/tts` via `sounds[].mp3_url`) from one imported table — importing it once and exposing three query paths over it, rather than treating it as three unrelated providers.

**Why**: discovered directly from inspecting `providers/kaikii/kaikki.org-dictionary-NorwegianBokmål.jsonl` — forcing every provider into "one network call" would mean importing/parsing that file three times. The same pattern applies to dict.cc, which is registered as both a `/translations` provider (contextual translation entries) and a `/tts` provider (real recorded pronunciation audio) — one adapter's scrape, two kinds' worth of data extracted from it.

### D-S5: Service stack
**Decision**: Python backend, its own Postgres database, matching phonexa's existing stack (Flask-style app, `alembic` migrations, server-rendered `/ui` — same pattern as phonexa's `shadow.html`/`shadowing.py`) rather than introducing a new language/framework into the ecosystem.

**Why**: solo-dev consistency; phonexa already proves this stack works for a small-footprint (~100MB RAM target per `02-services.md`) service with its own admin UI.

### D-S6: Auth — one shared bearer token
**Decision**: a single long-lived random token, env-configured, checked on every request. No per-client identity, no scopes.

**Why**: matches D01's ecosystem-wide pattern (single user, token not identity). smia has no dependents yet (hover-translate, stabbur arrive later); a shared token is the simplest thing that doesn't need rework — adding per-client tokens later is additive, not a breaking change, since the check (`is this token valid`) doesn't change shape.

### D-S7: Per-endpoint provider shortlist (first pass)

| Endpoint | Request | Response | Providers, in no particular order (no chain) | Source |
|---|---|---|---|---|
| `/inflections` | `{word, lang, provider}` | `{provider, candidates: [{lemma, pos, paradigm}]}` | `ordbank` (local import: `fullformsliste.txt` joined against `lemma.txt`/`paradigme.txt`/`boying.txt`, primary); `kaikki` (`forms[]`, secondary, imperative/passive-tagged forms excluded) | `providers/nbno/*ordbank*.tar.gz`, `providers/kaikii/` |
| `/ipa` | `{text, lang, provider}` | `{provider, candidates: [{phonemic?, phonetic?, variety}]}` | NST NOFABET lexicon (local, dialect-aware, needs the bundled NOFABET→IPA conversion table); kaikki.org dump (`sounds[].ipa`, ~13% coverage); ordbokene.no API (`body.pronunciation`); ipa-dict/nb (lemma-only, thin); wikipron's bundled `nob_latn_broad.tsv` (thin) | `providers/nbno/nb_uttale_*`, `providers/kaikii/`, `providers/ordbokene/`, `providers/open-dict/`, `providers/wikipron/` |
| `/tts` | `{text, lang, provider}` | `{provider, candidates: [{sha256, ...metadata}]}` | Forvo (real recordings); dict.cc (real recordings, non-generated); kaikki.org `sounds[].mp3_url` (real recordings, ~3% coverage); filmot.com (locate a real spoken instance in YouTube captions, slice that audio); ElevenLabs free tier (synthesis) | `providers/kaikii/`, user-confirmed filmot intent |
| `/translations` | `{text, from, to, provider}` | `{provider, text, context?}` | Google Translate (scrape, ported from `TranslatorFactory`/`google.ts`), Bing (scrape, ported from `bing.ts`), DeepL (official free-tier API), LibreTranslate (self-hosted or public instance), dict.cc | `hover-translate/extension/src/common/translators/` |
| `/stt` | audio body + `{provider}` (required) | `{provider, text}` | `hf_whisper` (Hugging Face Inference, whisper), cloud-only per D17 — the only provider, but still required per-request, not defaulted | ported from `phonexa/js/shadow.js`'s `transcribeViaHuggingFace` |

Naob (scrape-only, phonemic-only, frequently down) and espeak-ng (g2p approximation, not a real pronunciation lookup) are both excluded from `/ipa` — every configured provider is a genuine pronunciation source. piper is excluded from `/tts` in favor of ElevenLabs' free tier.

## Risks / Trade-offs

- **[Risk]** `forms` tags in kaikki.org (e.g. splits `imperative`/`passive` separately) don't map cleanly onto stabbur's existing 4-key verb paradigm shape (`infinitiv, presens, preteritum, perfektum`). → **Mitigation**: `imperative`/`passive`-tagged forms are dropped at the `kaikki` adapter boundary (see `inflect-api` spec); `ordbank` remains the primary, shape-matching provider, and `/inflect` never merges the two — a caller gets one provider's candidates per request.
- **[Risk]** filmot.com's real API contract is unknown (docs page is JS-rendered, not scraped successfully). → **Mitigation**: tracked as an open question; probe directly (browser tool or manual `curl` against the v1 endpoints) before writing the filmot adapter.
- **[Risk]** Dropping fallback chains is a breaking change versus `06-smia.md`'s documented shapes, discovered mid-design rather than at initial scoping. → **Mitigation**: `06-smia.md` itself will need a follow-up doc update (noted in proposal's Impact section) once this change lands, so future readers don't find the two designs in conflict.
- **[Risk]** No segment-level timestamps for `/stt` in this pass could block a future stabbur feature that wants them. → **Mitigation**: explicitly deferred, not foreclosed — HF's endpoint supports timestamp requests; the response shape can grow `segments` additively later.

## Migration Plan

Net-new service, no existing deployment to migrate. Sequencing (detailed in tasks.md):
1. Service skeleton + auth + `lookup-cache` mechanism.
2. `/inflections` (Norsk Ordbank import) — proves the full stack end-to-end with the richest local dataset.
3. `/ipa`, `/translations`, `/tts`, `/stt` provider adapters.
4. `/providers`, `/health`, `/ui`.
5. Only after smia is live: migrate hover-translate's `TranslatorFactory` call sites and phonexa's `shadow.js` transcription call sites to call smia instead (separate changes, out of scope here but noted as the consumers that motivate this one).

## Open Questions

- Exact filmot.com v1 API shape (endpoints, auth, rate limits) — needs hands-on probing.
- ElevenLabs' and dict.cc's exact free-tier API contracts (rate limits, response shapes) — needs hands-on probing before writing those adapters.
- `ordbank` and `kaikki` are both configured for `/inflect` and can disagree on a word's paradigm (e.g. kaikki's finer-grained tagging vs. ordbank's ordbank-paradigm slots). Since the caller must already name one provider per `lookup-cache`, this may not need resolving at all — each provider simply returns its own candidates independently, never merged. Confirm this is sufficient before implementation.
- Whether `/stt` should request HF timestamp output now (cheap incremental cost) or defer entirely until a consumer actually needs `segments`.
