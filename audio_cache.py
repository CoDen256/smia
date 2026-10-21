"""
audio_cache.py — smia's private, content-addressed audio cache (task 5.1).
Every `/tts` adapter calls `store(bytes, content_type) -> sha256` once it
has real audio bytes (synthesized or downloaded); `app.py`'s
`GET /tts/{sha256}` route (distinct from the generic lookup-cache
`GET /<kind>/{id}`, per the tts-api spec) reads back via `fetch(sha256)`.

This is explicitly NOT canonical storage (tts-api spec, CLAUDE.md's hard
boundary) — callers that need durable audio copy bytes elsewhere.
"""

from __future__ import annotations

import hashlib

from sqlalchemy import text

from db.models import TtsAudio


def store(db, data: bytes, content_type: str) -> str:
    sha256 = hashlib.sha256(data).hexdigest()
    row = db.get(TtsAudio, sha256)
    if row is None:
        db.add(TtsAudio(sha256=sha256, content_type=content_type, data=data))
        db.commit()
    return sha256


def fetch(db, sha256: str):
    """Returns `(data, content_type)` or `None` if unknown."""
    row = db.execute(
        text("SELECT data, content_type FROM tts_audio WHERE sha256 = :sha256"), {"sha256": sha256}
    ).first()
    if row is None:
        return None
    return bytes(row[0]), row[1]
