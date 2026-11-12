"""
scripts/import_pygmalion.py — load the Pygmalion recordings fetched by
`scripts/fetch_pygmalion_audio.py` into smia: each mp3 goes into the private
content-addressed audio cache (`audio_cache.store`) and its
word / dialect / take -> sha256 mapping into `pygmalion_audio`, which is what
the `pygmalion` /tts adapter queries.

Reads only committed files (the manifest and the mp3s beside it) — no network.
Every file's sha256 is checked against the manifest before it enters the
cache, so a corrupted or substituted file is skipped, not served.

Idempotent: `store()` is a no-op for known bytes and existing mapping rows are
left alone, so re-running (or a half-finished earlier run) is safe. To pick up
newly fetched words, truncate `pygmalion_audio` and restart — bootstrap only
imports when that table is empty (design D3/Risks).

Run: python -m scripts.import_pygmalion providers/pygmalion/audio/manifest.jsonl
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from audio_cache import store
from db.models import PygmalionAudio
from db.session import session_scope


def _rows(manifest: Path):
    with manifest.open(encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if line:
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as exc:
                    print(f"[import_pygmalion] {manifest}:{n}: skipping invalid JSON line ({exc})", file=sys.stderr)


def run(manifest_path: str) -> dict:
    """Returns `{imported, existing, skipped, mismatched}` counts."""
    manifest = Path(manifest_path)
    if not manifest.is_file():
        raise FileNotFoundError(f"pygmalion manifest not found: {manifest}")
    base = manifest.parent

    counts = {"imported": 0, "existing": 0, "skipped": 0, "mismatched": 0}
    with session_scope() as db:
        for row in _rows(manifest):
            if row.get("status") != "ok":
                counts["skipped"] += 1
                continue
            path = base / row["path"]
            try:
                data = path.read_bytes()
            except OSError:
                print(f"[import_pygmalion] missing file {path}, skipping", file=sys.stderr)
                counts["skipped"] += 1
                continue
            if hashlib.sha256(data).hexdigest() != row.get("sha256"):
                print(f"[import_pygmalion] sha256 mismatch for {path}, skipping", file=sys.stderr)
                counts["mismatched"] += 1
                continue

            sha256 = store(db, data, "audio/mpeg")
            key = (row["word"].casefold(), row["dialect"], row["take"])
            if db.get(PygmalionAudio, key) is not None:
                counts["existing"] += 1
                continue
            db.add(PygmalionAudio(word=key[0], dialect=key[1], take=key[2], sha256=sha256))
            counts["imported"] += 1
        db.commit()

    print(
        "[import_pygmalion] {imported} imported, {existing} already present, "
        "{skipped} skipped, {mismatched} hash-mismatched".format(**counts),
        file=sys.stderr,
    )
    return counts


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("manifest", help="providers/pygmalion/audio/manifest.jsonl")
    run(ap.parse_args().manifest)
