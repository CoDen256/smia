## ADDED Requirements

### Requirement: Recording inventory is extracted into a manifest
`scripts/fetch_pygmalion_audio.py extract` SHALL read `providers/pygmalion/vowels.json` and `providers/pygmalion/consonants.json`, visit every `MP_wordpair` record at any depth, and write `providers/pygmalion/audio/manifest.jsonl` with one JSON row per distinct audio file. Each row SHALL carry `word`, `dialect`, `take`, `translation`, `url`, `path` and `status`. The `dialect` SHALL be derived from the `audio_<Dialect>` key the path was listed under, never from the filename. The `url` SHALL be the fixed base `https://polymetis.hf.ntnu.no/static/WordObjectContent/Norwegian/Words_MP3/` followed by the path's basename. The `take` SHALL be the file's 0-based order of first appearance within its `(word, dialect)`. This command SHALL NOT perform any network request.

#### Scenario: The same word repeated across exercises yields one row per file
- **WHEN** the word `led` appears in several exercises listing the same Oslo file
- **THEN** the manifest contains exactly one row for that file, with `word: "led"` and `dialect: "Oslo"`

#### Scenario: Dialect comes from the key, not the filename
- **WHEN** a path is listed under `audio_Sandnessjøen` and its basename starts with `Sandnessjoeen_`
- **THEN** the row's `dialect` is `Sandnessjøen` and its `path` is under the `Sandnessjoeen/` directory

#### Scenario: Takes are numbered per word and dialect
- **WHEN** `led` has two distinct Oslo files and one Bergen file
- **THEN** the Oslo rows have `take` 0 and 1 and the Bergen row has `take` 0

#### Scenario: Phrases are kept verbatim
- **WHEN** a record's `word` is `la du` or `i-en`
- **THEN** the row's `word` is exactly that string, with its space or hyphen intact

#### Scenario: Empty dialect lists contribute nothing
- **WHEN** a record's `audio_Tromsø` list is empty
- **THEN** no row is created for it, and no warning is raised

#### Scenario: Entries the server mapping cannot reach are skipped and reported
- **WHEN** a path is not of the form `…\Words_MP3\<name>.mp3` (e.g. the `…\OriginalWords_Wav\…bolig….wav` entries)
- **THEN** no manifest row is created for it, and the command reports each skipped path with its reason

#### Scenario: Re-extraction preserves download progress
- **WHEN** `extract` is run again and a URL already has a manifest row with `status: "ok"`, `bytes` and `sha256`
- **THEN** that row keeps its `status`, `bytes` and `sha256`, new URLs are added as `pending`, and no row is deleted

### Requirement: Downloads are resumable from any interruption point
`scripts/fetch_pygmalion_audio.py download` SHALL fetch every manifest row whose `status` is not `ok` into `providers/pygmalion/audio/<path>`. A file SHALL be written to a `.part` file and atomically renamed only once complete and verified, and the manifest SHALL be atomically rewritten after every file. The manifest's `status` SHALL be the sole resume state; no separate checkpoint file SHALL exist.

#### Scenario: Interrupted run continues where it stopped
- **WHEN** a download run is interrupted by Ctrl-C after N files and is run again
- **THEN** the second run fetches only the rows not yet `ok` and performs no request for the N finished files

#### Scenario: Interruption leaves no partial file behind
- **WHEN** the process is interrupted while a file is being received
- **THEN** no file exists at that row's final `path`, the `.part` file is removed, and the row is not `ok`

#### Scenario: Crash between rename and manifest write is repaired
- **WHEN** a file exists at a row's final `path` but the row's `status` is not `ok`
- **THEN** the next run computes the file's `sha256` and size, marks the row `ok`, and does not download it again

#### Scenario: A hard kill is recoverable
- **WHEN** the process is killed without cleanup mid-download
- **THEN** the next run deletes any leftover `.part`, re-fetches that row, and the manifest is still valid JSONL

#### Scenario: Interrupt exits with a resume hint
- **WHEN** the operator presses Ctrl-C during a download
- **THEN** the command flushes the manifest, prints how many rows remain, and exits with status 130

### Requirement: Downloads are polite to the remote server
The downloader SHALL use a single connection and issue requests sequentially, sleeping a random 0.5–1.0 s between consecutive network requests, and SHALL send an identifying `User-Agent`. It SHALL honour a `Retry-After` header and SHALL back off exponentially on HTTP 429, 5xx and network errors, giving up on a row after 5 attempts. No delay SHALL be applied for rows skipped without a request.

#### Scenario: Requests are spaced out
- **WHEN** two consecutive files are downloaded
- **THEN** at least 0.5 s separates the start of their requests

#### Scenario: Retry-After is honoured
- **WHEN** the server answers 429 with `Retry-After: 7`
- **THEN** the next attempt for that row begins no sooner than 7 s later

#### Scenario: Transient failure is retried with backoff
- **WHEN** a request fails with a 503 or a connection error
- **THEN** it is retried after an exponentially growing wait, and the row is marked `failed` only after 5 failed attempts

#### Scenario: Skipped files cost no delay
- **WHEN** a run encounters rows already `ok` with their file present
- **THEN** it skips them without sleeping or contacting the server

### Requirement: Only real audio is saved
A response SHALL be saved only if its status is 200, its `Content-Type` starts with `audio/`, and its body is non-empty and, when `Content-Length` is given, of exactly that length. A 404 or 410 SHALL mark the row `missing` and SHALL NOT be retried within the same run. Rows marked `missing` or `failed` SHALL be retried only when `--retry-failed` is passed.

#### Scenario: HTML served with status 200 is rejected
- **WHEN** the server returns 200 with `Content-Type: text/html`
- **THEN** nothing is written to the final path and the row is not marked `ok`

#### Scenario: Truncated body is rejected
- **WHEN** the received byte count differs from `Content-Length`
- **THEN** the `.part` file is discarded and the attempt counts as a failure

#### Scenario: Missing file is recorded, not retried
- **WHEN** a URL answers 404
- **THEN** its row is marked `missing`, the run continues with the next row, and a plain re-run does not request it again

#### Scenario: Successful row records integrity data
- **WHEN** a file is downloaded successfully
- **THEN** its row has `status: "ok"`, its byte size, and the `sha256` of the saved bytes

### Requirement: Only one run uses the audio directory at a time
`extract` and `download` SHALL each take an exclusive, non-blocking advisory lock on `providers/pygmalion/audio/` for their whole run, because both rewrite the single manifest. A run that cannot take the lock SHALL print a message saying another run is in progress, change nothing, and exit with status 3 rather than raising. The lock SHALL be released when the process exits for any reason, and SHALL NOT leave a lock file behind. The manifest's temporary file SHALL have a name unique to the writing process.

#### Scenario: A second download is refused
- **WHEN** a `download` is running and a second `download` or `extract` is started on the same audio directory
- **THEN** the second run prints that another run is in progress, exits with status 3, and does not modify the manifest

#### Scenario: A crash does not wedge the directory
- **WHEN** a run is killed without cleanup
- **THEN** the next run acquires the lock normally

#### Scenario: Concurrent manifest writes cannot collide on a temp file
- **WHEN** two processes write the manifest at the same moment
- **THEN** each writes its own uniquely named temporary file, so neither's rename can fail because the other consumed it

### Requirement: Progress is observable in the terminal
The command SHALL present a live `rich` display containing a progress bar with rate and ETA, the word and dialect currently being fetched, counters for ok, skipped, missing and failed rows plus retries, and a bounded scrolling log of warnings and retries; it SHALL end with a per-dialect summary table. When standard output is not a terminal, it SHALL instead emit plain timestamped lines and no live redraw.

#### Scenario: Interactive run shows live progress
- **WHEN** `download` is run in a terminal
- **THEN** a live-updating view shows progress, the current word and dialect, and the counters

#### Scenario: Retries are visible
- **WHEN** a request is retried
- **THEN** a log line states the status or error, the wait, and the file concerned

#### Scenario: Piped output is plain
- **WHEN** `download` is run with output redirected to a file
- **THEN** the output contains plain timestamped lines and no cursor-control sequences

#### Scenario: Final summary
- **WHEN** a run finishes or is interrupted
- **THEN** a table shows, per dialect, the number of files ok, missing and failed and the bytes stored

### Requirement: The fetched corpus is committed
The downloaded files under `providers/pygmalion/audio/` and `manifest.jsonl` SHALL be committed to the repository, and SHALL NOT be gitignored. `rich` SHALL be declared in `requirements-dev.txt` and SHALL NOT be added to `requirements.txt`.

#### Scenario: Fresh clone needs no network
- **WHEN** the repository is freshly cloned
- **THEN** every manifest row with `status: "ok"` has its file present at `providers/pygmalion/audio/<path>`

#### Scenario: Runtime image does not require rich
- **WHEN** the runtime dependencies are installed from `requirements.txt`
- **THEN** `rich` is not among them
