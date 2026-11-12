"""scripts/import_pygmalion.py — manifest + mp3s -> `pygmalion_audio` and the
private audio cache (pygmalion-tts-provider tasks 3.1-3.4, 5.1-5.2).

Builds a tiny throwaway corpus in tmp_path (manifest + files laid out exactly
as scripts/fetch_pygmalion_audio.py writes them), so no real recordings are
needed. Requires the migrated test database, like the other table tests."""

from __future__ import annotations

import hashlib
import json

import pytest

from audio_cache import fetch
from db.models import PygmalionAudio, TtsAudio
from db.session import get_sessionmaker
from scripts import import_pygmalion
from scripts.bootstrap import _IMPORTS


@pytest.fixture(autouse=True)
def _clean_pygmalion():
    Session = get_sessionmaker()
    with Session() as db:
        db.query(PygmalionAudio).delete()
        db.query(TtsAudio).delete()
        db.commit()
    yield


def _corpus(tmp_path, entries):
    """entries: (word, dialect, take, content, overrides) -> manifest path.
    Files go to <tmp>/<Dialect>/<name>.mp3 like the fetch script lays them out."""
    rows = []
    for i, (word, dialect, take, content, extra) in enumerate(entries):
        rel = f"{dialect}/{dialect}_Normal_{i}.mp3"
        if content is not None:
            (tmp_path / dialect).mkdir(exist_ok=True)
            (tmp_path / rel).write_bytes(content)
        row = {
            "word": word, "dialect": dialect, "take": take, "translation": [],
            "url": f"https://example.invalid/{i}.mp3", "path": rel, "status": "ok",
            "bytes": len(content or b""), "sha256": hashlib.sha256(content or b"").hexdigest(),
        }
        row.update(extra)
        rows.append(row)
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    return str(manifest)


def _corpus_path_with_one_row():
    import tempfile
    from pathlib import Path
    return _corpus(Path(tempfile.mkdtemp()), [("led", "Oslo", 0, b"AAA", {})])


def _mapping_rows():
    with get_sessionmaker()() as db:
        return sorted((r.word, r.dialect, r.take, r.sha256) for r in db.query(PygmalionAudio).all())


def test_imports_mapping_and_stores_bytes_in_the_audio_cache(tmp_path):
    m = _corpus(tmp_path, [
        ("Led", "Oslo", 0, b"AAA", {}),
        ("led", "Sandnessjøen", 0, b"BBB", {}),
    ])
    counts = import_pygmalion.run(m)
    assert counts == {"imported": 2, "existing": 0, "skipped": 0, "mismatched": 0}

    rows = _mapping_rows()
    assert [(w, d, t) for w, d, t, _ in rows] == [("led", "Oslo", 0), ("led", "Sandnessjøen", 0)]  # word casefolded, dialect verbatim
    with get_sessionmaker()() as db:
        data, ctype = fetch(db, hashlib.sha256(b"AAA").hexdigest())
    assert data == b"AAA" and ctype == "audio/mpeg"


def test_second_run_is_idempotent(tmp_path):
    m = _corpus(tmp_path, [("led", "Oslo", 0, b"AAA", {}), ("led", "Oslo", 1, b"BBB", {})])
    import_pygmalion.run(m)
    before = _mapping_rows()
    counts = import_pygmalion.run(m)
    assert counts["imported"] == 0 and counts["existing"] == 2
    assert _mapping_rows() == before


def test_non_ok_rows_and_missing_files_are_skipped(tmp_path):
    m = _corpus(tmp_path, [
        ("ok", "Oslo", 0, b"AAA", {}),
        ("pending", "Oslo", 0, b"BBB", {"status": "pending"}),
        ("gone", "Oslo", 0, None, {}),  # no file written
    ])
    counts = import_pygmalion.run(m)
    assert counts["imported"] == 1 and counts["skipped"] == 2
    assert [r[0] for r in _mapping_rows()] == ["ok"]


def test_hash_mismatch_is_skipped_and_stores_nothing(tmp_path):
    m = _corpus(tmp_path, [("led", "Oslo", 0, b"tampered", {"sha256": hashlib.sha256(b"original").hexdigest()})])
    counts = import_pygmalion.run(m)
    assert counts["mismatched"] == 1 and counts["imported"] == 0
    assert _mapping_rows() == []
    with get_sessionmaker()() as db:
        assert db.query(TtsAudio).count() == 0  # the bad bytes never entered the cache


def test_absent_manifest_raises_filenotfound_for_bootstrap_to_warn_about(tmp_path):
    with pytest.raises(FileNotFoundError):
        import_pygmalion.run(str(tmp_path / "nope.jsonl"))


def test_bootstrap_runs_the_import_against_the_committed_manifest_only_when_empty():
    entry = next(e for e in _IMPORTS if e[0] == "pygmalion_audio")
    assert entry[1] is import_pygmalion.run
    assert entry[2] == ["providers/pygmalion/audio/manifest.jsonl"]
    # bootstrap's generic check is "table is empty" on the first element
    from scripts.bootstrap import _table_is_empty
    assert _table_is_empty("pygmalion_audio") is True
    import_pygmalion.run(_corpus_path_with_one_row())
    assert _table_is_empty("pygmalion_audio") is False


def test_real_committed_corpus_imports_cleanly():
    """The fetched corpus itself: every `ok` row's file exists and hashes right."""
    counts = import_pygmalion.run("providers/pygmalion/audio/manifest.jsonl")
    assert counts["mismatched"] == 0 and counts["skipped"] == 0
    assert counts["imported"] == 1176
    with get_sessionmaker()() as db:
        assert db.query(PygmalionAudio).count() == 1176
        assert {r.dialect for r in db.query(PygmalionAudio).all()} == {
            "Oslo", "Bergen", "Stavanger", "Trondheim", "Elverum", "Sandnessjøen", "Malm"
        }
