"""The `pygmalion` /tts adapter (pygmalion-tts-provider tasks 4.x, 5.3-5.8):
exact casefolded lookup, one `{sha256, source, voice}` candidate per recording,
Oslo first, no new fields, no variant fan-out. Seeds `pygmalion_audio` itself,
so no real corpus is required; the end-to-end tests go through the real app."""

from __future__ import annotations

import hashlib

import pytest

from adapters.pygmalion_tts import PygmalionTtsAdapter
from app import app as real_app
from audio_cache import store
from db.models import PygmalionAudio, TtsAudio
from db.session import get_sessionmaker

AUTH = {"Authorization": "Bearer test-token"}


@pytest.fixture(autouse=True)
def _clean_pygmalion():
    Session = get_sessionmaker()
    with Session() as db:
        db.query(PygmalionAudio).delete()
        db.query(TtsAudio).delete()
        db.commit()
    yield


def _seed(*entries):
    """entries: (word, dialect, take, audio_bytes). Returns the sha256s in order."""
    shas = []
    with get_sessionmaker()() as db:
        for word, dialect, take, data in entries:
            sha = store(db, data, "audio/mpeg")
            db.add(PygmalionAudio(word=word, dialect=dialect, take=take, sha256=sha))
            shas.append(sha)
        db.commit()
    return shas


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _lookup(text, lang="nb"):
    return PygmalionTtsAdapter().lookup({"text": text, "lang": lang})["candidates"]


def test_one_candidate_per_recording_ordered_oslo_first_with_exact_keys():
    o0, o1, b0 = _seed(
        ("led", "Oslo", 0, b"o0"), ("led", "Oslo", 1, b"o1"), ("led", "Bergen", 0, b"b0")
    )
    cands = _lookup("led")
    assert [(c["voice"], c["sha256"]) for c in cands] == [("Oslo", o0), ("Oslo", o1), ("Bergen", b0)]
    for c in cands:
        assert set(c) == {"sha256", "source", "voice"} and c["source"] == "human"  # no invented field


def test_oslo_leads_even_when_it_sorts_after_other_dialects():
    _seed(("hus", "Elverum", 0, b"e"), ("hus", "Oslo", 0, b"o"), ("hus", "Bergen", 0, b"b"))
    assert [c["voice"] for c in _lookup("hus")] == ["Oslo", "Bergen", "Elverum"]


def test_recordings_within_a_dialect_keep_take_order():
    _seed(("hus", "Oslo", 2, b"c"), ("hus", "Oslo", 0, b"a"), ("hus", "Oslo", 1, b"b"))
    assert [x["sha256"] for x in _lookup("hus")] == [_sha(b"a"), _sha(b"b"), _sha(b"c")]


def test_casefold_and_surrounding_whitespace_are_ignored():
    _seed(("led", "Oslo", 0, b"x"))
    assert _lookup("  Led ") == _lookup("led") != []


def test_phrases_match_exactly_or_not_at_all():
    _seed(("la du", "Oslo", 0, b"x"))
    assert len(_lookup("la du")) == 1
    assert _lookup("la deg") == []


def test_unknown_word_is_empty_not_an_error():
    assert PygmalionTtsAdapter().lookup({"text": "qzxnotaword", "lang": "nb"}) == {"candidates": []}


def test_count_function_reports_recordings_live():
    from adapters.pygmalion_tts import pygmalion_audio_count
    with get_sessionmaker()() as db:
        assert pygmalion_audio_count(db) == 0
    _seed(("led", "Oslo", 0, b"a"), ("led", "Bergen", 0, b"b"), ("ledd", "Oslo", 0, b"c"))
    with get_sessionmaker()() as db:
        assert pygmalion_audio_count(db) == 3


def test_registered_as_a_tts_provider_with_a_count_source():
    from registry import registry
    assert "pygmalion" in registry.providers_for("tts")
    _seed(("led", "Oslo", 0, b"a"), ("led", "Oslo", 1, b"b"))
    with get_sessionmaker()() as db:
        assert registry.counts_for(db, "tts")["pygmalion"] == 2


def test_other_languages_get_no_candidates():
    _seed(("led", "Oslo", 0, b"x"))
    assert _lookup("led", lang="en") == []


def test_citation_form_is_not_retried_as_the_bare_noun():
    _seed(("kalv", "Oslo", 0, b"x"))
    assert _lookup("en kalv") == []  # no norwegian-input variant fan-out for this provider


def test_identical_audio_is_deduplicated_by_sha256():
    _seed(("led", "Oslo", 0, b"same"), ("led", "Bergen", 0, b"same"))
    cands = _lookup("led")
    assert len(cands) == 1 and cands[0]["voice"] == "Oslo"


# ───────────────────────── through the real app ─────────────────────────

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SMIA_AUTH_TOKEN", "test-token")
    return real_app.test_client()


def test_post_tts_returns_candidates_and_get_serves_the_bytes(client):
    (sha,) = _seed(("led", "Oslo", 0, b"ID3-fake-mp3"))
    resp = client.post("/tts", json={"text": "led", "lang": "nb", "provider": "pygmalion"}, headers=AUTH)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["provider"] == "pygmalion"
    assert body["candidates"] == [{"sha256": sha, "source": "human", "voice": "Oslo"}]

    audio = client.get(f"/tts/{sha}", headers=AUTH)
    assert audio.status_code == 200
    assert audio.data == b"ID3-fake-mp3" and audio.headers["Content-Type"].startswith("audio/mpeg")


def test_post_tts_miss_is_a_successful_empty_response(client):
    resp = client.post("/tts", json={"text": "qzxnotaword", "lang": "nb", "provider": "pygmalion"}, headers=AUTH)
    assert resp.status_code == 200 and resp.get_json()["candidates"] == []


def test_providers_lists_pygmalion_with_a_live_count(client):
    first = client.get("/providers", headers=AUTH).get_json()
    assert "pygmalion" in first["tts"]
    assert first["counts"]["tts"]["pygmalion"] == 0

    _seed(("led", "Oslo", 0, b"a"), ("led", "Oslo", 1, b"b"))
    second = client.get("/providers", headers=AUTH).get_json()
    assert second["counts"]["tts"]["pygmalion"] == 2  # live, no restart
