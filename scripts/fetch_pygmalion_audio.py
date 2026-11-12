"""
scripts/fetch_pygmalion_audio.py — fetch the NTNU Pygmalion / LearnNoW
pronunciation recordings referenced by `providers/pygmalion/{vowels,
consonants}.json` into `providers/pygmalion/audio/`, with a manifest that
records which word / dialect / URL every file came from (the data half of the
`pygmalion` /tts provider).

Two steps, deliberately separate:

  extract   offline, pure. Walks both JSON files, maps every Windows path
            (`C:\\CalstFiles\\…\\Words_MP3\\<name>.mp3`) to its remote URL and
            writes `audio/manifest.jsonl`. Re-running keeps download progress.
  download  network. Fetches every manifest row not yet done, politely
            (one connection, 0.5–1 s jitter, Retry-After, backoff), and can be
            interrupted and resumed at any point: the manifest *is* the
            resume state, files land via `.part` + atomic rename.

Run:
  python -m scripts.fetch_pygmalion_audio extract
  python -m scripts.fetch_pygmalion_audio download [--retry-failed]
        [--dialect Oslo ...] [--limit N] [--delay-min 0.5 --delay-max 1.0]

Dev-time script: needs `rich` (requirements-dev.txt), not in the runtime image.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import random
import re
import signal
import sys
import time
import unicodedata
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

try:
    import fcntl
except ImportError:  # non-POSIX: no single-instance lock, everything else works
    fcntl = None

import requests
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    ProgressColumn,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeRemainingColumn,
)
from rich.table import Table
from rich.text import Text

BASE_URL = "https://polymetis.hf.ntnu.no/static/WordObjectContent/Norwegian/Words_MP3/"
# Same convention as adapters/kaikki_tts.py: identify the client.
USER_AGENT = "smia/0.1 (linguistics service; Tun ecosystem; pygmalion audio fetch)"

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_AUDIO_DIR = _REPO_ROOT / "providers" / "pygmalion" / "audio"
DEFAULT_SOURCES = [
    _REPO_ROOT / "providers" / "pygmalion" / "vowels.json",
    _REPO_ROOT / "providers" / "pygmalion" / "consonants.json",
]
MANIFEST_NAME = "manifest.jsonl"

MAX_ATTEMPTS = 5
BACKOFF_CAP_S = 60.0
RETRY_AFTER_CAP_S = 300.0  # never let a hostile header park us for hours
TIMEOUT = (10, 30)  # connect, read
CHUNK = 16 * 1024

# Windows paths in the source JSON, e.g.
#   C:\CalstFiles\WordObjectContent\Norwegian\Words_MP3\Oslo_Normal_X.mp3
# Only this shape maps onto BASE_URL; the two `…\OriginalWords_Wav\…wav`
# (bolig) entries do not and are skipped.
_MP3_PATH = re.compile(r"^.*[\\/]Words_MP3[\\/]([^\\/]+\.mp3)$", re.IGNORECASE)

_FIELD_ORDER = ("word", "dialect", "take", "translation", "url", "path", "status", "bytes", "sha256")
DONE, PENDING, MISSING, FAILED = "ok", "pending", "missing", "failed"


# ─────────────────────────── extract (pure) ───────────────────────────

def dialect_slug(dialect: str) -> str:
    """ASCII directory name for a dialect: `Sandnessjøen` → `Sandnessjoeen`
    (the server's own spelling), so paths are safe in git, Docker mounts and
    every filesystem. The manifest keeps the original in `dialect`."""
    s = dialect.replace("ø", "oe").replace("Ø", "Oe").replace("å", "aa").replace("Å", "Aa")
    s = s.replace("æ", "ae").replace("Æ", "Ae")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^A-Za-z0-9_-]", "", s)


def iter_wordpairs(obj):
    """Yield every dict that looks like a word record (a `word` plus at least
    one `audio_*` key), at any nesting depth — deliberately not hard-coded to
    soundgroups → dictionary → MP_wordpair."""
    if isinstance(obj, dict):
        if "word" in obj and any(k.startswith("audio_") for k in obj):
            yield obj
        for v in obj.values():
            yield from iter_wordpairs(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from iter_wordpairs(v)


def build_inventory(documents) -> tuple[list[dict], list[dict]]:
    """Returns `(rows, skipped)` from already-parsed JSON documents.

    One row per distinct URL. `take` is the file's 0-based order of first
    appearance within (word, dialect). Rows are sorted (dialect, word, take)
    so manifest diffs stay stable."""
    rows: dict[str, dict] = {}
    skipped: list[dict] = []
    takes: dict[tuple[str, str], int] = {}

    for doc in documents:
        for rec in iter_wordpairs(doc):
            word = rec["word"]
            translation = rec.get("Translation") or []
            for key, paths in rec.items():
                if not key.startswith("audio_") or not paths:
                    continue
                dialect = key[len("audio_"):]
                for p in paths:
                    m = _MP3_PATH.match(p)
                    if not m:
                        skipped.append(
                            {"word": word, "dialect": dialect, "path": p, "reason": "not a Words_MP3/*.mp3 path"}
                        )
                        continue
                    basename = m.group(1)
                    url = BASE_URL + basename
                    existing = rows.get(url)
                    if existing is not None:
                        if (existing["word"], existing["dialect"]) != (word, dialect):
                            skipped.append(
                                {
                                    "word": word,
                                    "dialect": dialect,
                                    "path": p,
                                    "reason": f"url already used by {existing['word']!r}/{existing['dialect']}",
                                }
                            )
                        continue
                    take = takes.get((word, dialect), 0)
                    takes[(word, dialect)] = take + 1
                    rows[url] = {
                        "word": word,
                        "dialect": dialect,
                        "take": take,
                        "translation": list(translation),
                        "url": url,
                        "path": f"{dialect_slug(dialect)}/{basename}",
                        "status": PENDING,
                    }
    ordered = sorted(rows.values(), key=lambda r: (r["dialect"], r["word"], r["take"]))
    return ordered, skipped


def merge_manifest(new_rows: list[dict], old_rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Keep download progress across re-extraction (design D7): a URL already
    in the manifest keeps its status/bytes/sha256. Rows that vanished from the
    source are retained (never delete data silently) and returned as `dropped`
    so the caller can report them."""
    old_by_url = {r["url"]: r for r in old_rows}
    merged = []
    for row in new_rows:
        old = old_by_url.get(row["url"])
        if old is not None:
            row = dict(row)
            row["status"] = old.get("status", PENDING)
            for k in ("bytes", "sha256"):
                if k in old:
                    row[k] = old[k]
        merged.append(row)
    new_urls = {r["url"] for r in new_rows}
    dropped = [r for r in old_rows if r["url"] not in new_urls]
    return merged + dropped, dropped


# ─────────────────────────── manifest I/O ───────────────────────────

def load_manifest(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{path}:{n}: invalid JSON ({exc}); fix or delete the line and re-run") from exc
    return rows


def save_manifest(path: Path, rows: list[dict]) -> None:
    """Atomic: write a temp file, fsync, `os.replace`. The manifest is the
    resume state, so a crash mid-write must never leave it half-written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # Per-process temp name: a fixed ".tmp" let two concurrent runs steal each
    # other's file (FileNotFoundError in os.replace). `run_lock` makes a second
    # run impossible; this keeps the write safe even if the lock is bypassed.
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for row in rows:
            ordered = {k: row[k] for k in _FIELD_ORDER if k in row}
            ordered.update({k: v for k, v in row.items() if k not in ordered})
            f.write(json.dumps(ordered, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


class AlreadyRunning(Exception):
    pass


@contextlib.contextmanager
def run_lock(audio_dir: Path):
    """Only one extract/download may use an audio directory at a time: both
    rewrite the one manifest, so two runs would silently overwrite each
    other's progress. An advisory `flock` on the directory itself — no lock
    file to leave behind or gitignore, and the OS drops it if the process dies
    (so a crash can never leave the directory stuck)."""
    audio_dir.mkdir(parents=True, exist_ok=True)
    if fcntl is None:
        yield
        return
    fd = os.open(audio_dir, os.O_RDONLY)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise AlreadyRunning(str(audio_dir)) from exc
        yield
    finally:
        os.close(fd)  # closing the descriptor releases the lock


# ─────────────────────────── terminal UI ───────────────────────────

class _RateColumn(ProgressColumn):
    def render(self, task) -> Text:
        return Text(f"{task.speed:.1f} file/s" if task.speed else "-- file/s", style="cyan")


class Ui:
    """`rich` live view when stdout is a terminal; plain timestamped lines
    otherwise (piped to a file, CI) — same events either way."""

    LOG_LINES = 8
    _LEVEL_STYLE = {"INFO": "", "WARN": "yellow", "ERROR": "bold red"}

    def __init__(self, console: Console | None = None):
        self.console = console or Console()
        self.live_mode = self.console.is_terminal
        self.counts = {DONE: 0, "skipped": 0, MISSING: 0, FAILED: 0, "retries": 0}
        self._log: deque[Text] = deque(maxlen=self.LOG_LINES)
        self._now = Text("")
        self._progress: Progress | None = None
        self._task = None
        self._live: Live | None = None
        self._total = 0

    @contextlib.contextmanager
    def session(self, title: str, total: int, skipped: int = 0):
        self.counts["skipped"] = skipped
        self._total = total
        if self.live_mode:
            self._progress = Progress(
                SpinnerColumn(),
                TextColumn("[bold]{task.description}"),
                BarColumn(),
                MofNCompleteColumn(),
                TaskProgressColumn(),
                _RateColumn(),
                TextColumn("ETA"),
                TimeRemainingColumn(),
                console=self.console,
            )
            self._task = self._progress.add_task(title, total=total)
            self._live = Live(self._render(), console=self.console, refresh_per_second=8, transient=False)
            self._live.start()
        try:
            yield self
        finally:
            if self._live is not None:
                self._live.update(self._render())
                self._live.stop()
                self._live = None

    def _render(self):
        c = self.counts
        counters = Text.assemble(
            ("ok ", "green"), (f"{c[DONE]}   ", "bold green"),
            ("skipped ", "dim"), (f"{c['skipped']}   ", "dim"),
            ("missing ", "yellow"), (f"{c[MISSING]}   ", "yellow"),
            ("failed ", "red"), (f"{c[FAILED]}   ", "bold red"),
            ("retries ", "cyan"), (f"{c['retries']}", "cyan"),
        )
        log = Text("\n").join(self._log) if self._log else Text("(quiet — no retries or warnings yet)", style="dim")
        return Group(
            self._progress,
            Text.assemble(("now  ", "dim"), self._now),
            counters,
            Panel(log, title="log", title_align="left", height=self.LOG_LINES + 2),
        )

    def _refresh(self) -> None:
        if self._live is not None:
            self._live.update(self._render())

    def now(self, row: dict) -> None:
        self._now = Text(f"{row['dialect']} · «{row['word']}»  {Path(row['path']).name}")
        self._refresh()

    def event(self, level: str, message: str, *, plain_only: bool = False) -> None:
        """`plain_only` events (one line per downloaded file) are noise in the
        live view, whose counters already say it — but are the whole story in
        a log file."""
        stamp = datetime.now().strftime("%H:%M:%S")
        if self.live_mode:
            if not plain_only:
                self._log.append(Text(f"{stamp}  {level:<5} {message}", style=self._LEVEL_STYLE.get(level, "")))
                self._refresh()
        else:
            self.console.print(f"{stamp} {level:<5} {message}", markup=False, highlight=False, soft_wrap=True)

    def advance(self, status: str) -> None:
        self.counts[status] = self.counts.get(status, 0) + 1
        if self._progress is not None:
            self._progress.advance(self._task)
        self._refresh()

    def retry(self) -> None:
        self.counts["retries"] += 1
        self._refresh()


def _human_bytes(n: int) -> str:
    return f"{n / 1024:.1f} KiB" if n < 1024 * 1024 else f"{n / 1024 / 1024:.2f} MiB"


def print_download_summary(console: Console, rows: list[dict]) -> None:
    table = Table(title="pygmalion audio — manifest status", title_justify="left")
    table.add_column("dialect")
    for col in ("files", "ok", "pending", "missing", "failed"):
        table.add_column(col, justify="right")
    table.add_column("stored", justify="right")
    totals = dict.fromkeys(("files", DONE, PENDING, MISSING, FAILED, "bytes"), 0)
    for dialect in sorted({r["dialect"] for r in rows}):
        sub = [r for r in rows if r["dialect"] == dialect]
        cells = {
            "files": len(sub),
            **{s: sum(r["status"] == s for r in sub) for s in (DONE, PENDING, MISSING, FAILED)},
            "bytes": sum(r.get("bytes", 0) for r in sub if r["status"] == DONE),
        }
        for k, v in cells.items():
            totals[k] += v
        table.add_row(
            dialect, str(cells["files"]), str(cells[DONE]), str(cells[PENDING]),
            str(cells[MISSING]), str(cells[FAILED]), _human_bytes(cells["bytes"]),
        )
    table.add_section()
    table.add_row(
        "total", str(totals["files"]), str(totals[DONE]), str(totals[PENDING]),
        str(totals[MISSING]), str(totals[FAILED]), _human_bytes(totals["bytes"]), style="bold",
    )
    console.print(table)


# ─────────────────────────── download ───────────────────────────

class _Retryable(Exception):
    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


@dataclass
class Outcome:
    status: str
    bytes: int = 0
    sha256: str = ""
    error: str = ""


@dataclass
class RunResult:
    ok: int = 0
    skipped: int = 0
    repaired: int = 0
    missing: int = 0
    failed: int = 0
    interrupted: bool = False
    remaining: int = 0
    held: list = field(default_factory=list)


def parse_retry_after(value: str | None) -> float | None:
    """`Retry-After` is either delta-seconds or an HTTP date."""
    if not value:
        return None
    value = value.strip()
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())


def _sha256_file(path: Path) -> tuple[str, int]:
    h, n = hashlib.sha256(), 0
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            h.update(chunk)
            n += len(chunk)
    return h.hexdigest(), n


class Downloader:
    def __init__(
        self,
        rows: list[dict],
        manifest_path: Path,
        audio_dir: Path,
        *,
        session,
        ui: Ui,
        sleep=time.sleep,
        rng: random.Random | None = None,
        delay_min: float = 0.5,
        delay_max: float = 1.0,
    ):
        self.rows = rows
        self.manifest_path = manifest_path
        self.audio_dir = audio_dir
        self.session = session
        self.ui = ui
        self.sleep = sleep
        self.rng = rng or random.Random()
        self.delay_min, self.delay_max = delay_min, delay_max
        self._made_request = False

    # -- selection -----------------------------------------------------
    def _final(self, row: dict) -> Path:
        return self.audio_dir / row["path"]

    def _is_done(self, row: dict) -> bool:
        """`ok` only counts when the file is really there at the recorded size
        — a deleted or altered file is simply fetched again."""
        if row.get("status") != DONE:
            return False
        p = self._final(row)
        return p.is_file() and p.stat().st_size == row.get("bytes")

    def plan(self, *, retry_failed=False, dialects=(), limit=None) -> tuple[list[dict], int, list[dict]]:
        """Returns `(todo, already_done, held)`. `held` are missing/failed rows
        left alone because `--retry-failed` was not given."""
        wanted = {d.casefold() for d in dialects}
        todo, done, held = [], 0, []
        for row in self.rows:
            if wanted and row["dialect"].casefold() not in wanted:
                continue
            if self._is_done(row):
                done += 1
            elif row.get("status") in (MISSING, FAILED) and not retry_failed:
                held.append(row)
            else:
                todo.append(row)
        if limit is not None:
            todo = todo[:limit]
        return todo, done, held

    # -- main loop -----------------------------------------------------
    def run(self, *, retry_failed=False, dialects=(), limit=None) -> RunResult:
        todo, done, held = self.plan(retry_failed=retry_failed, dialects=dialects, limit=limit)
        result = RunResult(skipped=done, held=held)
        if held:
            self.ui.event("INFO", f"{len(held)} missing/failed rows left alone (use --retry-failed to retry them)")

        with self.ui.session("download", len(todo), skipped=done):
            index = -1
            try:
                for index, row in enumerate(todo):
                    self.ui.now(row)
                    self._process(row, result, index + 1, len(todo))
                    save_manifest(self.manifest_path, self.rows)
            except KeyboardInterrupt:
                result.interrupted = True
                result.remaining = len(todo) - index
                self.ui.event("WARN", f"interrupted — {result.remaining} row(s) remain; manifest saved")
            finally:
                save_manifest(self.manifest_path, self.rows)
        return result

    def _process(self, row: dict, result: RunResult, n: int, total: int) -> None:
        final = self._final(row)
        part = final.with_name(final.name + ".part")
        part.unlink(missing_ok=True)  # a leftover .part is never resumed: files are ~6 KB

        label = f"[{n}/{total}] {row['dialect']} «{row['word']}» {final.name}"
        if final.is_file():
            # Crash between rename and the manifest write: the file is whole
            # (atomic rename) but the row never became ok — verify and adopt.
            sha, size = _sha256_file(final)
            row.update(status=DONE, bytes=size, sha256=sha)
            result.repaired += 1
            result.ok += 1
            self.ui.event("INFO", f"{label} already on disk — marked ok (crash repair)")
            self.ui.advance(DONE)
            return

        outcome = self._fetch(row, final, part)
        row["status"] = outcome.status
        if outcome.status == DONE:
            row.update(bytes=outcome.bytes, sha256=outcome.sha256)
            result.ok += 1
            self.ui.event("INFO", f"{label} ok {outcome.bytes} B", plain_only=True)
        else:
            row.pop("bytes", None)
            row.pop("sha256", None)
            if outcome.status == MISSING:
                result.missing += 1
            else:
                result.failed += 1
            self.ui.event("ERROR" if outcome.status == FAILED else "WARN", f"{label} {outcome.status}: {outcome.error}")
        self.ui.advance(outcome.status)

    # -- one file ------------------------------------------------------
    def _fetch(self, row: dict, final: Path, part: Path) -> Outcome:
        if self._made_request:
            self.sleep(self.rng.uniform(self.delay_min, self.delay_max))
        self._made_request = True

        name = final.name
        last_error = ""
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                return self._attempt(row, final, part)
            except _Retryable as exc:
                last_error, retry_after = str(exc), exc.retry_after
            if attempt == MAX_ATTEMPTS:
                break
            wait = max(min(retry_after or 0.0, RETRY_AFTER_CAP_S), min(2.0**attempt, BACKOFF_CAP_S))
            suffix = f" (Retry-After {retry_after:g}s)" if retry_after else ""
            self.ui.event("WARN", f"{last_error} on {name}{suffix} — retry {attempt}/{MAX_ATTEMPTS - 1} in {wait:.1f}s")
            self.ui.retry()
            self.sleep(wait)
        return Outcome(FAILED, error=f"gave up after {MAX_ATTEMPTS} attempts: {last_error}")

    def _attempt(self, row: dict, final: Path, part: Path) -> Outcome:
        try:
            resp = self.session.get(row["url"], stream=True, timeout=TIMEOUT, headers={"User-Agent": USER_AGENT})
        except requests.RequestException as exc:
            raise _Retryable(f"{type(exc).__name__}") from exc

        with contextlib.closing(resp):
            code = resp.status_code
            if code in (404, 410):
                return Outcome(MISSING, error=f"HTTP {code}")
            if code == 429 or code >= 500:
                raise _Retryable(f"HTTP {code}", parse_retry_after(resp.headers.get("Retry-After")))
            if code != 200:
                return Outcome(FAILED, error=f"HTTP {code}")
            return self._receive(resp, final, part)

    def _receive(self, resp, final: Path, part: Path) -> Outcome:
        ctype = resp.headers.get("Content-Type", "")
        if not ctype.lower().startswith("audio/"):
            # e.g. an HTML error page served with 200 must never become an .mp3
            return Outcome(FAILED, error=f"unexpected Content-Type {ctype!r}")

        final.parent.mkdir(parents=True, exist_ok=True)
        h, size = hashlib.sha256(), 0
        try:
            try:
                with part.open("wb") as f:
                    for chunk in resp.iter_content(CHUNK):
                        f.write(chunk)
                        h.update(chunk)
                        size += len(chunk)
                    f.flush()
                    os.fsync(f.fileno())
            except requests.RequestException as exc:
                raise _Retryable(f"{type(exc).__name__} mid-body") from exc

            if size == 0:
                return Outcome(FAILED, error="empty body")
            declared = resp.headers.get("Content-Length")
            if declared is not None and declared.isdigit() and int(declared) != size:
                raise _Retryable(f"truncated body ({size} of {declared} B)")
            os.replace(part, final)
            return Outcome(DONE, bytes=size, sha256=h.hexdigest())
        finally:
            part.unlink(missing_ok=True)  # no-op after a successful rename


# ─────────────────────────── commands ───────────────────────────

def cmd_extract(args, console: Console) -> int:
    documents = []
    for src in args.source:
        try:
            with open(src, encoding="utf-8") as f:
                documents.append(json.load(f))
        except FileNotFoundError:
            console.print(f"[red]source not found:[/red] {src}")
            return 2

    rows, skipped = build_inventory(documents)
    manifest = args.audio_dir / MANIFEST_NAME
    merged, dropped = merge_manifest(rows, load_manifest(manifest))
    save_manifest(manifest, merged)

    table = Table(title="pygmalion audio — extract", title_justify="left")
    table.add_column("dialect")
    table.add_column("files", justify="right")
    table.add_column("words", justify="right")
    for dialect in sorted({r["dialect"] for r in rows}):
        sub = [r for r in rows if r["dialect"] == dialect]
        table.add_row(dialect, str(len(sub)), str(len({r["word"] for r in sub})))
    table.add_section()
    table.add_row("total", str(len(rows)), str(len({r["word"] for r in rows})), style="bold")
    console.print(table)

    for s in skipped:
        console.print(f"[yellow]skipped[/yellow] «{s['word']}» ({s['dialect']}): {s['reason']} — {s['path']}", highlight=False)
    if dropped:
        console.print(f"[yellow]{len(dropped)} manifest row(s) no longer in the source were kept[/yellow]")
    console.print(f"wrote {manifest} ({len(merged)} rows; {sum(r['status'] == DONE for r in merged)} already ok)")
    return 0


def cmd_download(args, console: Console, *, session=None, sleep=time.sleep) -> int:
    manifest = args.audio_dir / MANIFEST_NAME
    rows = load_manifest(manifest)
    if not rows:
        console.print(f"[red]no manifest at[/red] {manifest} — run `extract` first")
        return 2

    ui = Ui(console)
    own_session = session is None
    session = session or requests.Session()

    def _term(signum, frame):  # SIGTERM → the same clean path as Ctrl-C
        raise KeyboardInterrupt

    previous = signal.signal(signal.SIGTERM, _term)
    try:
        dl = Downloader(
            rows, manifest, args.audio_dir, session=session, ui=ui, sleep=sleep,
            delay_min=args.delay_min, delay_max=args.delay_max,
        )
        result = dl.run(retry_failed=args.retry_failed, dialects=args.dialect or (), limit=args.limit)
    finally:
        signal.signal(signal.SIGTERM, previous)
        if own_session:
            session.close()

    print_download_summary(console, rows)
    if result.interrupted:
        console.print(
            f"interrupted — {result.remaining} row(s) remain. Resume: python -m scripts.fetch_pygmalion_audio download",
            highlight=False,
        )
        return 130
    return 1 if (result.failed or result.missing) else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fetch_pygmalion_audio", description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="command", required=True)

    def common(sp):
        sp.add_argument("--audio-dir", type=Path, default=DEFAULT_AUDIO_DIR, help="audio + manifest directory")

    ex = sub.add_parser("extract", help="build/refresh manifest.jsonl from the source JSON (offline)")
    common(ex)
    ex.add_argument("--source", type=Path, action="append", help="source JSON (repeatable; default vowels+consonants)")

    dl = sub.add_parser("download", help="fetch every manifest row not yet done (resumable)")
    common(dl)
    dl.add_argument("--retry-failed", action="store_true", help="also retry rows marked missing/failed")
    dl.add_argument("--dialect", action="append", help="only this dialect (repeatable), e.g. Oslo")
    dl.add_argument("--limit", type=int, help="process at most N rows this run")
    dl.add_argument("--delay-min", type=float, default=0.5, help="min seconds between requests (default 0.5)")
    dl.add_argument("--delay-max", type=float, default=1.0, help="max seconds between requests (default 1.0)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    console = Console()
    if args.command == "download" and (args.delay_min < 0 or args.delay_max < args.delay_min):
        console.print("[red]--delay-max must be >= --delay-min >= 0[/red]")
        return 2
    try:
        with run_lock(args.audio_dir):
            if args.command == "extract":
                args.source = args.source or DEFAULT_SOURCES
                return cmd_extract(args, console)
            return cmd_download(args, console)
    except AlreadyRunning:
        console.print(
            f"[red]another fetch_pygmalion_audio run is already using[/red] {args.audio_dir}\n"
            "Two runs would overwrite each other's manifest. Wait for it to finish, "
            "or stop it (Ctrl-C is safe) and re-run."
        )
        return 3


if __name__ == "__main__":
    sys.exit(main())
