"""Tests for the `kaikki` `/examples` adapter (examples-api tasks 5.6, 7.3,
7.10, 7.11) against the real imported dump — requires
`python -m scripts.import_kaikki` to have been run against the test
database first."""

from __future__ import annotations

import pytest

from adapters.kaikki_examples import KaikkiExamplesAdapter


@pytest.fixture
def adapter():
    return KaikkiExamplesAdapter()


def test_real_usage_example_is_kept(adapter):
    result = adapter.lookup({"text": "fable", "lang": "nb", "limit": 5})
    assert any(c["text"] == "fable om suksess" for c in result["candidates"])


def test_morphology_fragment_is_excluded(adapter):
    result = adapter.lookup({"text": "a-", "lang": "nb", "limit": 5})
    assert all("→" not in c["text"] and " + " not in c["text"] for c in result["candidates"])


def test_no_candidate_carries_a_translation_field(adapter):
    result = adapter.lookup({"text": "fable", "lang": "nb", "limit": 5})
    for candidate in result["candidates"]:
        assert "translation" not in candidate
        assert "english" not in candidate
        assert set(candidate.keys()) == {"text"}


def test_unknown_word_is_empty_not_error(adapter):
    result = adapter.lookup({"text": "qzxnotaword999", "lang": "nb", "limit": 3})
    assert result == {"candidates": []}


def test_source_order_not_length_ranked(adapter):
    # "ab" has several examples of increasing length in the dump's own
    # order; a dictionary provider must preserve that order rather than
    # re-sorting shortest-first.
    result = adapter.lookup({"text": "ab", "lang": "nb", "limit": 10})
    texts = [c["text"] for c in result["candidates"]]
    assert texts  # sanity: "ab" really has examples in the dump
    lengths = [len(t) for t in texts]
    assert lengths != sorted(lengths)
