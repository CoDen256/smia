"""Tests for /stt (task 7.2): multipart audio body, provider required
regardless of how many are configured (D17), and the hf_whisper adapter
(task 7.1, mocking `huggingface_hub`'s `InferenceClient` per
`provider-client-libraries` — not raw HTTP). `/stt` now has two providers
(`hf_whisper`, `elevenlabs` — see tests/test_elevenlabs.py for the
latter's own tests), so the missing-provider test only asserts both names
appear in `available`, not that `hf_whisper` is the sole option."""

from __future__ import annotations

import io
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from huggingface_hub.errors import HfHubHTTPError

from adapters.hf_whisper import HfWhisperAdapter
from app import app as real_app
from cache import ProviderLookupError


@pytest.fixture
def client():
    return real_app.test_client()


AUTH = {"Authorization": "Bearer test-token"}


def test_missing_audio_is_400(client, monkeypatch):
    monkeypatch.setenv("SMIA_AUTH_TOKEN", "test-token")
    resp = client.post("/stt", data={}, headers=AUTH, content_type="multipart/form-data")
    assert resp.status_code == 400


def test_missing_provider_is_required(client, monkeypatch):
    monkeypatch.setenv("SMIA_AUTH_TOKEN", "test-token")
    # Both providers are dynamically unregistered from `available` when
    # their token isn't configured (see registry.py's `available=`) — set
    # both so this test exercises the "provider required" response, not
    # token-driven availability filtering (covered separately).
    monkeypatch.setenv("HF_TOKEN", "fake-token")
    monkeypatch.setenv("ELEVENLABS_TOKEN", "fake-token")
    data = {"audio": (io.BytesIO(b"fake-wav-bytes"), "clip.wav")}
    resp = client.post("/stt", data=data, headers=AUTH, content_type="multipart/form-data")
    assert resp.status_code == 400
    assert set(resp.get_json()["available"]) == {"hf_whisper", "elevenlabs"}


def test_hf_whisper_without_token_errors_clearly(monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    with pytest.raises(ProviderLookupError, match="HF_TOKEN"):
        HfWhisperAdapter().lookup({"audio_b64": "ZmFrZQ==", "lang": None})


def test_hf_whisper_parses_text(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "fake-token")
    mock_client = MagicMock()
    mock_client.automatic_speech_recognition.return_value = SimpleNamespace(text="hello world")
    with patch("adapters.hf_whisper.InferenceClient", return_value=mock_client):
        result = HfWhisperAdapter().lookup({"audio_b64": "ZmFrZQ==", "lang": None})
    assert result == {"text": "hello world"}


def test_hf_whisper_passes_language_via_extra_body(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "fake-token")
    mock_client = MagicMock()
    mock_client.automatic_speech_recognition.return_value = SimpleNamespace(text="hallo")
    with patch("adapters.hf_whisper.InferenceClient", return_value=mock_client):
        HfWhisperAdapter().lookup({"audio_b64": "ZmFrZQ==", "lang": "de"})
    _, kwargs = mock_client.automatic_speech_recognition.call_args
    assert kwargs["extra_body"] == {"generate_kwargs": {"language": "de", "task": "transcribe"}}


def test_hf_whisper_surfaces_model_loading_error(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "fake-token")
    mock_client = MagicMock()
    mock_client.automatic_speech_recognition.side_effect = HfHubHTTPError(
        "503 error", response=MagicMock(), server_message="Model is loading (~15s)"
    )
    with patch("adapters.hf_whisper.InferenceClient", return_value=mock_client):
        with pytest.raises(ProviderLookupError, match="loading"):
            HfWhisperAdapter().lookup({"audio_b64": "ZmFrZQ==", "lang": None})
