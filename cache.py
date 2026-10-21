"""
cache.py — the shared provider-execution + cache runner (D-S3): the one
mechanism every endpoint (`/inflections`, `/ipa`, `/tts`, `/translations`,
`/stt`) builds on. Cache check on `(kind, provider, sha256(input))` → call
provider on miss → store → return. See db/models.py's LookupCache docstring
for why there are two distinct hashes.
"""

from __future__ import annotations

import hashlib
import json

import health
from db.models import LookupCache
from registry import registry


def canonicalize(input_dict: dict) -> str:
    return json.dumps(input_dict, sort_keys=True, separators=(",", ":"))


def input_hash(input_dict: dict) -> str:
    return hashlib.sha256(canonicalize(input_dict).encode("utf-8")).hexdigest()


def resource_id(kind: str, provider: str, ihash: str) -> str:
    return hashlib.sha256(f"{kind}:{provider}:{ihash}".encode("utf-8")).hexdigest()


class ProviderLookupError(Exception):
    """Raised by an adapter's lookup() to signal the provider itself failed
    (network error, parse error, etc). The runner never tries another
    provider in response — that's a separate, explicit caller request
    per the 'no fallback or fan-out' requirement."""


def run_lookup(db, kind: str, requested_provider: str | None, input_dict: dict, *, force_refresh: bool = False):
    """Resolves the provider, checks the cache, invokes the adapter on a
    miss, stores the result, and returns `(payload, resource_id, was_cached)`.

    `payload` always includes a top-level `provider` key (provider
    provenance requirement) in addition to whatever shape the adapter
    returns.
    """
    provider = registry.resolve_provider(kind, requested_provider)
    ihash = input_hash(input_dict)
    rid = resource_id(kind, provider, ihash)
    health.record_request(db, kind, provider)

    if not force_refresh:
        row = db.get(LookupCache, rid)
        if row is not None:
            return row.payload, rid, True

    adapter = registry.adapter_for(kind, provider)
    try:
        result = adapter.lookup(input_dict)
    except ProviderLookupError as exc:
        health.record_failure(db, kind, provider, str(exc))
        raise
    health.record_success(db, kind, provider)
    payload = {"provider": provider, **result}

    row = db.get(LookupCache, rid)
    if row is None:
        row = LookupCache(id=rid, kind=kind, provider=provider, input_hash=ihash, payload=payload)
        db.add(row)
    else:
        row.payload = payload
    db.commit()

    return payload, rid, False


def fetch_by_id(db, kind: str, rid: str):
    """GET /<kind>/{id}: cache-only, no provider invocation. Returns the
    payload or None if unknown / belongs to a different kind."""
    row = db.get(LookupCache, rid)
    if row is None or row.kind != kind:
        return None
    return row.payload
