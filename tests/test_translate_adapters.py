"""Tests for the /translations adapters (tasks 6.1-6.4; updated by
`provider-client-libraries` for the DeepL/Bing client-library swap and the
libretranslate removal). Google still mocks raw HTTP (deliberately kept on
it, see google_translate.py's docstring); DeepL mocks the `deepl` package's
`Translator`; Bing mocks the `translators` package's `translate_text`.
Google/Bing's live calls were unreliable from this environment when first
implemented (Google IP-blocked, Bing's old hand-rolled auth endpoint
404ing) — see each adapter module's docstring. Mocked responses mirror
hover-translate's real captured shapes (google/types.ts) where applicable."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from adapters.bing_translate import BingTranslateAdapter
from adapters.deepl import DeeplAdapter
from adapters.google_translate import GoogleTranslateAdapter
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
    with patch("adapters.bing_translate.translators.translate_text", return_value="house") as mock_translate:
        result = BingTranslateAdapter().lookup({"text": "hus", "from": "nb", "to": "en"})
    assert result == {"text": "house"}
    _, kwargs = mock_translate.call_args
    assert kwargs["translator"] == "bing"
    assert kwargs["from_language"] == "nb"
    assert kwargs["to_language"] == "en"


def test_bing_translate_surfaces_client_error():
    with patch("adapters.bing_translate.translators.translate_text", side_effect=RuntimeError("boom")):
        with pytest.raises(ProviderLookupError, match="boom"):
            BingTranslateAdapter().lookup({"text": "hus", "from": "nb", "to": "en"})


def test_deepl_without_key_errors_clearly(monkeypatch):
    monkeypatch.delenv("DEEPL_TOKEN", raising=False)
    with pytest.raises(ProviderLookupError, match="DEEPL_TOKEN"):
        DeeplAdapter().lookup({"text": "hus", "from": "nb", "to": "en"})


def test_deepl_with_key_parses_translation(monkeypatch):
    monkeypatch.setenv("DEEPL_TOKEN", "fake-key")
    mock_translator = MagicMock()
    mock_translator.translate_text.return_value = MagicMock(text="house")
    with patch("adapters.deepl.deepl.Translator", return_value=mock_translator):
        result = DeeplAdapter().lookup({"text": "hus", "from": "nb", "to": "en"})
    assert result == {"text": "house"}
    _, kwargs = mock_translator.translate_text.call_args
    # bare "EN" is deprecated as a DeepL target_lang (confirmed live) —
    # the adapter must disambiguate it, not pass it through as-is.
    assert kwargs["target_lang"] == "EN-US"
    assert kwargs["source_lang"] == "NB"


def test_deepl_surfaces_client_exception(monkeypatch):
    import deepl as deepl_pkg

    monkeypatch.setenv("DEEPL_TOKEN", "fake-key")
    mock_translator = MagicMock()
    mock_translator.translate_text.side_effect = deepl_pkg.AuthorizationException("bad key")
    with patch("adapters.deepl.deepl.Translator", return_value=mock_translator):
        with pytest.raises(ProviderLookupError, match="bad key"):
            DeeplAdapter().lookup({"text": "hus", "from": "nb", "to": "en"})
