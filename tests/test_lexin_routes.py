"""End-to-end tests for `provider=lexin` through the real app (lexin-provider
task 6.8). LEXIN's HTTP layer is mocked; like the other route tests these need
the migrated database."""

from __future__ import annotations

import json
import pathlib

import pytest

from adapters import _lexin
from app import app as real_app

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "lexin"
AUTH = {"Authorization": "Bearer test-token"}


class _Resp:
    status_code = 200

    def __init__(self, body):
        self.body = body

    def raise_for_status(self):
        pass

    def json(self):
        return self.body


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SMIA_AUTH_TOKEN", "test-token")
    monkeypatch.setenv("LEXIN_MIN_INTERVAL_SECONDS", "0")
    return real_app.test_client()


@pytest.fixture
def serve(monkeypatch):
    def _serve(name):
        body = json.loads((FIXTURES / name).read_text())
        calls = []

        def fake_get(url, params=None, headers=None, timeout=None):
            calls.append(params)
            return _Resp(body)

        monkeypatch.setattr(_lexin.requests, "get", fake_get)
        return calls

    return _serve


def test_translations_nb_nb(client, serve):
    serve("nb_nb_avlyse.json")
    resp = client.post("/translations", json={"text": "avlyse", "from": "nb", "to": "nb", "provider": "lexin"}, headers=AUTH)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["provider"] == "lexin"
    assert {"text": "innstille, stanse, stoppe, skrinlegge", "context": "avlyse, verb"} in body["candidates"]


def test_translations_nb_en(client, serve):
    serve("nb_en_hand.json")
    resp = client.post("/translations", json={"text": "hånd", "from": "nb", "to": "en", "provider": "lexin"}, headers=AUTH)
    assert resp.status_code == 200
    assert sum(1 for c in resp.get_json()["candidates"] if c["text"] == "hand") == 3


def test_translations_unsupported_pair_is_a_gateway_error(client, serve):
    serve("nb_nb_avlyse.json")
    resp = client.post("/translations", json={"text": "avlyse", "from": "nb", "to": "de", "provider": "lexin"}, headers=AUTH)
    assert resp.status_code == 502


def test_ipa(client, serve):
    serve("nb_nb_avlyse.json")
    resp = client.post("/ipa", json={"text": "avlyse", "lang": "nb", "provider": "lexin"}, headers=AUTH)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["provider"] == "lexin"
    assert body["candidates"] == [{"ipa": "'a:vly:se"}]


def test_examples(client, serve):
    serve("nb_nb_avlyse.json")
    resp = client.post("/examples", json={"text": "avlyse", "provider": "lexin"}, headers=AUTH)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["provider"] == "lexin"
    assert len(body["candidates"]) == 3
    assert body["candidates"][0]["text"] == "konserten ble avlyst"


@pytest.mark.parametrize(
    "path, payload",
    [
        ("/translations", {"text": "avlyse", "from": "nb", "to": "nb", "provider": "lexin"}),
        ("/ipa", {"text": "avlyse", "lang": "nb", "provider": "lexin"}),
        ("/examples", {"text": "avlyse", "provider": "lexin"}),
    ],
)
def test_a_refused_lookup_is_a_gateway_error_and_is_not_cached(client, serve, path, payload):
    serve("access_denied.json")
    assert client.post(path, json=payload, headers=AUTH).status_code == 502

    # LEXIN recovers: the same request must reach LEXIN again, not hit a cached "empty" answer.
    calls = serve("nb_nb_avlyse.json")
    resp = client.post(path, json=payload, headers=AUTH)
    assert resp.status_code == 200
    assert calls, "the second request should have gone to LEXIN, not been served from cache"
    assert resp.get_json()["candidates"]
