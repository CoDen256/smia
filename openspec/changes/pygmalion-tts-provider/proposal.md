## Why

`pygmalion-audio-fetch` puts ~1,178 human recordings of 180 Norwegian words on
disk, in seven dialects, with a manifest. They are only useful to the rest of
the ecosystem once `POST /tts` can return them.

The coverage is narrow — 180 words, mostly minimal-pair material like
`led / ledd / lapp / labb`, because the data comes from a pronunciation-
training course — but the quality is the point: these are real speakers,
including regional ones (Bergen, Trondheim, Stavanger, …) that no other `/tts`
provider offers. For a word it has, it is the best-labelled audio smia can
return; for the rest it simply answers with no candidates, and the caller
tries another provider.

## What Changes

- **New `pygmalion` `/tts` provider.** `POST /tts {text, lang: "nb",
  provider: "pygmalion"}` returns one candidate per recording of that exact
  word, across all dialects.
- **Candidates reuse the fields `dictcc_api` already returns — nothing new is
  invented.** Each is `{"sha256": …, "source": "human", "voice": "<Dialect>"}`
  with the dialect name (`Oslo`, `Bergen`, `Sandnessjøen`, …) in `voice`. The
  `tts-api` spec already lists `source` and `voice` as provider metadata.
- **Data is loaded at startup, like the other table-backed providers.** A new
  `scripts/import_pygmalion.py` reads the committed manifest, stores each mp3 in
  smia's existing content-addressed audio cache (`audio_cache.store`), and
  records `(word, dialect, take) → sha256` in a new `pygmalion_audio` table.
  `scripts/bootstrap.py` runs it only when that table is empty.
- **Lookup is exact and lowercase.** Inflection and fuzzy matching belong to
  `/inflect`, not here (CLAUDE.md boundary). A miss is
  `{provider, candidates: []}`, not an error.
- **Provider-set and catalog entry.** `pygmalion` is registered in the
  declarative provider registry with a record count, so `GET /providers` and
  `/ui` list it with how many recordings back it.
- **Spec:** `tts-api`'s provider set gains `pygmalion`, and a new requirement
  defines its behaviour.

## Capabilities

### New Capabilities
None.

### Modified Capabilities
- `tts-api`: the provider set gains `pygmalion` (real, multi-dialect human
  recordings from a local table), and a new requirement specifies its lookup,
  its candidate shape (`source: "human"`, `voice: <dialect>`), and its
  ordering and deduplication.

## Impact

- **New** `adapters/pygmalion_tts.py`, `scripts/import_pygmalion.py`, an
  Alembic migration for `pygmalion_audio`, a model in `db/models.py`, and
  tests.
- **Edited** `adapters/__init__.py` (import the adapter), `scripts/bootstrap.py`
  (`_IMPORTS` entry), `db/models.py`.
- **Storage:** ~8 MB of mp3 bytes in the existing `tts_audio` table, via the
  existing `store()`; plus ~1,178 small rows in `pygmalion_audio`.
- `compose.yml` already bind-mounts `./providers` read-only at
  `/app/providers`, so the committed audio is visible to `bootstrap` with no
  Dockerfile or compose change. A missing manifest is skipped with a warning,
  like every other provider's missing source file.
- **No API shape change**: no new request or response fields, and the
  `GET /tts/{sha256}` route serves the audio unchanged.
- Hard boundaries (CLAUDE.md): smia stays a leaf service; the audio cache
  remains a private optimisation (the committed files and manifest are the
  durable source, and the DB can be rebuilt from them); the response records
  which provider answered; the provider is declarative registry config.
- **Depends on** `pygmalion-audio-fetch` having produced and committed
  `providers/pygmalion/audio/manifest.jsonl` and the mp3s. It must not be
  applied first.
- Private research use only.
