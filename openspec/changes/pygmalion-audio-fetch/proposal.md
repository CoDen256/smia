## Why

NTNU's Pygmalion / LearnNoW pronunciation-training data
(`providers/pygmalion/vowels.json`, `consonants.json`) references real human
recordings of Norwegian words, spoken in seven dialect areas. The JSON only
holds **paths into the authors' Windows machine**
(`C:\CalstFiles\WordObjectContent\Norwegian\Words_MP3\Oslo_Normal_….mp3`);
the audio itself is served from
`https://polymetis.hf.ntnu.no/static/WordObjectContent/Norwegian/Words_MP3/`.
Nothing in smia can use those recordings until they are on disk.

Measured against the two files:

| | |
|---|---|
| Unique words | 180 (some are phrases: `la du`, `i-en`) |
| Audio references | 2,585 |
| **Unique mp3 files** | **1,178** (~8 MB at ~6.5 KB each) |
| Dialects with data | Oslo 2213 refs, Bergen 150, Stavanger 56, Trondheim 56, Elverum 40, Sandnessjøen 40, Malm 30 (Tromsø: always empty) |

The 2,585→1,178 gap is the same word repeated across exercises; no file is
shared between different words or different dialects (verified).

This change fetches the audio and records what was fetched. It is the data
half of a later `/tts` provider (`pygmalion-tts-provider`) and ships no
service behaviour itself.

## What Changes

- **New** `scripts/fetch_pygmalion_audio.py`, run as
  `python -m scripts.fetch_pygmalion_audio <extract|download>`:
  - `extract` — offline and pure. Walks the nested
    `soundgroups → dictionary → MP_wordpair[]` structure of both JSON files,
    maps every `audio_<Dialect>` Windows path to its remote URL, dedupes by
    URL, and writes `providers/pygmalion/audio/manifest.jsonl`. Re-running it
    preserves the download status of rows that already exist.
  - `download` — fetches every manifest row not yet done, politely, into
    `providers/pygmalion/audio/<Dialect>/<basename>.mp3`.
- **The manifest is the resume state.** Files are written to `.part` and
  atomically renamed; the manifest is rewritten atomically after each file.
  Ctrl-C at any instant leaves a state the next run continues from.
- **Polite by construction:** one connection, 0.5–1 s jitter between
  requests, `Retry-After` honoured, exponential backoff on 429/5xx/network
  errors, an identifying `User-Agent`.
- **Rich terminal UI** (`rich`): live progress bar with ETA and rate, the
  current word and dialect, ok/skipped/failed counters, a scrolling log of
  retries and warnings, and a final summary table. Degrades to plain log lines
  when stdout is not a TTY.
- `rich` is added to `requirements-dev.txt` (dev-time script dependency, not
  in the runtime image).
- The downloaded mp3s and `manifest.jsonl` are **committed** (~8 MB), not
  gitignored and not zipped.

## Capabilities

### New Capabilities
- `pygmalion-audio-fetch`: extraction of the Pygmalion recording inventory
  into a manifest, and its resumable, rate-limited download.

### Modified Capabilities
None. No existing smia behaviour changes; the HTTP API is untouched.

## Impact

- **New** `scripts/fetch_pygmalion_audio.py`, `tests/test_pygmalion_fetch.py`.
- **New data**: `providers/pygmalion/audio/` (≈1,178 mp3s + `manifest.jsonl`,
  ≈8 MB plus ≈0.3 MB).
- `requirements-dev.txt`: `+rich`.
- Not touched: `app.py`, `registry.py`, `adapters/`, the DB, migrations.
- Hard boundaries (CLAUDE.md) are untouched: smia stays a leaf service, and
  this is an offline data-preparation step with no dependency on any other
  Tun service.
- Private research use only; no redistribution is intended or implemented.
- **Followed by** `pygmalion-tts-provider`, which consumes the manifest.
