"""Shared fixtures: a clean lookup_cache table per test, and a fresh
registry so adapters registered by one test don't leak into another."""

from __future__ import annotations

import pytest

from db.models import Base, LookupCache, ProviderHealth, TtsAudio
from db.session import get_sessionmaker
import registry as registry_module

# Importing `adapters` here (once, at collection time) runs every real
# adapter module's `registry.register(...)` call — the same side-effect
# `app.py` relies on. Snapshotting the resulting registry state lets
# `fresh_registry` restore *this* baseline before each test instead of
# wiping it to empty, so Flask-based tests that exercise the real `app`
# (e.g. test_stt.py) still see real providers registered, while tests that
# register their own throwaway test-kind adapters still get isolation.
import adapters  # noqa: E402,F401
_BASELINE_ADAPTERS = {kind: dict(providers) for kind, providers in registry_module.registry._adapters.items()}


@pytest.fixture(autouse=True)
def clean_db():
    Session = get_sessionmaker()
    with Session() as db:
        db.query(LookupCache).delete()
        db.query(TtsAudio).delete()
        db.query(ProviderHealth).delete()
        db.commit()
    yield


@pytest.fixture(autouse=True)
def fresh_registry():
    # Mutate the existing singleton in place rather than reassigning
    # `registry_module.registry` — every module did `from registry import
    # registry`, binding its own name to this object, so a reassignment
    # here wouldn't be visible to them.
    registry_module.registry._adapters.clear()
    registry_module.registry._adapters.update(
        {kind: dict(providers) for kind, providers in _BASELINE_ADAPTERS.items()}
    )
    yield
