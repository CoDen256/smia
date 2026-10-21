"""Tests for the `ordbank` /inflections adapter (tasks 3.2-3.5) against the
real imported data — requires `python -m scripts.import_ordbank` to have
been run against the test database first (CI/dev setup step, not something
these tests do themselves, since the import is a slow one-shot job)."""

from __future__ import annotations

import pytest

from adapters.ordbank import OrdbankAdapter


@pytest.fixture
def adapter():
    return OrdbankAdapter()


def test_ambiguous_word_returns_multiple_candidates(adapter):
    result = adapter.lookup({"word": "skinner", "lang": "nb"})
    candidates = result["candidates"]
    assert len(candidates) >= 2
    poses = {c["pos"] for c in candidates}
    assert "verb" in poses
    assert "substantiv" in poses


def test_verb_candidate_shape(adapter):
    result = adapter.lookup({"word": "skinner", "lang": "nb"})
    verb_candidates = [c for c in result["candidates"] if c["pos"] == "verb"]
    assert verb_candidates
    for c in verb_candidates:
        assert set(c["paradigm"].keys()) == {"infinitiv", "presens", "preteritum", "perfektum"}


def test_noun_candidate_shape(adapter):
    result = adapter.lookup({"word": "hus", "lang": "nb"})
    noun_candidates = [c for c in result["candidates"] if c["pos"] == "substantiv"]
    assert noun_candidates
    for c in noun_candidates:
        assert set(c["paradigm"].keys()) == {"article", "sg_indef", "sg_def", "pl_indef", "pl_def"}


def test_degree_inflecting_adverb_shape(adapter):
    result = adapter.lookup({"word": "ofte", "lang": "nb"})
    adverb_candidates = [c for c in result["candidates"] if c["pos"] == "adverb"]
    assert adverb_candidates
    assert set(adverb_candidates[0]["paradigm"].keys()) == {"form", "komparativ", "superlativ"}


def test_unknown_word_is_empty_not_error(adapter):
    result = adapter.lookup({"word": "qzxnotaword999", "lang": "nb"})
    assert result == {"candidates": []}
