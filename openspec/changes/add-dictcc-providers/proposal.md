## Why

`smia-service-foundation` shipped with two dict.cc-shaped tasks stubbed out (`adapters/not_configured.py`) because scraping dict.cc's website directly hit an obfuscated anti-bot JS loader: task 5.3 (`/tts` real recordings) and task 6.5 (`/translations`). New material has since turned up in `providers/dict/`: `api.md` documents dict.cc's actual mobile-app backend (`app_translations.php` / `speak.audio.v2.php`, keyed by a legitimate `appversioncode` rather than a scraped page), and three static vocabulary dumps (`NO-EN`, `NO-DE`, `DE-EN`) requested directly from dict.cc. Both are a different access path than the blocked web scrape, so both are worth adding as providers now.

Inspecting `api.md` also surfaced more than a `/translations` and `/tts` fix: a single `app_translations.php` call returns `translations[]`, an `inflections`/`inflections_repl` table, *and* ties to `speak.audio.v2.php` for both a real human recording and a synthesized "robot" voice — one dict.cc API adapter backs three kinds, the same "one dataset/one adapter, several query paths" pattern already established for kaikki.org in `smia-service-foundation`.

The user asked for the live API and the static dataset to be modeled as two distinct providers, not one — they have materially different capabilities (the static dump is translation-pairs-only, no inflections, no audio) and different operational characteristics (API needs no local storage but is a live dependency; the static dump is offline-safe but needs re-fetching to stay current, and its license is private-use-only — fine for an internal service, not republishable).

## What Changes

- Add `dictcc_api` as a new provider, backed by dict.cc's mobile-app backend:
  - `/translations`: `translations[]` → `{provider, text, context?}` (`context` built from `entry_type`/domain tags, e.g. `[zool.]`).
  - `/inflections`: `inflections_repl` → the existing paradigm shapes (confirmed structurally compatible — e.g. a `NOUN` table's `indefinite.sg | definite.sg | indefinite.pl | definite.pl` maps directly onto `substantiv {article, sg_indef, sg_def, pl_indef, pl_def}`). Coverage is best-effort — dict.cc only returns an inflection table for some word classes/entries, unlike ordbank's full paradigm coverage.
  - `/tts`: `speak.audio.v2.php` → one candidate per available recording, tagged by `source` (`human` recording vs `synthetic` voice, e.g. `voice: "Liv"`). Requires first resolving the word's dict.cc entry id via the translations call — an internal two-step inside the adapter, not a change to the one-request `/tts` contract.
- Add `dictcc_static` as a second, separate new provider, backed by the local import of the `NO-EN`/`NO-DE`/`DE-EN` tab-separated dumps:
  - `/translations` only: direct lemma-pair lookup → `{provider, text, context?}` (`context` built from the dataset's POS/domain-tag columns). No inflections, no audio — the dataset doesn't carry them.
- Un-stub `smia-service-foundation` tasks 5.3 (`/tts` dict.cc) and 6.5 (`/translations` dict.cc) now that a working access path exists; replace the `not_configured.py` registration for dict.cc with the real `dictcc_api` adapter.
- **BREAKING for nothing** — this only adds providers to existing kinds; no existing request/response contract changes.

## Capabilities

### New Capabilities
_None — this adds providers to existing capabilities, not new endpoint behavior._

### Modified Capabilities
- `translate-api`: adds `dictcc_api` and `dictcc_static` to the provider set.
- `tts-api`: adds `dictcc_api` to the provider set (replaces the `not_configured` stub), with `source`/`voice` candidate metadata.
- `inflect-api`: adds `dictcc_api` as a third provider, with explicitly best-effort (not full) coverage.

## Impact

- **smia**: new `adapters/dictcc_api.py` and `adapters/dictcc_static.py`; a local import job for the three static dumps (mirroring the kaikki/ordbank import pattern); removal of the dict.cc `not_configured` stub registration.
- **Licensing**: the static dataset's terms ("private use... not published or given away") are compatible with smia's own private, non-redistributing use — noted in design.md so the import job doesn't accidentally expose the raw dump files.
- **No impact on mjolnir.**
