"""Tests for /tts wiring and the stub adapters (tasks 5.1, 5.7)."""

from __future__ import annotations

import pytest

from adapters.not_configured import NotConfiguredAdapter
from audio_cache import fetch, store
from cache import ProviderLookupError
from db.session import get_sessionmaker


def test_audio_cache_round_trip():
    Session = get_sessionmaker()
    with Session() as db:
        sha = store(db, b"fake-mp3-bytes", "audio/mpeg")
    with Session() as db:
        data, content_type = fetch(db, sha)
    assert data == b"fake-mp3-bytes"
    assert content_type == "audio/mpeg"


def test_audio_cache_is_idempotent_on_identical_bytes():
    Session = get_sessionmaker()
    with Session() as db:
        sha1 = store(db, b"same-bytes", "audio/mpeg")
        sha2 = store(db, b"same-bytes", "audio/mpeg")
    assert sha1 == sha2


def test_fetch_unknown_sha_returns_none():
    Session = get_sessionmaker()
    with Session() as db:
        assert fetch(db, "deadbeef") is None


def test_stub_adapter_raises_clear_error():
    adapter = NotConfiguredAdapter("forvo", "needs a Forvo API key")
    with pytest.raises(ProviderLookupError, match="forvo.*Forvo API key"):
        adapter.lookup({"text": "hus", "lang": "nb"})
