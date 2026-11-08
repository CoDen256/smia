"""Tests for `adapters/_form_expansion.py` against the real imported
`ordbank_fullform` table (examples-api tasks 3.1-3.3, 7.4, 7.5)."""

from __future__ import annotations

from db.session import session_scope
from adapters._form_expansion import surface_forms, to_tsquery_or


def test_irregular_umlaut_plural_is_included():
    with session_scope() as db:
        forms = surface_forms(db, "bok")
    assert "bøker" in forms


def test_stopword_listed_preterite_is_included():
    with session_scope() as db:
        forms = surface_forms(db, "komme")
    assert "kom" in forms


def test_vaere_expands_to_var():
    with session_scope() as db:
        forms = surface_forms(db, "være")
    assert "var" in forms


def test_word_outside_ordbank_falls_back_to_itself():
    with session_scope() as db:
        forms = surface_forms(db, "qzxnotaword999")
    assert forms == ["qzxnotaword999"]


def test_unrelated_similar_word_is_not_a_form_of_kalv():
    with session_scope() as db:
        forms = surface_forms(db, "kalv")
    assert "kalkun" not in forms


def test_to_tsquery_or_escapes_embedded_quote():
    query = to_tsquery_or(["bror's", "bok"])
    assert "bror''s" in query
    assert query.count("|") == 1
