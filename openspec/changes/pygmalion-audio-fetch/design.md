## Context

The source JSON nests every recording like this:

```
{ "soundgroups": [ { sound, sidekicks, dictionary: {
     "<sidekick>": [ { …exercise…, MP_wordpair: [
        { word: "led", Translation: ["fairway"],
          audio_Oslo:      ["C:\\CalstFiles\\…\\Words_MP3\\Oslo_Normal_4XTO….mp3", …],
          audio_Bergen:    [], audio_Trondheim: [], audio_Stavanger: [],
          audio_Malm: [],     audio_Elverum: [],  audio_Sandnessjøen: [],
          audio_Tromsø: [] } ] } ] } } ] }
```

Facts established by inspecting the two files and probing the server:

- 408 `MP_wordpair` records → 180 unique words; 2,585 audio references →
  **1,178 unique files**. A file is never shared between two different words
  or two dialects, so a file has exactly one `(word, dialect)`.
- 2,583 paths match `C:\CalstFiles\WordObjectContent\Norwegian\Words_MP3\<file>.mp3`.
  Two are `D:\Workspace\…\OriginalWords_Wav\anMtr_…bolig….wav` — raw WAVs in a
  directory the server mapping does not reach.
- The dialect **must** come from the JSON key, not the filename: the key
  `audio_Sandnessjøen` has files prefixed `Sandnessjoeen_`, and a handful of
  `anMtr_` WAV names carry no dialect at all.
- HEAD requests for Oslo, Elverum, Bergen, Malm and Sandnessjøen files returned
  200 under the basename-only URL mapping. `robots.txt` does not exist (the
  root returns a JSON 404), so no site-stated limit exists; we choose the rate.
- `adapters/kaikki_tts.py` already establishes the repo's HTTP conventions:
  `requests`, a fixed identifying `User-Agent`, timeouts.
- `requests` and `tqdm` are pinned in `requirements.txt`; `rich` is not.

## Goals / Non-Goals

**Goals:**
- Every downloadable recording on disk, with a manifest that records which
  word, dialect and URL each file came from.
- Interrupt anywhere (Ctrl-C, SIGTERM, power loss) and re-run to continue, never
  re-downloading finished files and never trusting a half-written one.
- A request rate no reasonable server operator would object to.
- A UI that makes a ~20-minute run legible.

**Non-Goals:**
- Any `/tts` behaviour, DB table, or adapter — that is `pygmalion-tts-provider`.
- Concurrency. 1,178 small files do not justify it, and it works against
  politeness.
- Converting, trimming or normalising audio. Bytes are stored as served.
- Fetching the 2 WAV entries.
- Re-fetching when the upstream file changes. Files are treated as immutable.

## Decisions

### D1: Two subcommands; the manifest is the resume state

```
 vowels.json ─┐
              ├─► extract ─► manifest.jsonl ─► download ─► audio/<Dialect>/*.mp3
 consonants ──┘   (offline,    (the TODO list     (network,    (+ manifest rows
                   pure)        and the result)    resumable)    updated in place)
```

`extract` is pure and offline so the inventory logic is unit-testable without
a network. `download` reads only the manifest, never the source JSON. There is
no separate checkpoint file: a row's `status` *is* the checkpoint.

**Alternative considered:** one command that extracts and downloads in a single
pass with a sidecar state file. Rejected: two sources of truth, and the
inventory could not be inspected or diffed before any network traffic.

### D2: Manifest row shape (JSONL, one row per file)

```json
{"word": "led", "dialect": "Oslo", "take": 0,
 "translation": ["fairway"],
 "url": "https://polymetis.hf.ntnu.no/static/WordObjectContent/Norwegian/Words_MP3/Oslo_Normal_4XTOXWDM2944G551.mp3",
 "path": "Oslo/Oslo_Normal_4XTOXWDM2944G551.mp3",
 "status": "ok", "bytes": 6552, "sha256": "…"}
```

- One row per **file**, keyed by `url` (the basename is unique, verified).
- `take` is the file's 0-based order of first appearance within
  `(word, dialect)`, so `led`'s two Oslo recordings are takes 0 and 1.
- `word` is stored exactly as in the source (phrases keep their spaces and
  hyphens). Case folding is the consumer's job, not the manifest's.
- `path` is relative to `providers/pygmalion/audio/`, so the manifest is
  relocatable and the DB importer need not know the absolute layout.
- `status ∈ pending | ok | missing | failed`. `bytes`/`sha256` exist only for
  `ok` rows.
- JSONL rather than one JSON document: line-oriented diffs in git, and a
  corrupted line cannot take the whole file with it.

**Alternative considered:** a `words: [...]` list per file (my first sketch).
Dropped once verification showed no file is shared between words.

### D3: Directory and dialect naming

Directory = ASCII slug of the dialect key (`Sandnessjøen` → `Sandnessjoeen`,
matching the server's own spelling) so paths are safe in git, Docker bind
mounts and every filesystem. The manifest's `dialect` field keeps the
original `Sandnessjøen`, since that is the human-meaningful value and the one
a TTS `voice` label would show.

### D4: Download algorithm, per row with `status ≠ ok`

```
 target exists with plausible size? ──yes──► hash it, mark ok (crash repair)
        │no
        ▼
 sleep jitter(0.5–1.0 s) ─► GET (stream, timeout 10s connect / 30s read)
        │
        ├─ 200 + audio/* + non-empty ─► write .part ─► fsync ─► rename ─► sha256 ─► row ok
        ├─ 404 / 410                  ─► row missing (permanent; no retry this run)
        └─ 429 / 5xx / network error  ─► wait max(Retry-After, 2^n s, cap 60) ─► retry
                                          (max 5 attempts, then row failed)
```

- The jitter applies only after a **real request**; skipping an existing file
  costs no delay, so a resume that is 90% done is near-instant.
- **Crash repair:** if the process died between `rename` and the manifest
  write, the file exists but its row is not `ok`. The next run hashes the file
  and marks it `ok` instead of re-downloading. A leftover `.part` is always
  deleted and re-fetched, never resumed — files are ~6 KB, so HTTP `Range`
  resumption would be complexity with no benefit.
- Content check: `Content-Type` must start with `audio/` (a captive page or a
  nginx HTML error served with 200 must not be saved as an mp3), and the body
  must be non-empty. If `Content-Length` is present it must match the bytes
  received.
- `missing` and `failed` rows are retried only with `--retry-failed`, so a
  broken URL does not make every re-run slow.

### D5: Interruption safety

- Manifest is rewritten **after every file** (tmp file + `os.replace`). At
  ~300 KB × 1,178 that is negligible next to the 0.5–1 s sleep, and it makes
  "continuable from any point" literally true rather than "from the last
  checkpoint".
- On `KeyboardInterrupt`/`SIGTERM`: close the in-flight response, delete its
  `.part`, flush the manifest, print a one-line resume hint, exit 130. A second
  Ctrl-C during that cleanup is harmless because every step is already atomic.
- `kill -9` and power loss are covered by the same properties plus the crash
  repair above.

### D6: UI with `rich`

```
 pygmalion audio · download                       polymetis.hf.ntnu.no
 ━━━━━━━━━━━━━━━╸━━━━━━━━━━━━━━━  730/1178  62%  1.4 file/s  ETA 5:09
 now   Bergen · «ledd»  Bergen_Normal_0VEPBXJ6Z5QNE27E.mp3
 ok 702   skipped 28   missing 0   failed 0   retries 3
 ── log ──────────────────────────────────────────────────────────
 12:04:11  WARN  429 on Oslo_Normal_…  waiting 4.0s (Retry-After 4)
 12:04:15  INFO  resumed after backoff
```

A `rich.live.Live` layout with a `Progress` bar, a counters line, and a
bounded log panel (last ~8 events). When `console.is_terminal` is false (piped
to a file, CI), the same events are emitted as plain timestamped lines with no
live redraw. A final `rich.table.Table` summarises per dialect: files, ok,
missing, failed, bytes. `extract` gets a smaller summary: files per dialect,
words, skipped entries with reasons.

**Alternative considered:** `tqdm` (already pinned). Rejected by the operator:
`rich` gives a multi-line live view and a summary table at no extra
complexity, for the price of one dev dependency.

### D7: `extract` re-runs are merge-preserving

`extract` rebuilds the inventory from the source JSON, then for each URL that
already has a manifest row keeps that row's `status`, `bytes` and `sha256`.
New URLs are added as `pending`; rows whose URL no longer appears in the
source are kept (never delete data silently) and reported. This makes
`extract` safe to re-run after the JSON changes without losing download
progress.

### D8: CLI surface — deliberately small

`extract`, `download`, plus on `download`: `--retry-failed`, `--dialect NAME`
(repeatable, to fetch a subset), `--limit N`, `--delay-min/--delay-max`.
`--limit` and `--dialect` exist mostly for cheap first live runs and tests.

### D9: Committing the audio

The mp3s and manifest are committed as-is (~8 MB). No `.gitignore` entry, no
zip, per the operator's decision. This is a reasonable size next to the
existing committed `providers/` data, and means a fresh clone needs no network
to build the TTS provider.

## Risks / Trade-offs

- **Unstated rate limit** → no published limit exists, so a ~1 req/s ceiling
  is chosen as plainly polite for ~1,178 tiny files, with backoff and
  `Retry-After` as the safety net. Delays are flags if it proves too slow.
- **Upstream disappears or moves** → rows become `missing`; the run completes
  and reports them. The committed mp3s are the lasting copy.
- **`rich` colours and redraw in odd terminals / logs** → mitigated by the
  non-TTY plain-line path.
- **WAV-only words** → `bolig` has only the 2 skipped entries and so gets no
  audio. Reported as a warning by `extract`; acceptable for 1 of 180 words.
- **Manifest rewritten per file** → ~1,178 × 300 KB of writes; trivial, and
  buys exact resumability. Revisit only if the corpus grows by orders of
  magnitude.
- **Immutable-file assumption** → a re-recorded file under the same basename
  would not be re-fetched. Basenames embed a random id, so a changed recording
  would get a new name.

## Open Questions

- None blocking. The first live run will show whether the server tolerates the
  default delay; adjust the default from that evidence.
