"""Tests for the `kaikki` /inflections adapter (tasks 3.6-3.8) against the
real imported dump — requires `python -m scripts.import_kaikki` to have
been run against the test database first."""

from __future__ import annotations

import pytest

from adapters.kaikki import KaikkiAdapter


@pytest.fixture
def adapter():
    return KaikkiAdapter()


def test_inflected_surface_form_matches_headword_entry(adapter):
    # "fablet" is listed only inside "fable"'s forms[], never as its own
    # kaikki_entry.word — exercises the headword-OR-forms[] reverse lookup.
    result = adapter.lookup({"word": "fablet", "lang": "nb"})
    verb_candidates = [c for c in result["candidates"] if c["pos"] == "verb"]
    assert any(c["lemma"] == "fable" for c in verb_candidates)


def test_verb_excludes_imperative_and_passive_forms(adapter):
    result = adapter.lookup({"word": "fable", "lang": "nb"})
    fable = next(c for c in result["candidates"] if c["lemma"] == "fable" and c["pos"] == "verb")
    assert set(fable["paradigm"].keys()) <= {"infinitiv", "presens", "preteritum", "perfektum"}
    assert "fabl" not in fable["paradigm"].values()  # the imperative form
    assert "fables" not in fable["paradigm"].values()  # the passive form


def test_unknown_word_is_empty_not_error(adapter):
    result = adapter.lookup({"word": "qzxnotaword999", "lang": "nb"})
    assert result == {"candidates": []}
