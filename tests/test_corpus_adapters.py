"""Integration tests for the `tatoeba`/`leipzig` `/examples` adapters
against the real imported corpora (examples-api tasks 7.4-7.8) — requires
`python -m scripts.import_tatoeba`/`import_leipzig` to have been run
against the test database first."""

from __future__ import annotations

from sqlalchemy import text

from adapters.leipzig import LeipzigAdapter
from adapters.tatoeba import TatoebaAdapter
from adapters._form_expansion import surface_forms, to_tsquery_or
from db.session import session_scope


def _match_count(db, corpora: list[str], word: str) -> int:
    forms = surface_forms(db, word)
    tsquery = to_tsquery_or(forms)
    return db.execute(
        text(
            "SELECT count(*) FROM corpus_sentence WHERE corpus = ANY(:c) "
            "AND tsv @@ to_tsquery('simple', :q)"
        ),
        {"c": corpora, "q": tsquery},
    ).scalar()


def test_regular_inflected_forms_are_matched():
    result = LeipzigAdapter().lookup({"text": "kalv", "limit": 10})
    assert result["candidates"]


def test_irregular_plural_is_matched():
    # "bøker" is an umlaut plural of "bok" — only findable via ordbank
    # form expansion against a `simple`-config index (design D3). Checked
    # against the raw match count, not the top-ranked output, since
    # ranking/limit could otherwise cut the specific umlaut-plural
    # sentence out of a small top-N without that meaning the match failed.
    with session_scope() as db:
        assert _match_count(db, ["web_2020", "news_2013", "wikipedia_2014"], "bok") > 0


def test_stopword_listed_preterite_is_matched():
    result = TatoebaAdapter().lookup({"text": "komme", "limit": 10})
    assert result["candidates"]


def test_word_outside_ordbank_still_answers():
    # a nonsense token not in ordbank_fullform falls back to itself
    # (surface-form-only match) rather than erroring.
    result = LeipzigAdapter().lookup({"text": "qzxnotaword999", "limit": 3})
    assert result == {"candidates": []}


def test_no_candidate_carries_a_translation_field():
    result = TatoebaAdapter().lookup({"text": "kalv", "limit": 5})
    for candidate in result["candidates"]:
        assert "translation" not in candidate
        assert set(candidate.keys()) <= {"text", "source"}


def test_leipzig_registered_once_spans_multiple_corpora():
    from registry import registry

    assert registry.providers_for("examples").count("leipzig") == 1
    result = LeipzigAdapter().lookup({"text": "kalv", "limit": 10})
    sources = {c["source"] for c in result["candidates"]}
    assert sources  # at least one corpus answered
    assert sources <= {"web_2020", "news_2013", "wikipedia_2014"}


def test_leipzig_can_return_candidates_from_more_than_one_corpus():
    result = LeipzigAdapter().lookup({"text": "kalv", "limit": 10})
    sources = {c["source"] for c in result["candidates"]}
    assert len(sources) >= 2
