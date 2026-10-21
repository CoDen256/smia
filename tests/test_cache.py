"""Tests for the lookup-cache core (tasks 2.1-2.6): idempotent POST,
cache-miss-on-different-provider, no-fallback-on-failure, and the generic
GET /<kind>/{id} fetch-by-id contract — exercised via a throwaway test
kind so this doesn't depend on any real provider adapter existing yet."""

from __future__ import annotations

import pytest

import cache
import registry as registry_module
from db.session import get_sessionmaker
from registry import ProviderRequiredError, UnknownProviderError, registry


class CountingAdapter:
    """Records how many times it was actually invoked, so tests can assert
    a cache hit never reaches the adapter."""

    def __init__(self, result_fn):
        self.calls = 0
        self._result_fn = result_fn

    def lookup(self, input_dict):
        self.calls += 1
        return self._result_fn(input_dict)


class FailingAdapter:
    def __init__(self):
        self.calls = 0

    def lookup(self, input_dict):
        self.calls += 1
        raise cache.ProviderLookupError("boom")


def _db():
    return get_sessionmaker()()


def test_resolve_provider_requires_explicit_choice_with_multiple_configured():
    registry.register("testkind", "a", CountingAdapter(lambda i: {}))
    registry.register("testkind", "b", CountingAdapter(lambda i: {}))
    with pytest.raises(ProviderRequiredError) as exc:
        registry.resolve_provider("testkind", None)
    assert set(exc.value.available) == {"a", "b"}


def test_resolve_provider_defaults_when_exactly_one_configured():
    registry.register("testkind", "only", CountingAdapter(lambda i: {}))
    assert registry.resolve_provider("testkind", None) == "only"


def test_resolve_provider_rejects_unknown_name():
    registry.register("testkind", "a", CountingAdapter(lambda i: {}))
    with pytest.raises(UnknownProviderError):
        registry.resolve_provider("testkind", "nope")


def test_identical_request_hits_cache_without_reinvoking_provider():
    adapter = CountingAdapter(lambda i: {"word": i["word"].upper()})
    registry.register("testkind", "p", adapter)

    with _db() as db:
        payload1, rid1, cached1 = cache.run_lookup(db, "testkind", "p", {"word": "hei"})
    with _db() as db:
        payload2, rid2, cached2 = cache.run_lookup(db, "testkind", "p", {"word": "hei"})

    assert adapter.calls == 1
    assert cached1 is False
    assert cached2 is True
    assert rid1 == rid2
    assert payload1 == payload2 == {"provider": "p", "word": "HEI"}


def test_same_input_different_provider_is_cache_miss():
    adapter_a = CountingAdapter(lambda i: {"from": "a"})
    adapter_b = CountingAdapter(lambda i: {"from": "b"})
    registry.register("testkind", "a", adapter_a)
    registry.register("testkind", "b", adapter_b)

    with _db() as db:
        payload_a, rid_a, _ = cache.run_lookup(db, "testkind", "a", {"word": "hei"})
    with _db() as db:
        payload_b, rid_b, _ = cache.run_lookup(db, "testkind", "b", {"word": "hei"})

    assert adapter_a.calls == 1
    assert adapter_b.calls == 1
    assert rid_a != rid_b
    assert payload_a["provider"] == "a"
    assert payload_b["provider"] == "b"


def test_failing_provider_returns_failure_and_is_not_retried_with_another():
    failing = FailingAdapter()
    other = CountingAdapter(lambda i: {"ok": True})
    registry.register("testkind", "bad", failing)
    registry.register("testkind", "good", other)

    with _db() as db:
        with pytest.raises(cache.ProviderLookupError):
            cache.run_lookup(db, "testkind", "bad", {"word": "hei"})

    assert failing.calls == 1
    assert other.calls == 0  # no fallback or fan-out


def test_force_refresh_bypasses_cache_and_overwrites():
    calls = {"n": 0}

    def result_fn(i):
        calls["n"] += 1
        return {"n": calls["n"]}

    adapter = CountingAdapter(result_fn)
    registry.register("testkind", "p", adapter)

    with _db() as db:
        payload1, rid1, cached1 = cache.run_lookup(db, "testkind", "p", {"word": "hei"})
    with _db() as db:
        payload2, rid2, cached2 = cache.run_lookup(db, "testkind", "p", {"word": "hei"}, force_refresh=True)

    assert cached1 is False
    assert cached2 is False
    assert rid1 == rid2
    assert payload1["n"] == 1
    assert payload2["n"] == 2
    assert adapter.calls == 2


def test_fetch_by_id_returns_cached_payload_without_invoking_provider():
    adapter = CountingAdapter(lambda i: {"word": i["word"]})
    registry.register("testkind", "p", adapter)

    with _db() as db:
        _, rid, _ = cache.run_lookup(db, "testkind", "p", {"word": "hei"})

    assert adapter.calls == 1
    with _db() as db:
        fetched = cache.fetch_by_id(db, "testkind", rid)
    assert fetched == {"provider": "p", "word": "hei"}
    assert adapter.calls == 1  # fetch-by-id never calls the provider


def test_fetch_by_id_unknown_id_returns_none():
    with _db() as db:
        assert cache.fetch_by_id(db, "testkind", "deadbeef") is None


def test_fetch_by_id_wrong_kind_returns_none():
    adapter = CountingAdapter(lambda i: {"word": i["word"]})
    registry.register("testkind", "p", adapter)
    with _db() as db:
        _, rid, _ = cache.run_lookup(db, "testkind", "p", {"word": "hei"})

    with _db() as db:
        assert cache.fetch_by_id(db, "othertestkind", rid) is None
