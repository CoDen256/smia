"""Tests for `/ipa`'s whole-phrase-then-split flow (routes/ipa.py, tasks
4.1-6.4). Uses the real app and real imported adapter data (`ipadict`,
`nst`) wherever possible, same convention as the other adapter test
files, with small throwaway mock adapters registered under the real `ipa`
kind only where a real-data gap can't be found deterministically (the
"no fan-out" and "forceRefresh re-invokes" tests)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from sqlalchemy import text as sql_text

from app import app as real_app
from db.session import get_sessionmaker
from registry import registry

AUTH = {"Authorization": "Bearer test-token"}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SMIA_AUTH_TOKEN", "test-token")
    return real_app.test_client()


def _lookup_cache_row_count() -> int:
    Session = get_sessionmaker()
    with Session() as db:
        return db.execute(sql_text("SELECT count(*) FROM lookup_cache")).scalar()


# ---------------------------------------------------------------------------
# 4. Phrase branch
# ---------------------------------------------------------------------------

def test_single_word_request_is_unchanged_apart_from_mode(client):
    resp = client.post("/ipa", json={"text": "kalv", "lang": "nb", "provider": "ipadict"}, headers=AUTH)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body == {"provider": "ipadict", "mode": "phrase", "candidates": [{"ipa": "kɑlʋ"}]}
    assert "tokens" not in body


def test_single_word_with_no_entry_returns_empty_phrase_and_no_split(client):
    before = _lookup_cache_row_count()
    resp = client.post(
        "/ipa", json={"text": "qzxnotaword999", "lang": "nb", "provider": "ipadict"}, headers=AUTH
    )
    assert resp.status_code == 200
    assert resp.get_json() == {"provider": "ipadict", "mode": "phrase", "candidates": []}
    # A single token can never split — exactly one cache row (the phrase
    # attempt, which is also the top-level resource since they share an
    # input) is created, not two.
    assert _lookup_cache_row_count() == before + 1


def test_real_multiword_entry_resolves_as_phrase_with_no_split(client):
    resp = client.post("/ipa", json={"text": "av og til", "lang": "nb", "provider": "ipadict"}, headers=AUTH)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body == {"provider": "ipadict", "mode": "phrase", "candidates": [{"ipa": "ɑʋɔtɪl"}]}


def test_provider_error_on_phrase_attempt_yields_502_with_no_split():
    class Boom:
        def lookup(self, input_dict):
            raise __import__("cache").ProviderLookupError("boom")

    boom = Boom()
    registry.register("ipa", "boomy", boom)
    import os
    os.environ["SMIA_AUTH_TOKEN"] = "test-token"
    client = real_app.test_client()
    resp = client.post("/ipa", json={"text": "god morgen", "lang": "nb", "provider": "boomy"}, headers=AUTH)
    assert resp.status_code == 502


def test_citation_form_resolves_via_phrase_branch_not_split(client):
    resp = client.post("/ipa", json={"text": "en kalv", "lang": "nb", "provider": "ipadict"}, headers=AUTH)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["mode"] == "phrase"
    assert body["candidates"] == [{"ipa": "kɑlʋ"}]


# ---------------------------------------------------------------------------
# 5. Split branch
# ---------------------------------------------------------------------------

def test_two_word_phrase_both_known_returns_per_word_in_order(client):
    resp = client.post("/ipa", json={"text": "god morgen", "lang": "nb", "provider": "ipadict"}, headers=AUTH)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["mode"] == "per_word"
    assert [t["text"] for t in body["tokens"]] == ["god", "morgen"]
    assert all(t["candidates"] for t in body["tokens"])


def test_one_unknown_word_returns_empty_token_in_position_with_200(client):
    resp = client.post(
        "/ipa", json={"text": "god qzxnotaword999", "lang": "nb", "provider": "ipadict"}, headers=AUTH
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["mode"] == "per_word"
    assert body["tokens"] == [
        {"text": "god", "candidates": [{"ipa": "guː"}]},
        {"text": "qzxnotaword999", "candidates": []},
    ]


def test_no_known_word_returns_all_empty_tokens_with_200(client):
    resp = client.post(
        "/ipa",
        json={"text": "qzxnotaword999 qzxnotaword998", "lang": "nb", "provider": "ipadict"},
        headers=AUTH,
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["mode"] == "per_word"
    assert all(t["candidates"] == [] for t in body["tokens"])


def test_joined_present_when_every_token_has_exactly_one_candidate(client):
    resp = client.post("/ipa", json={"text": "god morgen", "lang": "nb", "provider": "ipadict"}, headers=AUTH)
    body = resp.get_json()
    assert body["joined"] == "guː ˈmoːɔɳ"


def test_joined_absent_when_a_token_is_missing(client):
    resp = client.post(
        "/ipa", json={"text": "god qzxnotaword999", "lang": "nb", "provider": "ipadict"}, headers=AUTH
    )
    assert "joined" not in resp.get_json()


def test_joined_absent_when_a_token_is_ambiguous(client):
    # nst returns multiple dialect candidates per word, so a 2-word phrase
    # it has to split has an ambiguous token and no `joined`.
    resp = client.post("/ipa", json={"text": "god morgen", "lang": "nb", "provider": "nst"}, headers=AUTH)
    body = resp.get_json()
    assert body["mode"] == "per_word"
    assert "joined" not in body


def test_dialect_candidates_survive_per_token_against_multi_dialect_provider(client):
    resp = client.post("/ipa", json={"text": "god morgen", "lang": "nb", "provider": "nst"}, headers=AUTH)
    body = resp.get_json()
    for token in body["tokens"]:
        varieties = {c["variety"] for c in token["candidates"]}
        assert len(varieties) > 1


def test_hyphenated_compound_is_one_token(client):
    resp = client.post("/ipa", json={"text": "ja sju-åtte", "lang": "nb", "provider": "ipadict"}, headers=AUTH)
    body = resp.get_json()
    assert [t["text"] for t in body["tokens"]] == ["ja", "sju-åtte"]


def test_digit_only_token_produces_no_token_entry(client):
    # Three whitespace-separated words so the digit-only one still leaves
    # 2+ real tokens behind — tokenize() drops it before the split, so no
    # split-vs-single-token ambiguity (task 2.5) kicks in.
    resp = client.post("/ipa", json={"text": "klokka er 5", "lang": "nb", "provider": "ipadict"}, headers=AUTH)
    body = resp.get_json()
    assert [t["text"] for t in body["tokens"]] == ["klokka", "er"]


def test_reflexive_seg_is_looked_up_on_its_own(client):
    # ipadict has "anstrenge seg" as a whole-phrase entry, which would mask
    # the split — use nst, which has no multi-word entries at all (task
    # 1.2 measurement), to force the split and exercise `seg` as its own
    # token.
    resp = client.post("/ipa", json={"text": "anstrenge seg", "lang": "nb", "provider": "nst"}, headers=AUTH)
    body = resp.get_json()
    assert body["mode"] == "per_word"
    seg = next(t for t in body["tokens"] if t["text"] == "seg")
    assert seg["candidates"]


def test_gap_is_not_filled_by_another_provider():
    only_empty = MagicMock()
    only_empty.lookup.return_value = {"candidates": []}
    has_it = MagicMock()
    has_it.lookup.return_value = {"candidates": [{"ipa": "x"}]}
    registry.register("ipa", "emptyprovider", only_empty)
    registry.register("ipa", "hasitprovider", has_it)

    import os
    os.environ["SMIA_AUTH_TOKEN"] = "test-token"
    client = real_app.test_client()
    resp = client.post(
        "/ipa", json={"text": "foo bar", "lang": "nb", "provider": "emptyprovider"}, headers=AUTH
    )
    body = resp.get_json()
    assert body["mode"] == "per_word"
    assert all(t["candidates"] == [] for t in body["tokens"])
    has_it.lookup.assert_not_called()


# ---------------------------------------------------------------------------
# 6. Caching
# ---------------------------------------------------------------------------

def test_token_input_is_independently_retrievable_from_cache(client):
    client.post("/ipa", json={"text": "god morgen", "lang": "nb", "provider": "ipadict"}, headers=AUTH)
    before = _lookup_cache_row_count()
    resp = client.post("/ipa", json={"text": "god", "lang": "nb", "provider": "ipadict"}, headers=AUTH)
    assert resp.status_code == 200
    assert resp.get_json()["candidates"] == [{"ipa": "guː"}]
    # Served from the sub-lookup's existing row — no new row created.
    assert _lookup_cache_row_count() == before


def test_location_and_get_round_trip_the_assembled_per_word_payload(client):
    resp = client.post("/ipa", json={"text": "god morgen", "lang": "nb", "provider": "ipadict"}, headers=AUTH)
    rid = resp.headers["Location"].rsplit("/", 1)[-1]
    get_resp = client.get(f"/ipa/{rid}", headers=AUTH)
    assert get_resp.status_code == 200
    assert get_resp.get_json() == resp.get_json()
    assert get_resp.get_json()["mode"] == "per_word"


def test_force_refresh_reinvokes_provider_for_every_token():
    calls = []

    class Counting:
        def lookup(self, input_dict):
            calls.append(input_dict["text"])
            return {"candidates": []}

    registry.register("ipa", "counting", Counting())
    import os
    os.environ["SMIA_AUTH_TOKEN"] = "test-token"
    client = real_app.test_client()

    client.post("/ipa", json={"text": "foo bar", "lang": "nb", "provider": "counting"}, headers=AUTH)
    first_call_count = len(calls)
    assert first_call_count > 0

    client.post(
        "/ipa",
        json={"text": "foo bar", "lang": "nb", "provider": "counting", "forceRefresh": True},
        headers=AUTH,
    )
    assert len(calls) > first_call_count


def test_n_plus_one_cache_rows_after_one_phrase_request(client):
    before = _lookup_cache_row_count()
    client.post("/ipa", json={"text": "god morgen", "lang": "nb", "provider": "ipadict"}, headers=AUTH)
    after = _lookup_cache_row_count()
    # query_variants("god morgen") == ["god morgen"] (no stripping possible
    # on an unrecognised first token, no case difference), so the single
    # phrase-attempt row and the top-level assembled row share one
    # resource id (same input) -> 1 shared row + 2 token rows = N+1 for
    # N=2 tokens.
    assert after - before == 3


def test_pre_change_cached_row_with_no_mode_key_is_still_served(client):
    # Simulate a row written before this change: a plain {provider,
    # candidates} payload with no `mode` key, same shape run_lookup always
    # wrote for /ipa pre-multiword.
    from cache import input_hash, resource_id
    from db.models import LookupCache

    Session = get_sessionmaker()
    with Session() as db:
        ihash = input_hash({"text": "legacyword", "lang": "nb"})
        rid = resource_id("ipa", "ipadict", ihash)
        db.add(LookupCache(
            id=rid, kind="ipa", provider="ipadict", input_hash=ihash,
            payload={"provider": "ipadict", "candidates": [{"ipa": "legacy"}]},
        ))
        db.commit()

    resp = client.get(f"/ipa/{rid}", headers=AUTH)
    assert resp.status_code == 200
    assert resp.get_json() == {"provider": "ipadict", "candidates": [{"ipa": "legacy"}]}
