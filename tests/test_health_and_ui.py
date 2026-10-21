"""Tests for GET /providers, GET /health (task 8.1-8.2), and /ui static
serving + its auth exemption (tasks 8.3-8.4)."""

from __future__ import annotations

import cache
from app import app as real_app
from db.session import session_scope
from registry import registry


def _client():
    return real_app.test_client()


AUTH = {"Authorization": "Bearer test-token"}


def test_providers_catalog_lists_registered_adapters(monkeypatch):
    monkeypatch.setenv("SMIA_AUTH_TOKEN", "test-token")
    resp = _client().get("/providers", headers=AUTH)
    assert resp.status_code == 200
    body = resp.get_json()
    assert "ordbank" in body["inflections"]


def test_health_reflects_requests_and_cache_hits(monkeypatch):
    monkeypatch.setenv("SMIA_AUTH_TOKEN", "test-token")
    registry.register("testkind", "only", type("A", (), {"lookup": lambda self, i: {"ok": True}})())

    with session_scope() as db:
        cache.run_lookup(db, "testkind", "only", {"x": 1})
    with session_scope() as db:
        cache.run_lookup(db, "testkind", "only", {"x": 1})  # cache hit

    resp = _client().get("/health", headers=AUTH)
    rows = resp.get_json()
    row = next(r for r in rows if r["kind"] == "testkind" and r["provider"] == "only")
    assert row["requestsCount"] == 2
    assert row["successCount"] == 1
    assert row["hitCount"] == 1


def test_ui_index_and_assets_are_unauthenticated():
    c = _client()
    assert c.get("/ui").status_code == 200
    assert c.get("/ui/ui.css").status_code == 200
    assert c.get("/ui/ui.js").status_code == 200


def test_api_routes_still_require_auth_under_ui_unrelated_paths():
    c = _client()
    assert c.get("/providers").status_code == 401
