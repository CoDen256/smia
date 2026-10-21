"""Tests for the generic POST/GET routes (routes/generic.py) and the
shared-bearer-token auth middleware, via a minimal throwaway Flask app
(not app.py's real one, so this doesn't depend on any real adapter)."""

from __future__ import annotations

import os

import pytest
from flask import Flask

from auth import register_auth
from registry import registry
from routes.generic import register_lookup_routes


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SMIA_AUTH_TOKEN", "test-token")
    app = Flask(__name__)
    register_auth(app)

    def extract_input(body):
        if "word" not in body:
            raise ValueError("word is required")
        return {"word": body["word"]}

    register_lookup_routes(app, "testkind", extract_input)
    return app.test_client()


AUTH = {"Authorization": "Bearer test-token"}


def test_missing_token_is_rejected(client):
    resp = client.post("/testkind", json={"word": "hei"})
    assert resp.status_code == 401


def test_wrong_token_is_rejected(client):
    resp = client.post("/testkind", json={"word": "hei"}, headers={"Authorization": "Bearer wrong"})
    assert resp.status_code == 401


def test_post_then_get_round_trips(client):
    registry.register("testkind", "p", type("A", (), {"lookup": lambda self, i: {"word": i["word"]}})())

    post_resp = client.post("/testkind", json={"word": "hei", "provider": "p"}, headers=AUTH)
    assert post_resp.status_code == 200
    body = post_resp.get_json()
    assert body == {"provider": "p", "word": "hei"}

    rid = post_resp.headers["Location"].rsplit("/", 1)[-1]
    get_resp = client.get(f"/testkind/{rid}", headers=AUTH)
    assert get_resp.status_code == 200
    assert get_resp.get_json() == {"provider": "p", "word": "hei"}


def test_get_unknown_id_is_404(client):
    resp = client.get("/testkind/deadbeef", headers=AUTH)
    assert resp.status_code == 404


def test_post_missing_provider_with_multiple_configured_is_400(client):
    registry.register("testkind", "a", type("A", (), {"lookup": lambda self, i: {}})())
    registry.register("testkind", "b", type("B", (), {"lookup": lambda self, i: {}})())

    resp = client.post("/testkind", json={"word": "hei"}, headers=AUTH)
    assert resp.status_code == 400
    assert set(resp.get_json()["available"]) == {"a", "b"}


def test_post_malformed_body_is_400(client):
    registry.register("testkind", "p", type("A", (), {"lookup": lambda self, i: {}})())
    resp = client.post("/testkind", json={}, headers=AUTH)
    assert resp.status_code == 400
