## 1. Setup

- [x] 1.1 Add `rich==13.9.4` to `requirements-dev.txt` (not `requirements.txt` — design D6, spec "fetched corpus is committed").
- [x] 1.2 Create `scripts/fetch_pygmalion_audio.py` with an `argparse` CLI exposing `extract` and `download` (design D1, D8) and `python -m scripts.fetch_pygmalion_audio` entry, matching the other `scripts/import_*.py`.

## 2. `extract`

- [x] 2.1 Implement a generic recursive walker that finds every dict with a `word` key and `audio_*` lists, at any nesting depth (do not hard-code the `soundgroups → dictionary → MP_wordpair` path).
- [x] 2.2 Map each Windows path to `(basename, url)` only when it matches `…\Words_MP3\<name>.mp3`; collect everything else as skipped-with-reason (design D4, the two `…\OriginalWords_Wav\…bolig….wav` entries).
- [x] 2.3 Derive `dialect` from the `audio_<Dialect>` key; derive the on-disk directory as an ASCII slug (`Sandnessjøen` → `Sandnessjoeen`) while keeping the original in the row (design D3).
- [x] 2.4 Dedupe by URL; assign `take` as order of first appearance within `(word, dialect)`; keep `word` verbatim (design D2).
- [x] 2.5 Write `providers/pygmalion/audio/manifest.jsonl` atomically (tmp + `os.replace`), rows in deterministic order (dialect, word, take) so git diffs are stable.
- [x] 2.6 Merge-preserving re-run: keep `status`/`bytes`/`sha256` for known URLs, add new ones as `pending`, retain and report rows no longer in the source (design D7).
- [x] 2.7 Print an `extract` summary: files per dialect, unique words, skipped entries with reasons.

## 3. `download`

- [x] 3.1 Implement manifest load/save helpers (JSONL, atomic rewrite after every completed row — design D5).
- [x] 3.2 Implement the fetch of one row with a `requests.Session`: stream, connect/read timeouts, identifying `User-Agent` in the style of `adapters/kaikki_tts.py`, write to `<path>.part`, `fsync`, `os.replace` to the final path.
- [x] 3.3 Validate the response: 200, `Content-Type` starts with `audio/`, non-empty, `Content-Length` matches when present; compute `sha256` and `bytes` (spec "Only real audio is saved").
- [x] 3.4 Pacing: sleep `uniform(delay_min, delay_max)` (default 0.5–1.0 s) after each real request only; never after a skip (spec "polite").
- [x] 3.5 Retry policy: on 429/5xx/network error wait `max(Retry-After, 2**n)` capped at 60 s, max 5 attempts, then `failed`; parse `Retry-After` both as seconds and as an HTTP date. 404/410 → `missing`, no retry this run.
- [x] 3.6 Crash repair: if the final file exists but the row is not `ok`, hash it and mark `ok`; always delete a leftover `.part` before fetching (design D4).
- [x] 3.7 Select rows: all non-`ok` by default; `missing`/`failed` only with `--retry-failed`; support repeatable `--dialect`, `--limit N`, `--delay-min`, `--delay-max` (design D8).
- [x] 3.8 Interruption: handle `KeyboardInterrupt` and `SIGTERM` — drop the `.part`, flush the manifest, print remaining count and the command to resume, exit 130 (design D5).

- [x] 3.9 Single-instance guard: take an exclusive non-blocking `flock` on the audio directory for the whole `extract`/`download` run; on contention print a message and exit 3. Use a per-process manifest temp name. (Added after a live failure: a second concurrent `download` crashed with `FileNotFoundError` in `os.replace` because both runs shared `manifest.jsonl.tmp`.)

## 4. Terminal UI

- [x] 4.1 Build the `rich` live view: progress bar with rate and ETA, current word · dialect · filename, counters (ok / skipped / missing / failed / retries), and a bounded log panel (design D6).
- [x] 4.2 Route all retry, backoff, skip and warning events through one logger so they appear in the log panel in a TTY and as plain timestamped lines when `console.is_terminal` is false.
- [x] 4.3 Print the final per-dialect summary table on finish **and** on interruption.

## 5. Tests

- [x] 5.1 `tests/test_pygmalion_fetch.py`: `extract` on a small fixture JSON — nested depth, dedupe-by-URL, `take` numbering, phrase words verbatim, empty dialect lists, `Sandnessjøen` directory slug.
- [x] 5.2 `extract` skips non-`Words_MP3` / non-`.mp3` paths and reports them; creates no row for them.
- [x] 5.3 Merge-preserving re-extract keeps an `ok` row's `sha256`, adds a new URL as `pending`, and keeps a row that vanished from the source.
- [x] 5.4 `download` with HTTP stubbed (monkeypatch `requests.Session.get` or a local `http.server`): success writes the file, `sha256`, `bytes`, and `status: ok`; no `.part` remains.
- [x] 5.5 Rejections: `text/html` with 200, short body vs `Content-Length`, empty body — none write a final file or mark `ok`.
- [x] 5.6 Retry: a stubbed 429 with `Retry-After: 2` waits at least that long (patch `time.sleep` to record); 503 ×5 ends `failed`; 404 ends `missing` and is not re-requested on a plain re-run but is with `--retry-failed`.
- [x] 5.7 Resume: pre-mark some rows `ok` with files present → zero requests for them and no sleep; a final file present with a non-`ok` row is repaired to `ok` without a request; a stale `.part` is removed.
- [x] 5.8 Interruption: raise `KeyboardInterrupt` from the stubbed fetch mid-run → manifest still valid JSONL, no final file for the in-flight row, exit code 130.
- [x] 5.9 Pacing: with `time.sleep` patched, consecutive real requests are separated by a recorded delay within [0.5, 1.0]; skipped rows record none.

## 6. Live run and commit of the corpus

- [x] 6.1 Run `python -m scripts.fetch_pygmalion_audio extract` and check the summary against the known figures: 180 unique words, 1,176 mp3 files, 2 skipped WAV entries, and zero rows for Tromsø.
- [x] 6.2 Smoke test: `download --limit 5 --dialect Oslo`, then re-run and confirm no requests for those 5; interrupt a second run with Ctrl-C and resume it.
- [x] 6.3 Full `download`. Review the final summary: expect ~1,176 `ok`, and investigate any `missing`/`failed` before accepting.
- [x] 6.4 Spot-check a handful of files per dialect (non-zero size, valid mp3, plausibly the right word) — and confirm the Oslo `led` recordings (`Oslo_Normal_4XTOXWDM2944G551.mp3`, `Oslo_Normal_WL34HFEVDYIWE1QE.mp3`) are present.
- [x] 6.5 Commit `providers/pygmalion/audio/` (mp3s + `manifest.jsonl`), the script, tests and `requirements-dev.txt`. Confirm no `.gitignore` rule excludes any of them and `git status` is clean afterwards.
