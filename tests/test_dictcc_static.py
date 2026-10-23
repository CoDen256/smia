"""Tests for the `dictcc_static` adapter (tasks 3.4-3.5) against the real
imported data — requires `python -m scripts.import_dictcc_static` to have
been run against the test database first, same convention as
test_ordbank.py/test_kaikki.py."""

from __future__ import annotations

import pytest

from adapters.dictcc_static import DictccStaticAdapter, UnsupportedPairError
from scripts.import_dictcc_static import _clean


@pytest.fixture
def adapter():
    return DictccStaticAdapter()


def test_clean_strips_leading_infinitive_marker_for_verbs():
    assert _clean("å komme") == "komme"
    assert _clean("å komme over") == "komme over"


def test_clean_strips_trailing_annotation_and_leading_marker_together():
    assert _clean("å være {verb} [aux.]") == "være"


def test_clean_leaves_non_verb_terms_unaffected():
    assert _clean("Haus {n}") == "Haus"
    assert _clean("hus") == "hus"


def test_lookup_finds_verb_by_bare_infinitive_without_marker(adapter):
    # "komme" is stored as "å komme" in the raw dump (task 4) — the query
    # must match the bare infinitive, same as dictcc_api already does.
    result = adapter.lookup({"text": "komme", "from": "nb", "to": "en"})
    assert any("come" in c["text"].lower() for c in result["candidates"])


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
