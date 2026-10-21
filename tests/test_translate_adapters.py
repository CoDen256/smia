"""Tests for the /translations adapters (tasks 6.1-6.4), mocking HTTP
since live calls to these endpoints are currently unreliable from this
environment (Google IP-blocked, Bing's auth endpoint returning 404,
LibreTranslate's free public instances all down/key-gated — see each
adapter module's docstring). Mocked responses mirror hover-translate's
real captured shapes (google/types.ts, bing/types.ts)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from adapters.bing_translate import BingTranslateAdapter
from adapters.deepl import DeeplAdapter
from adapters.google_translate import GoogleTranslateAdapter
from adapters.libretranslate import LibreTranslateAdapter
from cache import ProviderLookupError


def _mock_response(json_data=None, text_data=None, status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.raise_for_status = MagicMock()
    if json_data is not None:
        resp.json.return_value = json_data
    if text_data is not None:
        resp.text = text_data
    return resp


def test_google_translate_parses_sentences_and_dict():
    fixture = {
        "src": "nb",
        "sentences": [{"orig": "hus", "trans": "house"}],
        "dict": [{"pos": "noun", "base_form": "hus", "terms": ["house", "building"], "entry": []}],
    }
    with patch("adapters.google_translate.requests.get", return_value=_mock_response(json_data=fixture)):
        result = GoogleTranslateAdapter().lookup({"text": "hus", "from": "nb", "to": "en"})
    assert result["text"] == "house"
    assert "noun: house, building" in result["context"]


def test_google_translate_omits_context_when_absent():
    fixture = {"src": "nb", "sentences": [{"orig": "hus", "trans": "house"}]}
    with patch("adapters.google_translate.requests.get", return_value=_mock_response(json_data=fixture)):
        result = GoogleTranslateAdapter().lookup({"text": "hus", "from": "nb", "to": "en"})
    assert result == {"text": "house"}


def test_bing_translate_parses_translation():
    fixture = [{"translations": [{"to": "en", "text": "house"}]}]
    with patch("adapters.bing_translate.requests.get", return_value=_mock_response(text_data="fake.jwt.token")), \
         patch("adapters.bing_translate.requests.post", return_value=_mock_response(json_data=fixture)):
        result = BingTranslateAdapter().lookup({"text": "hus", "from": "nb", "to": "en"})
    assert result == {"text": "house"}


def test_deepl_without_key_errors_clearly(monkeypatch):
    monkeypatch.delenv("DEEPL_API_KEY", raising=False)
    with pytest.raises(ProviderLookupError, match="DEEPL_API_KEY"):
        DeeplAdapter().lookup({"text": "hus", "from": "nb", "to": "en"})


def test_deepl_with_key_parses_translation(monkeypatch):
    monkeypatch.setenv("DEEPL_API_KEY", "fake-key")
    fixture = {"translations": [{"detected_source_language": "NB", "text": "house"}]}
    with patch("adapters.deepl.requests.post", return_value=_mock_response(json_data=fixture)):
        result = DeeplAdapter().lookup({"text": "hus", "from": "nb", "to": "en"})
    assert result == {"text": "house"}


def test_libretranslate_parses_translation():
    fixture = {"translatedText": "house"}
    with patch("adapters.libretranslate.requests.post", return_value=_mock_response(json_data=fixture)):
        result = LibreTranslateAdapter().lookup({"text": "hus", "from": "nb", "to": "en"})
    assert result == {"text": "house"}


def test_libretranslate_surfaces_server_error():
    fixture = {"error": "no key"}
    with patch("adapters.libretranslate.requests.post", return_value=_mock_response(json_data=fixture)):
        with pytest.raises(ProviderLookupError, match="no key"):
            LibreTranslateAdapter().lookup({"text": "hus", "from": "nb", "to": "en"})
