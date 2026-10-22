## Why

smia is currently unimplemented — a name and a design sketch in `tun/docs/06-smia.md`. Two real systems already duplicate the work smia exists to absorb: hover-translate's `TranslatorFactory` (Google/Bing scrape translators) and phonexa's Shadowing STT config (local/HF whisper). Standing up smia's actual shape — API, provider execution model, cache, and the first real providers — unblocks both migrations and removes that duplication (D16).

Exploration (via `/opsx:explore`) surfaced that two of `06-smia.md`'s design assumptions don't hold once examined against real constraints and real data the user has already gathered:

1. **No endpoint should pick a "winner" among providers.** The original design mixed "chain with fallback" (one answer) and "return all candidates" (`/inflect`, `/translate`) inconsistently. Since every provider used is free (no cost pressure to minimize calls), the simplest and most consistent model is: the caller names exactly one provider per call, smia executes it (cache-first) and returns one normalized object. Provider selection is entirely a frontend/caller concern (hover-translate's fast-then-enrich flow and stabbur's triage UI both confirm this — neither needs smia to decide).
2. **The provider landscape is much richer than `06-smia.md`'s three-provider chains**, once the user's downloaded raw data (`providers/`) is inspected: a full relational Norsk Ordbank export (resolves the long-open Q10), an NST pronunciation lexicon in NOFABET notation with dialect variants and a working NOFABET→IPA conversion table, a kaikki.org/Wiktionary dump usable for `/inflect`, `/ipa`, *and* `/tts` (real recorded audio), and the official ordbokene.no API. The original naob→ipa-lookup→espeak and Forvo→dict.cc→cloud→piper chains undersell what's actually available and already on disk.

This change defines the service skeleton, the shared provider-execution/cache model, and the REST surface for all five endpoints, informed by that research — before any code is written.

## What Changes

- Stand up smia as a Python service (consistent with phonexa's existing stack) with its own Postgres database (D42: no cross-service FKs).
- **Drop chain-with-fallback entirely.** Every endpoint takes an explicit `provider` field (required whenever more than one provider is configured for that kind) and returns a result tagged with that provider — **BREAKING** relative to `06-smia.md`'s original per-endpoint shapes (`/ipa` and `/tts` were previously documented as single-winner outputs from an implicit chain; `/translate`'s original array-of-all-providers shape is also dropped in favor of one request naming one provider).
- **Candidates, not a single winner, wherever a provider's own data is inherently multi-valued** — not just `/inflect`'s long-standing ambiguity rule, but now also `/ipa` (one provider can hold several dialect/variety pronunciations) and `/tts` (one provider can hold several recordings/speakers). This is still "one provider per call," just acknowledging that one provider can legitimately return more than one item.
- REST-ify the five endpoints around content-addressed resources: `POST /ipa`, `POST /tts`, `POST /stt`, `POST /inflections`, `POST /translations`, each idempotent (resource id = `sha256(kind, provider, input)`), each fetchable by id via `GET`.
- Add `GET /providers` (full catalog, all kinds) and `GET /health` (per-provider last-success/failure, quota) as the data `/ui` renders — no dynamic/persisted chain reordering, no fan-out, no racing.
- Implement the provider-execution/cache runner once, reused by all five endpoints: cache check on `(kind, provider, sha256(input))` → call provider on miss → store → return.
- Import/wire the first real providers per endpoint based on research (see design.md):
  - `/inflections` `{word, lang, provider}` → `{provider, candidates: [{lemma, pos, paradigm}]}` — Norsk Ordbank (local Postgres import, primary) and kaikki.org `forms[]` (secondary, imperative/passive forms excluded). Adverb paradigms gain optional `komparativ`/`superlativ` only when the source paradigm defines degree inflection (confirmed against the ordbank data: plain adverbs are invariable, "adjektiv, adverbtype" adverbs inflect for degree).
  - `/ipa` `{text, lang, provider}` → `{provider, candidates: [{phonemic?, phonetic?, variety}]}` — NST NOFABET lexicon, kaikki.org `sounds[].ipa`, ordbokene.no, ipa-dict/nb, wikipron. naob and espeak-ng dropped entirely.
  - `/tts` `{text, lang, provider}` → `{provider, candidates: [{sha256, ...metadata}]}` — Forvo, dict.cc (real recordings), kaikki.org `sounds[].mp3_url`, filmot.com (locates a real spoken clip in YouTube captions via its API and slices it), ElevenLabs free tier (synthesis). piper dropped.
  - `/translations` `{text, from, to, provider}` → `{provider, text, context?}` — Google/Bing scrape, DeepL, LibreTranslate, dict.cc. No `lang`, `transliteration`, or `transcription` in the response; the former `dictionary` field is renamed `context` (meaning-specific disambiguation).
  - `/stt` audio body + `{provider}` (always required, even with one provider configured) → `{provider, text}` — Hugging Face Inference (whisper) only, matching D17.
- Auth: a single long-lived shared bearer token (D01-style), env-configured, no per-client identity — simplest thing that doesn't need rework when hover-translate/stabbur arrive as callers.

## Capabilities

### New Capabilities
- `lookup-cache`: the shared single-provider execution + cache contract every endpoint is built on — `(kind, provider, sha256(input))` keying, idempotent create, fetch-by-id.
- `inflect-api`: `POST /inflections` — Norwegian inflection lookup returning candidates (never one answer) from the Norsk Ordbank import.
- `ipa-api`: `POST /ipa` — phonemic/phonetic transcription lookup across the researched provider set.
- `tts-api`: `POST /tts` — audio clip lookup/synthesis across the researched provider set, writing into smia's private content-addressed cache.
- `translate-api`: `POST /translations` — single-provider translation lookup, absorbing hover-translate's `TranslatorFactory`.
- `stt-api`: `POST /stt` — cloud-only (Hugging Face Inference) speech-to-text, absorbing phonexa's Shadowing STT config.
- `provider-catalog`: `GET /providers` and `GET /health` — the catalog and status data backing `/ui`.

### Modified Capabilities
_None — smia has no existing specs yet._

## Impact

- **New repo contents**: smia's service code, its own Postgres schema/migrations, provider adapter modules, the Norsk Ordbank import job.
- **hover-translate**: `TranslatorFactory`/`BaseTranslator`/`google.ts`/`bing.ts` are superseded by a call to `POST /translations`; the extension's fast-local-then-enrich pattern (D32) is unaffected — local translation stays client-side for speed, smia is the async enrichment call.
- **phonexa**: `shadow.js`'s local faster-whisper path (`formanter.py` backend selector, HF fallback) is replaced by a single call to smia's `POST /stt`; the local-backend option in Settings goes away.
- **tun/docs**: `06-smia.md`'s endpoint table and `07-decisions.md`/`09-open-questions.md` (Q10) need updates once this change lands, to record the no-fallback/single-provider model and the resolved ordbank shape.
- **No impact on mjolnir or its progress** (explicitly out of scope, per the exploration request).
