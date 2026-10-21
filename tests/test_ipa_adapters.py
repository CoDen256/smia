"""Tests for the local /ipa adapters (tasks 4.1-4.3, 4.5) against the
real imported data. `ordbokene` (task 4.4, a live network call) is
exercised in test_ordbokene.py instead, since it needs network access and
shouldn't block the rest of the suite if unavailable."""

from __future__ import annotations

from adapters.ipadict import IpaDictAdapter
from adapters.kaikki_ipa import KaikkiIpaAdapter
from adapters.nst import NstAdapter
from adapters.wikipron import WikipronAdapter


def test_nst_standard_and_dialect_candidates_are_deduplicated():
    result = NstAdapter().lookup({"text": "hus", "lang": "nb"})
    candidates = result["candidates"]
    assert sum(1 for c in candidates if c["variety"] == "standard") == 1
    varieties = [c["variety"] for c in candidates]
    assert len(varieties) == len(set(varieties))
    assert "eastern_spoken" in varieties
    assert "southwestern_written" in varieties


def test_nst_unknown_word_is_empty():
    result = NstAdapter().lookup({"text": "qzxnotaword999", "lang": "nb"})
    assert result == {"candidates": []}


def test_kaikki_ipa_candidate_has_phonemic():
    result = KaikkiIpaAdapter().lookup({"text": "fable", "lang": "nb"})
    assert result["candidates"]
    assert result["candidates"][0]["phonemic"] == "/fɑːblə/"


def test_ipadict_thin_lookup():
    result = IpaDictAdapter().lookup({"text": "abort", "lang": "nb"})
    assert result["candidates"] == [{"phonemic": "ɑˈbɔʈ"}]


def test_wikipron_multiple_candidates():
    result = WikipronAdapter().lookup({"text": "A", "lang": "nb"})
    phonemics = {c["phonemic"] for c in result["candidates"]}
    assert "a" in phonemics
    assert "ɑː" in phonemics
