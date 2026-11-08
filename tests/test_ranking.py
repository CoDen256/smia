"""Unit tests for `adapters/_ranking.py` (examples-api tasks 4.4-4.7, 7.6,
7.7) — pure-Python, no database needed."""

from __future__ import annotations

from adapters._ranking import rank_candidates


def test_short_complete_sentence_outranks_long_one():
    rows = [
        (1, "news_2013", "Ælvespeilet i Porsgrunn har adoptert disse to kalvene som ble født i vinter.", 12),
        (2, "news_2013", "Kalven på bildet er to timer gammel.", 7),
    ]
    result = rank_candidates(rows, "kalv", limit=2)
    assert result[0]["text"] == "Kalven på bildet er to timer gammel."


def test_timestamp_prefixed_sentence_ranks_below_clean_one():
    rows = [
        (1, "news_2013", "01 mai 2013 10:38 Lettvin blir tungt for mange å forstå nå.", 9),
        (2, "news_2013", "Kalven ble født i natt.", 5),
    ]
    result = rank_candidates(rows, "kalv", limit=2)
    assert result[0]["text"] == "Kalven ble født i natt."


def test_multi_sentence_line_is_excluded():
    rows = [
        (1, "wikipedia_2014", "Kalven ble født i mai. Bonden var glad.", 8),
    ]
    assert rank_candidates(rows, "kalv", limit=10) == []


def test_url_bearing_line_is_excluded():
    rows = [
        (1, "web_2020", "Se mer om kalven på https://example.com/kalv her.", 8),
    ]
    assert rank_candidates(rows, "kalv", limit=10) == []


def test_no_alphabetical_bias_in_tie_breaking():
    # Equal-rank, equal-length candidates whose text happens to be
    # alphabetically ordered (A, B, C, D, E, ...) by row order/id — a
    # row-order tie-break would always return the "A..." set first.
    letters = "ABCDEFGHIJ"
    rows = [(i, "web_2020", f"{letter} kalv er fin i dag her.", 6) for i, letter in enumerate(letters)]
    result = rank_candidates(rows, "kalv", limit=3)
    initials = {c["text"][0] for c in result}
    assert initials != {"A"}


def test_ranking_is_reproducible():
    rows = [(i, "web_2020", f"Kalv nummer {i} er fin i dag.", 6) for i in range(20)]
    first = rank_candidates(rows, "kalv", limit=5)
    second = rank_candidates(rows, "kalv", limit=5)
    assert first == second


def test_limit_is_respected():
    rows = [(i, "tatoeba", f"Kalven løper fort i dag {i}.", 5) for i in range(10)]
    result = rank_candidates(rows, "kalv", limit=3)
    assert len(result) == 3
