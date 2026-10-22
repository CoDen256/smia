"""Tests for the `elevenlabs` /tts and /stt adapters (add-elevenlabs-
provider tasks 2.1-2.4), mocking the official `elevenlabs` SDK client —
no live `ELEVENLABS_TOKEN` was available in this environment to test
against the real API (see adapters/elevenlabs.py's docstring; task 3.1
needs to be run by whoever has the real token)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from adapters.elevenlabs import ElevenLabsSttAdapter, ElevenLabsTtsAdapter
from cache import ProviderLookupError
from db.session import get_sessionmaker


def _mock_voice(voice_id="v1", name="Rachel", gender=None):
    return SimpleNamespace(voice_id=voice_id, name=name, labels={"gender": gender} if gender else {})


def _mock_client(voices=None, tts_chunks=None, stt_text=None):
    client = MagicMock()
    client.voices.search.return_value = SimpleNamespace(voices=voices or [])
    client.text_to_speech.convert.return_value = iter(tts_chunks or [b"fake-mp3-bytes"])
    client.speech_to_text.convert.return_value = SimpleNamespace(text=stt_text or "")
    return client


def test_tts_without_token_errors_clearly(monkeypatch):
    monkeypatch.delenv("ELEVENLABS_TOKEN", raising=False)
    with pytest.raises(ProviderLookupError, match="ELEVENLABS_TOKEN"):
        ElevenLabsTtsAdapter().lookup({"text": "hus", "lang": "nb"})


def test_stt_without_token_errors_clearly(monkeypatch):
    monkeypatch.delenv("ELEVENLABS_TOKEN", raising=False)
    with pytest.raises(ProviderLookupError, match="ELEVENLABS_TOKEN"):
        ElevenLabsSttAdapter().lookup({"audio_b64": "ZmFrZQ=="})


def test_tts_returns_candidate_with_stored_audio(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_TOKEN", "fake-token")
    voice = _mock_voice(voice_id="v1", name="Rachel", gender="female")
    client = _mock_client(voices=[voice], tts_chunks=[b"abc", b"def"])
    with patch("adapters.elevenlabs.ElevenLabs", return_value=client):
        result = ElevenLabsTtsAdapter().lookup({"text": "hus", "lang": "nb"})

    assert len(result["candidates"]) == 1
    candidate = result["candidates"][0]
    assert candidate["voice"] == "Rachel"
    assert candidate["gender"] == "female"
    assert "sha256" in candidate

    Session = get_sessionmaker()
    with Session() as db:
        from audio_cache import fetch

        data, content_type = fetch(db, candidate["sha256"])
    assert data == b"abcdef"  # chunks concatenated
    assert content_type == "audio/mpeg"


def test_tts_falls_back_to_any_voice_when_none_match_language(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_TOKEN", "fake-token")
    fallback_voice = _mock_voice(voice_id="v2", name="Adam")
    client = MagicMock()
    client.voices.search.side_effect = [
        SimpleNamespace(voices=[]),  # language-filtered search: no match
        SimpleNamespace(voices=[fallback_voice]),  # unfiltered fallback
    ]
    client.text_to_speech.convert.return_value = iter([b"fake-mp3-bytes"])
    with patch("adapters.elevenlabs.ElevenLabs", return_value=client):
        result = ElevenLabsTtsAdapter().lookup({"text": "hus", "lang": "nb"})
    assert result["candidates"][0]["voice"] == "Adam"


def test_tts_no_voices_available_is_a_clear_error(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_TOKEN", "fake-token")
    client = _mock_client(voices=[])
    with patch("adapters.elevenlabs.ElevenLabs", return_value=client):
        with pytest.raises(ProviderLookupError, match="no voices available"):
            ElevenLabsTtsAdapter().lookup({"text": "hus", "lang": "nb"})


def test_stt_parses_text(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_TOKEN", "fake-token")
    client = _mock_client(stt_text="hello world")
    with patch("adapters.elevenlabs.ElevenLabs", return_value=client):
        result = ElevenLabsSttAdapter().lookup({"audio_b64": "ZmFrZQ==", "lang": "en"})
    assert result == {"text": "hello world"}
    _, kwargs = client.speech_to_text.convert.call_args
    assert kwargs["language_code"] == "en"


def _api_error(status_code, body="error"):
    from elevenlabs.core.api_error import ApiError

    return ApiError(status_code=status_code, body=body)


def test_quota_exceeded_is_mapped_clearly(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_TOKEN", "fake-token")
    client = _mock_client(voices=[_mock_voice()])
    client.text_to_speech.convert.side_effect = _api_error(429, "quota exceeded")
    with patch("adapters.elevenlabs.ElevenLabs", return_value=client):
        with pytest.raises(ProviderLookupError, match="quota exceeded or rate-limited \\(429\\)"):
            ElevenLabsTtsAdapter().lookup({"text": "hus", "lang": "nb"})


def test_bad_credential_is_mapped_clearly(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_TOKEN", "fake-token")
    client = _mock_client(voices=[_mock_voice()])
    client.text_to_speech.convert.side_effect = _api_error(401, "invalid key")
    with patch("adapters.elevenlabs.ElevenLabs", return_value=client):
        with pytest.raises(ProviderLookupError, match="credential rejected \\(401\\)"):
            ElevenLabsTtsAdapter().lookup({"text": "hus", "lang": "nb"})


def test_other_api_error_includes_status_code(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_TOKEN", "fake-token")
    client = _mock_client(voices=[_mock_voice()])
    client.text_to_speech.convert.side_effect = _api_error(500, "server error")
    with patch("adapters.elevenlabs.ElevenLabs", return_value=client):
        with pytest.raises(ProviderLookupError, match="request failed \\(500\\)"):
            ElevenLabsTtsAdapter().lookup({"text": "hus", "lang": "nb"})
