"""Tests for /tts wiring (tasks 5.1, 5.7) and the manual-link adapters
(provider-tokens-and-manual-link-fallback tasks 4.1-4.2)."""

from __future__ import annotations

from adapters.manual_link import ManualLinkAdapter, _filmot_url, _forvo_url
from app import app as real_app
from audio_cache import fetch, store
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


def test_forvo_url_maps_nb_to_forvos_own_code():
    # Forvo's own code for Norwegian is "no", not "nb"; the real
    # shareable per-language link fragment is the bare code, not
    # "#language-no" (user-corrected, see adapters/manual_link.py).
    assert _forvo_url("hygge", "nb") == "https://forvo.com/word/hygge/#no"


def test_forvo_url_passes_through_other_codes():
    assert _forvo_url("Haus", "de") == "https://forvo.com/word/Haus/#de"
    assert _forvo_url("house", "en") == "https://forvo.com/word/house/#en"


def test_forvo_url_encodes_special_characters():
    assert _forvo_url("på", "nb") == "https://forvo.com/word/p%C3%A5/#no"


def test_filmot_url_construction():
    assert _filmot_url("hus", "nb") == "https://filmot.com/search/hus/1?gridView=1&lang=no"


def test_filmot_url_joins_multi_word_query_with_plus():
    assert (
        _filmot_url("jeg er norsk", "nb")
        == "https://filmot.com/search/jeg+er+norsk/1?gridView=1&lang=no"
    )


def test_manual_link_adapter_returns_empty_candidates_and_url():
    adapter = ManualLinkAdapter(lambda text, lang: f"https://example.com/{text}/{lang}")
    result = adapter.lookup({"text": "hus", "lang": "nb"})
    assert result == {"candidates": [], "url": "https://example.com/hus/nb"}


def test_providers_catalog_still_lists_forvo_and_filmot_for_tts(monkeypatch):
    monkeypatch.setenv("SMIA_AUTH_TOKEN", "test-token")
    resp = real_app.test_client().get("/providers", headers={"Authorization": "Bearer test-token"})
    assert resp.status_code == 200
    assert {"forvo", "filmot"} <= set(resp.get_json()["tts"])
