"""
tests/test_pygmalion_fetch.py — scripts/fetch_pygmalion_audio.py: the
offline `extract` inventory and the resumable, polite `download`.

HTTP is a fake session and `sleep` is injected, so nothing here touches the
network or actually waits. These tests need no database: the two autouse
fixtures from conftest.py that wipe DB tables are overridden with no-ops.
"""

from __future__ import annotations

import hashlib
import io
import json
import random

import pytest
import requests
from rich.console import Console

from scripts import fetch_pygmalion_audio as fpa


@pytest.fixture(autouse=True)
def clean_db():  # shadows conftest: this module is DB-free
    yield


@pytest.fixture(autouse=True)
def fresh_registry():  # shadows conftest: this module is DB-free
    yield


# ─────────────────────────── extract ───────────────────────────

def _win(name: str) -> str:
    return "C:\\CalstFiles\\WordObjectContent\\Norwegian\\Words_MP3\\" + name


def _rec(word, **audio):
    base = {f"audio_{d}": [] for d in ("Oslo", "Trondheim", "Stavanger", "Malm", "Bergen", "Sandnessjøen", "Elverum", "Tromsø")}
    base.update({f"audio_{d}": [_win(n) for n in names] for d, names in audio.items()})
    return {"word": word, "Translation": ["x"], **base}


def _doc(*recs):
    # arbitrary extra nesting: the walker must not depend on the exact path
    return {"soundgroups": [{"sound": "e", "dictionary": {"eː": [{"MP_wordpair": list(recs)}]}}]}


def test_extract_dedupes_repeats_and_numbers_takes():
    doc = _doc(
        _rec("led", Oslo=["Oslo_Normal_A.mp3", "Oslo_Normal_B.mp3"], Bergen=["Bergen_Normal_C.mp3"]),
        _rec("led", Oslo=["Oslo_Normal_A.mp3", "Oslo_Normal_B.mp3"]),  # same word, another exercise
    )
    rows, skipped = fpa.build_inventory([doc])
    assert skipped == []
    assert [(r["dialect"], r["take"], r["path"]) for r in rows] == [
        ("Bergen", 0, "Bergen/Bergen_Normal_C.mp3"),
        ("Oslo", 0, "Oslo/Oslo_Normal_A.mp3"),
        ("Oslo", 1, "Oslo/Oslo_Normal_B.mp3"),
    ]
    assert rows[1]["url"] == fpa.BASE_URL + "Oslo_Normal_A.mp3"
    assert all(r["status"] == "pending" and r["word"] == "led" for r in rows)


def test_extract_dialect_from_key_not_filename_and_ascii_dir():
    rows, _ = fpa.build_inventory([_doc(_rec("Oda", **{"Sandnessjøen": ["Sandnessjoeen_Normal_Z.mp3"]}))])
    assert rows[0]["dialect"] == "Sandnessjøen"
    assert rows[0]["path"] == "Sandnessjoeen/Sandnessjoeen_Normal_Z.mp3"


def test_extract_keeps_phrases_verbatim_and_ignores_empty_dialects():
    doc = _doc(_rec("la du", Oslo=["Oslo_Normal_A.mp3"]), _rec("i-en", Oslo=["Oslo_Normal_B.mp3"]))
    rows, skipped = fpa.build_inventory([doc])
    assert {r["word"] for r in rows} == {"la du", "i-en"}
    assert skipped == []  # the all-empty audio_Tromsø etc. lists raise no warning
    assert not [r for r in rows if r["dialect"] == "Tromsø"]


def test_extract_skips_non_words_mp3_paths_and_reports_them():
    wav = "D:\\Workspace\\CalstFiles\\WordObjectContent\\Norwegian\\OriginalWords_Wav\\anMtr_x_bolig_y.wav"
    rec = _rec("bolig", Oslo=["Oslo_Normal_A.mp3"])
    rec["audio_Oslo"].append(wav)
    rows, skipped = fpa.build_inventory([_doc(rec)])
    assert [r["path"] for r in rows] == ["Oslo/Oslo_Normal_A.mp3"]
    assert len(skipped) == 1 and skipped[0]["path"] == wav and "Words_MP3" in skipped[0]["reason"]


def test_merge_preserves_progress_adds_new_and_keeps_vanished():
    old = [
        {"word": "a", "dialect": "Oslo", "take": 0, "url": "u1", "path": "Oslo/1.mp3", "status": "ok", "bytes": 5, "sha256": "h"},
        {"word": "gone", "dialect": "Oslo", "take": 0, "url": "u9", "path": "Oslo/9.mp3", "status": "ok", "bytes": 1, "sha256": "g"},
    ]
    new = [
        {"word": "a", "dialect": "Oslo", "take": 0, "url": "u1", "path": "Oslo/1.mp3", "status": "pending"},
        {"word": "b", "dialect": "Oslo", "take": 0, "url": "u2", "path": "Oslo/2.mp3", "status": "pending"},
    ]
    merged, dropped = fpa.merge_manifest(new, old)
    by_url = {r["url"]: r for r in merged}
    assert by_url["u1"]["status"] == "ok" and by_url["u1"]["sha256"] == "h" and by_url["u1"]["bytes"] == 5
    assert by_url["u2"]["status"] == "pending"
    assert "u9" in by_url and [r["url"] for r in dropped] == ["u9"]


def test_manifest_roundtrip_is_jsonl_and_atomic(tmp_path):
    p = tmp_path / "m.jsonl"
    rows = [{"word": "å", "dialect": "Sandnessjøen", "take": 0, "url": "u", "path": "x", "status": "pending"}]
    fpa.save_manifest(p, rows)
    assert fpa.load_manifest(p) == rows
    assert "Sandnessjøen" in p.read_text(encoding="utf-8")  # not \u-escaped
    assert not (tmp_path / "m.jsonl.tmp").exists()


# ─────────────────────────── download harness ───────────────────────────

class FakeResp:
    def __init__(self, status=200, body=b"ID3" + b"\x00" * 97, ctype="audio/mpeg", headers=None,
                 declared_len=None, raise_mid=False):
        self.status_code = status
        self.body = body
        self.headers = {"Content-Type": ctype, **(headers or {})}
        if declared_len is not None:
            self.headers["Content-Length"] = str(declared_len)
        self.raise_mid = raise_mid
        self.closed = False

    def iter_content(self, n):
        half = len(self.body) // 2
        yield self.body[:half]
        if self.raise_mid:
            raise requests.exceptions.ChunkedEncodingError("boom")
        yield self.body[half:]

    def close(self):
        self.closed = True


class FakeSession:
    """`handler(url, call_number) -> FakeResp`; may raise instead."""

    def __init__(self, handler=None):
        self.handler = handler or (lambda url, n: FakeResp())
        self.calls: list[str] = []
        self.headers_seen: list[dict] = []

    def get(self, url, **kw):
        self.calls.append(url)
        self.headers_seen.append(kw.get("headers", {}))
        return self.handler(url, len(self.calls))

    def close(self):
        pass


def _rows(n=3, dialect="Oslo"):
    return [
        {"word": f"w{i}", "dialect": dialect, "take": 0, "translation": [], "url": fpa.BASE_URL + f"{dialect}_Normal_{i}.mp3",
         "path": f"{dialect}/{dialect}_Normal_{i}.mp3", "status": "pending"}
        for i in range(n)
    ]


def _ui():
    buf = io.StringIO()
    return fpa.Ui(Console(file=buf, force_terminal=False, width=200)), buf


def _dl(tmp_path, rows, session, sleeps=None, **kw):
    sleeps = sleeps if sleeps is not None else []
    ui, buf = _ui()
    manifest = tmp_path / "manifest.jsonl"
    fpa.save_manifest(manifest, rows)
    dl = fpa.Downloader(rows, manifest, tmp_path, session=session, ui=ui, sleep=sleeps.append,
                        rng=random.Random(1), **kw)
    return dl, manifest, buf


# ─────────────────────────── download: success & rejections ───────────────────────────

def test_success_writes_file_hash_bytes_and_no_part(tmp_path):
    rows = _rows(1)
    dl, manifest, _ = _dl(tmp_path, rows, FakeSession())
    res = dl.run()
    body = b"ID3" + b"\x00" * 97
    assert (res.ok, res.failed) == (1, 0)
    assert rows[0]["status"] == "ok" and rows[0]["bytes"] == 100
    assert rows[0]["sha256"] == hashlib.sha256(body).hexdigest()
    assert (tmp_path / rows[0]["path"]).read_bytes() == body
    assert not list(tmp_path.rglob("*.part"))
    assert fpa.load_manifest(manifest)[0]["status"] == "ok"


def test_identifying_user_agent_is_sent(tmp_path):
    s = FakeSession()
    _dl(tmp_path, _rows(1), s)[0].run()
    assert "smia" in s.headers_seen[0]["User-Agent"]


@pytest.mark.parametrize(
    "resp",
    [
        FakeResp(ctype="text/html", body=b"<html>nope</html>"),
        FakeResp(body=b""),
        FakeResp(declared_len=999),  # truncated vs Content-Length
    ],
)
def test_bad_responses_never_become_files(tmp_path, resp):
    rows = _rows(1)
    dl, _, _ = _dl(tmp_path, rows, FakeSession(lambda u, n: resp))
    dl.run()
    assert rows[0]["status"] == "failed"
    assert "bytes" not in rows[0]
    assert not (tmp_path / rows[0]["path"]).exists()
    assert not list(tmp_path.rglob("*.part"))


def test_connection_dropped_mid_body_is_retried_then_succeeds(tmp_path):
    seen = []
    rows = _rows(1)
    dl, _, _ = _dl(tmp_path, rows, FakeSession(lambda u, n: FakeResp(raise_mid=True) if n == 1 else FakeResp()), sleeps=seen)
    dl.run()
    assert rows[0]["status"] == "ok"
    assert seen == [2.0]  # one backoff, no leftover .part
    assert not list(tmp_path.rglob("*.part"))


# ─────────────────────────── download: retry & politeness ───────────────────────────

def test_retry_after_is_honoured(tmp_path):
    seen = []
    rows = _rows(1)
    s = FakeSession(lambda u, n: FakeResp(status=429, headers={"Retry-After": "7"}) if n == 1 else FakeResp())
    dl, _, buf = _dl(tmp_path, rows, s, sleeps=seen)
    dl.run()
    assert rows[0]["status"] == "ok"
    assert seen == [7.0]
    assert "Retry-After 7" in buf.getvalue() and "429" in buf.getvalue()


def test_503_backs_off_exponentially_then_fails_after_five_attempts(tmp_path):
    seen = []
    rows = _rows(1)
    s = FakeSession(lambda u, n: FakeResp(status=503))
    dl, _, _ = _dl(tmp_path, rows, s, sleeps=seen)
    dl.run()
    assert len(s.calls) == 5
    assert seen == [2.0, 4.0, 8.0, 16.0]
    assert rows[0]["status"] == "failed"


def test_network_error_is_retried(tmp_path):
    rows = _rows(1)

    def handler(u, n):
        if n < 3:
            raise requests.ConnectionError("down")
        return FakeResp()

    dl, _, _ = _dl(tmp_path, rows, FakeSession(handler))
    dl.run()
    assert rows[0]["status"] == "ok"


def test_parse_retry_after_forms():
    assert fpa.parse_retry_after("7") == 7.0
    assert fpa.parse_retry_after(None) is None
    assert fpa.parse_retry_after("garbage") is None
    assert fpa.parse_retry_after("Wed, 21 Oct 2015 07:28:00 GMT") == 0.0  # past date → no wait


def test_404_is_missing_then_not_rerequested_unless_retry_failed(tmp_path):
    rows = _rows(1)
    s = FakeSession(lambda u, n: FakeResp(status=404))
    dl, _, _ = _dl(tmp_path, rows, s)
    dl.run()
    assert rows[0]["status"] == "missing" and len(s.calls) == 1

    dl.run()  # plain re-run: held back
    assert len(s.calls) == 1

    s.handler = lambda u, n: FakeResp()
    res = dl.run(retry_failed=True)
    assert len(s.calls) == 2 and rows[0]["status"] == "ok" and res.ok == 1


def test_requests_are_spaced_by_jitter_and_skips_cost_nothing(tmp_path):
    seen = []
    rows = _rows(4)
    # row 0 is already done on disk → skipped without a sleep or request
    done = tmp_path / rows[0]["path"]
    done.parent.mkdir(parents=True)
    done.write_bytes(b"abcde")
    rows[0].update(status="ok", bytes=5, sha256=hashlib.sha256(b"abcde").hexdigest())

    s = FakeSession()
    dl, _, _ = _dl(tmp_path, rows, s, sleeps=seen)
    res = dl.run()
    assert res.skipped == 1 and len(s.calls) == 3
    assert len(seen) == 2  # between 3 real requests; none for the skip, none before the first
    assert all(0.5 <= x <= 1.0 for x in seen)


# ─────────────────────────── download: resume & interruption ───────────────────────────

def test_ok_rows_with_files_cause_no_requests(tmp_path):
    rows = _rows(2)
    for r in rows:
        p = tmp_path / r["path"]
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"xyz")
        r.update(status="ok", bytes=3, sha256="h")
    s = FakeSession()
    seen = []
    dl, _, _ = _dl(tmp_path, rows, s, sleeps=seen)
    res = dl.run()
    assert s.calls == [] and seen == [] and res.skipped == 2


def test_ok_row_whose_file_vanished_is_refetched(tmp_path):
    rows = _rows(1)
    rows[0].update(status="ok", bytes=100, sha256="h")
    s = FakeSession()
    _dl(tmp_path, rows, s)[0].run()
    assert len(s.calls) == 1 and (tmp_path / rows[0]["path"]).exists()


def test_crash_between_rename_and_manifest_is_repaired_without_request(tmp_path):
    rows = _rows(1)
    p = tmp_path / rows[0]["path"]
    p.parent.mkdir(parents=True)
    p.write_bytes(b"whole-file")
    s = FakeSession()
    res = _dl(tmp_path, rows, s)[0].run()
    assert s.calls == [] and res.repaired == 1
    assert rows[0]["status"] == "ok" and rows[0]["bytes"] == 10
    assert rows[0]["sha256"] == hashlib.sha256(b"whole-file").hexdigest()


def test_stale_part_is_removed_and_refetched(tmp_path):
    rows = _rows(1)
    part = tmp_path / (rows[0]["path"] + ".part")
    part.parent.mkdir(parents=True)
    part.write_bytes(b"half")
    s = FakeSession()
    _dl(tmp_path, rows, s)[0].run()
    assert len(s.calls) == 1 and not part.exists() and rows[0]["status"] == "ok"


def test_interrupt_leaves_valid_manifest_no_partial_and_resumes(tmp_path):
    rows = _rows(4)

    def handler(u, n):
        if n == 3:
            raise KeyboardInterrupt
        return FakeResp()

    s = FakeSession(handler)
    dl, manifest, buf = _dl(tmp_path, rows, s)
    res = dl.run()
    assert res.interrupted and res.remaining == 2  # the in-flight row + the one after it
    saved = fpa.load_manifest(manifest)  # still valid JSONL
    assert [r["status"] for r in saved] == ["ok", "ok", "pending", "pending"]
    assert not (tmp_path / rows[2]["path"]).exists()
    assert not list(tmp_path.rglob("*.part"))

    # resume: only the unfinished rows are requested
    s2 = FakeSession()
    dl2 = fpa.Downloader(saved, manifest, tmp_path, session=s2, ui=_ui()[0], sleep=lambda x: None)
    res2 = dl2.run()
    assert len(s2.calls) == 2 and res2.ok == 2 and res2.skipped == 2
    assert all(r["status"] == "ok" for r in fpa.load_manifest(manifest))


def test_cli_interrupt_exits_130_and_prints_resume_hint(tmp_path):
    rows = _rows(2)
    fpa.save_manifest(tmp_path / fpa.MANIFEST_NAME, rows)

    def handler(u, n):
        raise KeyboardInterrupt

    args = fpa.build_parser().parse_args(["download", "--audio-dir", str(tmp_path)])
    out = io.StringIO()
    code = fpa.cmd_download(args, Console(file=out, force_terminal=False, width=200),
                            session=FakeSession(handler), sleep=lambda s: None)
    assert code == 130
    assert "Resume" in out.getvalue()


def test_dialect_filter_and_limit(tmp_path):
    rows = _rows(3, "Oslo") + _rows(2, "Bergen")
    s = FakeSession()
    res = _dl(tmp_path, rows, s)[0].run(dialects=["bergen"], limit=1)
    assert res.ok == 1 and len(s.calls) == 1 and "Bergen" in s.calls[0]


# ─────────────────────────── UI ───────────────────────────

def test_non_tty_output_is_plain_timestamped_lines_without_control_sequences(tmp_path):
    rows = _rows(2)
    s = FakeSession(lambda u, n: FakeResp(status=503) if n == 1 else FakeResp())
    dl, _, buf = _dl(tmp_path, rows, s)
    dl.run()
    out = buf.getvalue()
    assert "\x1b" not in out
    lines = [l for l in out.splitlines() if l.strip()]
    assert all(l[2] == ":" and l[5] == ":" for l in lines)  # HH:MM:SS prefix
    assert any("WARN" in l and "503" in l for l in lines)
    assert any("ok 100 B" in l for l in lines)


def test_summary_table_counts_per_dialect():
    buf = io.StringIO()
    rows = _rows(2, "Oslo") + _rows(1, "Bergen")
    rows[0].update(status="ok", bytes=2048)
    rows[2].update(status="missing")
    fpa.print_download_summary(Console(file=buf, force_terminal=False, width=120), rows)
    out = buf.getvalue()
    assert "Bergen" in out and "Oslo" in out and "total" in out and "2.0 KiB" in out


# ─────────────────────────── single-instance lock ───────────────────────────
# Regression: a second concurrent `download` shared one fixed manifest temp
# name, so one run's os.replace found the other's temp file already gone
# (FileNotFoundError traceback) and the runs overwrote each other's progress.

def test_run_lock_is_exclusive_and_released(tmp_path):
    with fpa.run_lock(tmp_path):
        with pytest.raises(fpa.AlreadyRunning):
            with fpa.run_lock(tmp_path):
                pytest.fail("second lock must not be acquired")
    with fpa.run_lock(tmp_path):  # released on exit, even after the failed attempt
        pass


def test_run_lock_released_when_the_body_raises(tmp_path):
    with pytest.raises(RuntimeError):
        with fpa.run_lock(tmp_path):
            raise RuntimeError("boom")
    with fpa.run_lock(tmp_path):
        pass


def test_second_run_exits_3_with_message_not_a_traceback(tmp_path, capsys):
    fpa.save_manifest(tmp_path / fpa.MANIFEST_NAME, _rows(1))
    with fpa.run_lock(tmp_path):
        for cmd in (["download"], ["extract", "--source", str(tmp_path / "x.json")]):
            assert fpa.main([*cmd, "--audio-dir", str(tmp_path)]) == 3
    assert "already" in capsys.readouterr().out
    assert fpa.load_manifest(tmp_path / fpa.MANIFEST_NAME)[0]["status"] == "pending"  # untouched


def test_manifest_temp_name_is_per_process(tmp_path, monkeypatch):
    seen = []
    real = fpa.os.replace
    monkeypatch.setattr(fpa.os, "replace", lambda src, dst: (seen.append(str(src)), real(src, dst))[1])
    fpa.save_manifest(tmp_path / "m.jsonl", _rows(1))
    assert len(seen) == 1 and str(fpa.os.getpid()) in seen[0]
    assert not list(tmp_path.glob("*.tmp"))
