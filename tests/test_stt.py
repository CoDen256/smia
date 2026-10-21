"""Tests for /stt (task 7.2): multipart audio body, provider required even
with only one configured (D17 override of the usual lookup-cache default),
and the hf_whisper adapter (task 7.1, mocked HTTP)."""

from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

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


def test_missing_provider_is_required_even_with_one_configured(client, monkeypatch):
    monkeypatch.setenv("SMIA_AUTH_TOKEN", "test-token")
    data = {"audio": (io.BytesIO(b"fake-wav-bytes"), "clip.wav")}
    resp = client.post("/stt", data=data, headers=AUTH, content_type="multipart/form-data")
    assert resp.status_code == 400
    assert resp.get_json()["available"] == ["hf_whisper"]


def test_hf_whisper_without_token_errors_clearly(monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    with pytest.raises(ProviderLookupError, match="HF_TOKEN"):
        HfWhisperAdapter().lookup({"audio_b64": "ZmFrZQ==", "lang": None})


def test_hf_whisper_parses_text(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "fake-token")
    resp = MagicMock()
    resp.ok = True
    resp.content = b'{"text": "hello world"}'
    resp.json.return_value = {"text": "hello world"}
    with patch("adapters.hf_whisper.requests.post", return_value=resp):
        result = HfWhisperAdapter().lookup({"audio_b64": "ZmFrZQ==", "lang": None})
    assert result == {"text": "hello world"}


def test_hf_whisper_surfaces_model_loading_error(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "fake-token")
    resp = MagicMock()
    resp.ok = False
    resp.content = b'{"error": "Model is loading", "estimated_time": 15.2}'
    resp.json.return_value = {"error": "Model is loading", "estimated_time": 15.2}
    with patch("adapters.hf_whisper.requests.post", return_value=resp):
        with pytest.raises(ProviderLookupError, match="loading"):
            HfWhisperAdapter().lookup({"audio_b64": "ZmFrZQ==", "lang": None})
