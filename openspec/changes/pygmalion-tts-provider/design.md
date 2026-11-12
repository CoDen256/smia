## Context

Existing `/tts` machinery this change builds on:

- `adapters/kaikki_tts.py` — the closest model: a table-backed provider that
  returns `{"candidates": [{"sha256": …}]}` and is registered with
  `registry.register("tts", "kaikki", Adapter(), count=…)`.
- `adapters/dictcc_api.py` (`DictccApiTtsAdapter`) — already returns candidates
  with extra metadata: `{"sha256", "source": "human"}` and
  `{"sha256", "source": "synthetic", "voice": …}`. The `tts-api` spec says
  "Metadata fields (e.g. `gender`, `source`, `voice`) are present when the
  provider supplies them", so `source` and `voice` are already sanctioned.
- `audio_cache.store(db, bytes, content_type) -> sha256` — content-addressed
  and idempotent; `GET /tts/{sha256}` serves from `tts_audio`.
- `registry.py` — "declarative config, not code paths". There is no separate
  chain file: the set of registered providers per kind *is* the configuration
  `GET /providers` and `/ui` read, and a caller names the provider per request.
- `scripts/bootstrap.py` — `_IMPORTS = [(table, run, args), …]`, each run only
  if its table is empty; `FileNotFoundError` is a skipped-with-warning, not a
  failure.
- `compose.yml` bind-mounts `./providers` read-only at `/app/providers`.

From `pygmalion-audio-fetch`, the manifest has one row per file:
`{word, dialect, take, translation, url, path, status, bytes, sha256}`, and no
file is shared between words or dialects.

## Goals / Non-Goals

**Goals:**
- `provider=pygmalion` returns every recording of an exact word, labelled with
  its dialect, using only existing candidate fields.
- Load once at startup from committed data; no network at import or at lookup.
- A provider that is visible in `/providers` with an honest record count.

**Non-Goals:**
- Inflection, lemmatisation, or fuzzy matching — `/inflect` owns that.
- Tokenised or per-word phrase assembly. A phrase is served only if the data
  has that exact phrase (`la du`, `i-en` are real entries).
- A new response field, a `dialect` field, or an API-level dialect filter.
- Choosing a "best" dialect for the caller (CLAUDE.md: return candidates,
  never one answer).
- Making the audio cache durable or canonical; stabbur owns canonical audio.

## Decisions

### D1: Dialect goes in `voice`; `source` is `human`

```
POST /tts {text:"led", lang:"nb", provider:"pygmalion"}
→ { provider: "pygmalion",
    candidates: [
      {"sha256": "…", "source": "human", "voice": "Oslo"},
      {"sha256": "…", "source": "human", "voice": "Oslo"},
      {"sha256": "…", "source": "human", "voice": "Bergen"} ] }
```

This follows the operator's instruction to reuse what `dictcc_api` returns and
put the dialect under `voice`. `voice` already means "which speaker/rendering",
which a regional speaker is. A caller that only wants one dialect filters on
`voice` itself, so no request-side field is needed.

**Alternative considered:** a new `dialect` field. Rejected by the operator:
it would invent an unspecified field and force stabbur to learn a shape that
no other provider shares.

### D2: A mapping table; bytes in the existing cache

New table `pygmalion_audio`:

```
word      text    -- lowercased, exactly as matched at lookup
dialect   text    -- original spelling, e.g. "Sandnessjøen"
take      int
sha256    text    -- → tts_audio.sha256 (no FK; the cache is a private optimisation)
PRIMARY KEY (word, dialect, take);  INDEX (word)
```

The mp3 bytes live once in `tts_audio` via `audio_cache.store`. The mapping
table is what makes the provider a *table-backed* one for `count=` and for the
bootstrap emptiness check — the same pattern as `kaikki_entry`.

There is deliberately **no foreign key** to `tts_audio`: the audio cache is, by
the `tts-api` spec, a private and evictable optimisation. A lookup whose
`sha256` is no longer in the cache is handled by D6, not by a constraint.

**Alternative considered:** reading the files from `providers/pygmalion/audio/`
at lookup time and calling `store()` lazily, like `kaikki_tts` does with HTTP.
Rejected: it makes `/providers` counts depend on the filesystem at request time,
and breaks if the bind mount is absent while the DB is populated. A load-once
import matches every other provider and is idempotent.

### D3: Import (`scripts/import_pygmalion.py`)

`run(manifest_path)`:

1. Raise `FileNotFoundError` if the manifest is absent (bootstrap already turns
   that into a warning).
2. For each row with `status == "ok"`: read `providers/pygmalion/audio/<path>`,
   **verify its sha256 equals the manifest's** (a corrupted or substituted file
   must not enter the cache), `audio_cache.store(db, data, "audio/mpeg")`, and
   insert `(word.lower(), dialect, take, sha256)`.
3. Rows that are not `ok`, or whose file is missing/mismatched, are skipped and
   counted; the run logs a one-line summary and does not abort.
4. Idempotent: `ON CONFLICT DO NOTHING` on the primary key, and `store()` is
   already a no-op for an existing hash.

`bootstrap._IMPORTS` gains `("pygmalion_audio", import_pygmalion.run,
["providers/pygmalion/audio/manifest.jsonl"])`, using the existing
table-is-empty check.

### D4: Lookup

```
 text ─► strip + casefold ─► SELECT dialect, take, sha256
                             FROM pygmalion_audio WHERE word = :w
                             ORDER BY dialect_rank, dialect, take
                                  │
                                  ▼
            candidates (dedupe by sha256), each
            {"sha256", "source": "human", "voice": dialect}
```

- Exact match on the casefolded, whitespace-stripped input. No
  `query_variants`: citation-form handling is a `dictcc_api`-specific
  requirement, and other providers receive the caller's text unchanged
  (`tts-api` "Other audio providers are unaffected").
- `lang` other than `nb` returns `candidates: []` — the data is Norwegian-only,
  and returning Norwegian audio for an English `led` would be wrong.
- **Ordering**: Oslo first (the reference variety, 86% of the data), then other
  dialects alphabetically, then `take`. Deterministic, so the cached response
  is stable. It is a display order, not a preference — every recording is
  returned.
- Deduplicate by `sha256`, matching `dictcc_api`'s rule.
- A miss is `{"candidates": []}`, a normal successful response, not a
  `ProviderLookupError`.

### D5: Registration is the declarative config

`registry.register("tts", "pygmalion", PygmalionTtsAdapter(),
count=pygmalion_audio_count)`, where the count is `SELECT count(*) FROM
pygmalion_audio` run live per `/providers` call. `adapters/__init__.py` gains
the import. No chain file exists to edit; the registry plus the caller naming
`provider` per request is the existing mechanism, and the provider's narrow
coverage means callers will typically try it first and fall through on
`candidates: []`.

### D6: A mapped hash missing from the audio cache

If the cache was cleared but `pygmalion_audio` was not, `GET /tts/{sha256}` for a
returned hash would 404. Rather than add self-healing to the lookup, the
import's emptiness check is on `pygmalion_audio`, so a cleared **mapping**
reimports everything. For a cleared **cache** with an intact mapping, the
documented recovery is to truncate `pygmalion_audio` and restart. This is a
private research service; the extra machinery is not justified.

### D7: Specs

`tts-api` gets `pygmalion` added to its "Provider set" requirement, and one new
requirement defining the behaviour. No `provider-catalog` delta is needed: its
existing requirement already covers any table-backed provider reporting a
count, and `pygmalion` is simply one more.

## Risks / Trade-offs

- **Tiny coverage (180 words)** → expected and documented; a miss is an empty,
  successful response, so it composes cleanly into a try-in-order chain.
- **Phrase entries** (`la du`) match only the exact phrase, so `la deg` misses.
  Accepted — no inference in a lookup provider.
- **Exact-match brittleness** (`Led` handled by casefold; `leds` not) → the
  caller's job via `/inflect`, per the project's boundary.
- **DB growth of ~8 MB** in `tts_audio` → negligible and rebuildable from the
  committed files.
- **Empty-table-only import** means new fetched words do not appear until the
  table is truncated. This is the same trade-off every other provider makes
  (the repo's own bootstrap comment about not reimporting millions of rows) and
  matches the operator's expectation; a forced reimport is truncate + restart.
- **Dependency ordering** → applying this before `pygmalion-audio-fetch` has
  committed its data yields a skipped-with-warning import and an empty
  provider, not a crash.

## Migration Plan

1. Merge and apply `pygmalion-audio-fetch` (data committed).
2. Apply this change: the Alembic migration creates `pygmalion_audio`; on next
   container start `bootstrap` imports the manifest.
3. Rollback: `alembic downgrade -1` drops the table; the orphaned `tts_audio`
   rows are harmless and are not referenced by anything else.

## Open Questions

- Should `/ui`'s try-it surface `voice` for the new provider's candidates? It
  already renders `dictcc_api`'s `voice`, so likely nothing to do; confirm
  during implementation.
