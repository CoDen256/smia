## 1. Prerequisite check

- [x] 1.1 Confirm `pygmalion-audio-fetch` is applied: `providers/pygmalion/audio/manifest.jsonl` exists, its `status: "ok"` rows each have a file, and the mp3s are committed. This change must not ship first (proposal: Impact).
- [x] 1.2 Re-read `adapters/kaikki_tts.py`, `adapters/dictcc_api.py`'s `DictccApiTtsAdapter`, and `adapters/kaikki.py`'s `kaikki_entry_count` to match their conventions for `lookup()`, `session_scope()` and `count=`.

## 2. Schema

- [x] 2.1 Add a `PygmalionAudio` model to `db/models.py`: `word` (Text), `dialect` (Text), `take` (Integer), `sha256` (Text); composite primary key `(word, dialect, take)`; index on `word`. No foreign key to `tts_audio` (design D2).
- [x] 2.2 Add an Alembic migration creating `pygmalion_audio`. Find the real head with `alembic heads` rather than guessing it from filenames; include a working `downgrade` that drops the table (design Migration Plan).
- [ ] 2.3 Run the migration against a scratch DB: upgrade → downgrade → upgrade all succeed. **NOT VERIFIED — no Postgres available when applied (Docker daemon down); revision graph (single head `e6b3a9d2f401`) and offline upgrade/downgrade SQL were checked with `alembic --sql`.**

## 3. Import

- [x] 3.1 Create `scripts/import_pygmalion.py` with `run(manifest_path)`; raise `FileNotFoundError` when the manifest is absent (design D3).
- [x] 3.2 For each `status == "ok"` row read `providers/pygmalion/audio/<path>` relative to the manifest, verify its sha256 against the row, then `audio_cache.store(db, data, "audio/mpeg")`.
- [x] 3.3 Insert `(word.casefold(), dialect, take, sha256)` with `ON CONFLICT DO NOTHING`; skip and count rows that are not `ok`, missing on disk, or hash-mismatched; print one summary line (imported / skipped / mismatched).
- [x] 3.4 Add the entry to `scripts/bootstrap.py`'s `_IMPORTS`: `("pygmalion_audio", import_pygmalion.run, ["providers/pygmalion/audio/manifest.jsonl"])`, plus the `from scripts import …` addition.

## 4. Adapter

- [x] 4.1 Create `adapters/pygmalion_tts.py` with `PygmalionTtsAdapter.lookup(input_dict)` per design D4: `lang != "nb"` → `{"candidates": []}`; casefold + strip `text`; exact `WHERE word = :w`.
- [x] 4.2 Order results Oslo first, then other dialects alphabetically, then `take`; dedupe by `sha256`; emit `{"sha256", "source": "human", "voice": dialect}` and nothing else (spec "no new field").
- [x] 4.3 Do **not** call `query_variants` and do not retry with a stripped article (spec "No citation-form fan-out").
- [x] 4.4 Add `pygmalion_audio_count(db)` and register `registry.register("tts", "pygmalion", PygmalionTtsAdapter(), count=pygmalion_audio_count)`; add `from . import pygmalion_tts  # noqa: F401` to `adapters/__init__.py` (design D5).

## 5. Tests

- [x] 5.1 `tests/test_import_pygmalion.py` against a small fixture manifest + a few tiny files: rows are inserted, mp3 bytes land in `tts_audio`, a second run inserts nothing, a non-`ok` row and a missing file are skipped, a hash-mismatched file is skipped and counted and stores nothing.
- [x] 5.2 `FileNotFoundError` on an absent manifest, and `bootstrap` turns it into a warning rather than a crash (skip-when-populated is also asserted).
- [x] 5.3 `tests/test_pygmalion_tts.py` for the adapter: a word with 2 Oslo + 1 Bergen recordings yields 3 candidates ordered Oslo, Oslo, Bergen with `voice` set and keys exactly `{sha256, source, voice}`.
- [x] 5.4 Casefold and whitespace: `"  Led "` equals `"led"`. Phrases: `"la du"` matches exactly, `"la deg"` is empty.
- [x] 5.5 Unknown word → `{"candidates": []}`, no exception; `lang="en"` → empty; `"en kalv"` is not retried as `kalv`.
- [x] 5.6 Dedupe by `sha256`: two rows with identical hash produce one candidate.
- [x] 5.7 End-to-end through the app: `POST /tts` with `provider=pygmalion` returns the shape above, and `GET /tts/{sha256}` for a returned hash returns the bytes with `audio/mpeg`.
- [ ] 5.8 `GET /providers` lists `pygmalion` under `tts` with a live row count, and the count changes after an import without a restart. **Route test is written (`test_providers_lists_pygmalion_with_a_live_count`) but NOT RUN: `/providers` also counts `examples` with Postgres-only `= ANY()`. The registry-level count wiring is tested and passes.**
- [ ] 5.9 Run the full existing suite (`pytest`) and confirm no `dictcc_api`/`kaikki` `/tts` tests changed behaviour. **NOT RUN — the existing suite needs a migrated Postgres. Only the new tests and tests/test_pygmalion_fetch.py were run (51 passed on in-process SQLite).**

## 6. Verify on real data and document

- [ ] 6.1 Start the service on a fresh DB; confirm the log shows the import and that `GET /providers` reports a count equal to the number of `ok` manifest rows. **NOT DONE — needs Postgres/Docker. 6.2/6.3 were instead verified through the real Flask app on SQLite with the real corpus imported (1,176 rows).**
- [x] 6.2 `POST /tts {"text":"led","lang":"nb","provider":"pygmalion"}` → candidates for the Oslo recordings of `led`; fetch one `sha256` and play the mp3.
- [x] 6.3 A word with a regional recording (e.g. one with `Bergen`) shows `voice: "Bergen"`; a word not in the data (e.g. `hest`) returns `candidates: []`. (Verified on SQLite: `led` → 2 Oslo; `de` → Oslo+Bergen; `bolig` → 2; `hest`/`en kalv` → empty.)
- [x] 6.4 Check `/ui`'s try-it renders the `voice` for `pygmalion` candidates; resolve design Open Question 1.
- [x] 6.5 Update `README.md` / any provider documentation that enumerates `/tts` providers to include `pygmalion`, noting its 180-word coverage.
