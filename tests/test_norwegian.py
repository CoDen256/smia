"""Tests for the shared `norwegian.py` query-preparation module (tasks
2.1-2.7), against the rules fixed in design.md D1-D3, D8."""

from __future__ import annotations

from norwegian import query_variants, tokenize


def test_single_lowercase_word_yields_one_variant():
    assert query_variants("kalv") == ["kalv"]


def test_each_gender_article_and_infinitive_marker_yield_two_variants():
    assert query_variants("en kalv") == ["en kalv", "kalv"]
    assert query_variants("ei bok") == ["ei bok", "bok"]
    assert query_variants("et hus") == ["et hus", "hus"]
    assert query_variants("å komme") == ["å komme", "komme"]


def test_bare_article_or_marker_is_not_stripped():
    assert query_variants("å") == ["å"]
    assert query_variants("en") == ["en"]


def test_en_aa_strips_exactly_once():
    assert query_variants("en å") == ["en å", "å"]


def test_unrecognised_first_token_is_unchanged():
    assert query_variants("god morgen") == ["god morgen"]


def test_casing_variants_in_exact_order():
    assert query_variants("Kalv") == ["Kalv", "kalv"]
    assert query_variants("En Kalv") == ["En Kalv", "en kalv", "Kalv", "kalv"]


def test_tokenize_two_word_phrase():
    assert tokenize("god morgen") == ["god", "morgen"]


def test_tokenize_keeps_hyphenated_compound_whole():
    assert tokenize("sju-åtte") == ["sju-åtte"]


def test_tokenize_drops_digit_only_tokens():
    assert tokenize("klokka 5") == ["klokka"]


def test_tokenize_keeps_reflexive_seg():
    assert tokenize("anstrenge seg") == ["anstrenge", "seg"]


def test_tokenize_strips_trailing_punctuation():
    assert tokenize("god morgen!") == ["god", "morgen"]


def test_tokenize_does_not_apply_prefix_rule():
    assert tokenize("en kalv") == ["en", "kalv"]
