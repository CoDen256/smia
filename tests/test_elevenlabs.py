"""Tests for the `elevenlabs` /stt adapter (add-elevenlabs-provider tasks
2.1-2.4), mocking the official `elevenlabs` SDK client — no live
`ELEVENLABS_TOKEN` was available in this environment to test against the
real API (see adapters/elevenlabs.py's docstring; task 3.1 needs to be run
by whoever has the real token).

The `/tts` registration was removed (see the module docstring): every
voice this adapter could reach is a shared/library voice, and those 402
`paid_plan_required` on free-tier accounts — a permanent block on this
account tier, not a configured-but-sometimes-failing provider."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from adapters.elevenlabs import ElevenLabsSttAdapter
from cache import ProviderLookupError


def _mock_client(stt_text=None):
    client = MagicMock()
    client.speech_to_text.convert.return_value = SimpleNamespace(text=stt_text or "")
    return client


def test_stt_without_token_errors_clearly(monkeypatch):
    monkeypatch.delenv("ELEVENLABS_TOKEN", raising=False)
    with pytest.raises(ProviderLookupError, match="ELEVENLABS_TOKEN"):
        ElevenLabsSttAdapter().lookup({"audio_b64": "ZmFrZQ=="})


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
    client = _mock_client()
    client.speech_to_text.convert.side_effect = _api_error(429, "quota exceeded")
    with patch("adapters.elevenlabs.ElevenLabs", return_value=client):
        with pytest.raises(ProviderLookupError, match="quota exceeded or rate-limited \\(429\\)"):
            ElevenLabsSttAdapter().lookup({"audio_b64": "ZmFrZQ=="})


def test_bad_credential_is_mapped_clearly(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_TOKEN", "fake-token")
    client = _mock_client()
    client.speech_to_text.convert.side_effect = _api_error(401, "invalid key")
    with patch("adapters.elevenlabs.ElevenLabs", return_value=client):
        with pytest.raises(ProviderLookupError, match="authorization error \\(401"):
            ElevenLabsSttAdapter().lookup({"audio_b64": "ZmFrZQ=="})


def test_payment_required_is_mapped_clearly(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_TOKEN", "fake-token")
    client = _mock_client()
    client.speech_to_text.convert.side_effect = _api_error(402, "paid_plan_required")
    with patch("adapters.elevenlabs.ElevenLabs", return_value=client):
        with pytest.raises(ProviderLookupError, match="requires a paid plan"):
            ElevenLabsSttAdapter().lookup({"audio_b64": "ZmFrZQ=="})


def test_other_api_error_includes_status_code(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_TOKEN", "fake-token")
    client = _mock_client()
    client.speech_to_text.convert.side_effect = _api_error(500, "server error")
    with patch("adapters.elevenlabs.ElevenLabs", return_value=client):
        with pytest.raises(ProviderLookupError, match="request failed \\(500\\)"):
            ElevenLabsSttAdapter().lookup({"audio_b64": "ZmFrZQ=="})


def test_elevenlabs_tts_is_not_registered():
    from registry import registry

    assert "elevenlabs" not in registry.providers_for("tts")
