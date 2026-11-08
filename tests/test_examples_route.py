"""Contract tests for `POST /examples` / `GET /examples/{id}` (examples-api
tasks 7.1, 7.2, 7.12) against the real `app`, registering a throwaway fake
provider for deterministic candidate counts."""

from __future__ import annotations

import pytest

from app import app as real_app, _extract_examples_input
from registry import registry


def _client():
    return real_app.test_client()


AUTH = {"Authorization": "Bearer test-token"}


class _FakeAdapter:
    def lookup(self, input_dict: dict) -> dict:
        limit = input_dict["limit"]
        return {"candidates": [{"text": f"example {i}"} for i in range(limit)]}


@pytest.fixture
def fake_provider():
    registry.register("examples", "faketest", _FakeAdapter())
    return "faketest"


def test_extract_input_defaults_limit_to_3():
    assert _extract_examples_input({"text": "kalv"}) == {"text": "kalv", "lang": "nb", "limit": 3}


def test_extract_input_clamps_limit_below_1():
    assert _extract_examples_input({"text": "kalv", "limit": 0})["limit"] == 1


def test_extract_input_clamps_limit_above_10():
    assert _extract_examples_input({"text": "kalv", "limit": 999})["limit"] == 10


def test_extract_input_rejects_non_nb_lang():
    with pytest.raises(ValueError):
        _extract_examples_input({"text": "kalv", "lang": "en"})


def test_extract_input_requires_text():
    with pytest.raises(ValueError):
        _extract_examples_input({})


def test_post_examples_default_limit_is_3(monkeypatch, fake_provider):
    monkeypatch.setenv("SMIA_AUTH_TOKEN", "test-token")
    resp = _client().post("/examples", json={"text": "kalv", "provider": fake_provider}, headers=AUTH)
    assert resp.status_code == 200
    body = resp.get_json()
    assert len(body["candidates"]) == 3


def test_post_examples_explicit_limit_is_honored(monkeypatch, fake_provider):
    monkeypatch.setenv("SMIA_AUTH_TOKEN", "test-token")
    resp = _client().post(
        "/examples", json={"text": "kalv", "provider": fake_provider, "limit": 10}, headers=AUTH
    )
    assert len(resp.get_json()["candidates"]) == 10


def test_post_examples_unsupported_lang_is_400(monkeypatch, fake_provider):
    monkeypatch.setenv("SMIA_AUTH_TOKEN", "test-token")
    resp = _client().post(
        "/examples", json={"text": "kalv", "lang": "en", "provider": fake_provider}, headers=AUTH
    )
    assert resp.status_code == 400


def test_limit_3_and_limit_10_are_distinct_cache_resources(monkeypatch, fake_provider):
    monkeypatch.setenv("SMIA_AUTH_TOKEN", "test-token")
    client = _client()
    resp3 = client.post("/examples", json={"text": "kalv", "provider": fake_provider, "limit": 3}, headers=AUTH)
    resp10 = client.post("/examples", json={"text": "kalv", "provider": fake_provider, "limit": 10}, headers=AUTH)

    rid3 = resp3.headers["Location"].rsplit("/", 1)[-1]
    rid10 = resp10.headers["Location"].rsplit("/", 1)[-1]
    assert rid3 != rid10

    get3 = client.get(f"/examples/{rid3}", headers=AUTH)
    get10 = client.get(f"/examples/{rid10}", headers=AUTH)
    assert len(get3.get_json()["candidates"]) == 3
    assert len(get10.get_json()["candidates"]) == 10


def test_providers_catalog_lists_examples_kind_with_counts(monkeypatch):
    monkeypatch.setenv("SMIA_AUTH_TOKEN", "test-token")
    resp = _client().get("/providers", headers=AUTH)
    body = resp.get_json()
    assert "examples" in body
    for name in ("tatoeba", "leipzig", "kaikki"):
        assert name in body["examples"]
    counts = body["counts"].get("examples", {})
    for name in ("tatoeba", "leipzig", "kaikki"):
        assert name in counts
    assert "ordbokene" not in counts
