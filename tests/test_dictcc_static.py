"""Tests for the `dictcc_static` adapter (tasks 3.4-3.5) against the real
imported data — requires `python -m scripts.import_dictcc_static` to have
been run against the test database first, same convention as
test_ordbank.py/test_kaikki.py."""

from __future__ import annotations

import pytest

from adapters.dictcc_static import DictccStaticAdapter, UnsupportedPairError


@pytest.fixture
def adapter():
    return DictccStaticAdapter()


def test_lookup_strips_grammar_annotation_from_query_but_not_answer(adapter):
    # "Haus" is stored as "Haus {n}" in the raw dump — the query must match
    # the bare lemma while the returned answer keeps its own annotation.
    result = adapter.lookup({"text": "Haus", "from": "de", "to": "en"})
    assert result["candidates"]
    assert all(c["text"] != "" for c in result["candidates"])
    assert any("context" in c for c in result["candidates"])


def test_lookup_both_directions_of_a_pair(adapter):
    forward = adapter.lookup({"text": "hus", "from": "nb", "to": "en"})
    assert any(c["text"].lower() == "house" for c in forward["candidates"])
    backward = adapter.lookup({"text": "house", "from": "en", "to": "nb"})
    assert backward["candidates"]


def test_unknown_word_returns_empty_candidates(adapter):
    result = adapter.lookup({"text": "qzxnotaword999", "from": "nb", "to": "en"})
    assert result == {"candidates": []}


def test_unsupported_pair_raises(adapter):
    with pytest.raises(UnsupportedPairError):
        adapter.lookup({"text": "hus", "from": "nb", "to": "fr"})
