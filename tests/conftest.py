"""Shared fixtures: a clean lookup_cache table per test, and a fresh
registry so adapters registered by one test don't leak into another."""

from __future__ import annotations

import pytest

from db.models import Base, LookupCache, TtsAudio
from db.session import get_sessionmaker
import registry as registry_module


@pytest.fixture(autouse=True)
def clean_db():
    Session = get_sessionmaker()
    with Session() as db:
        db.query(LookupCache).delete()
        db.query(TtsAudio).delete()
        db.commit()
    yield


@pytest.fixture(autouse=True)
def fresh_registry():
    # Mutate the existing singleton in place rather than reassigning
    # `registry_module.registry` — every module did `from registry import
    # registry`, binding its own name to this object, so a reassignment
    # here wouldn't be visible to them.
    registry_module.registry._adapters.clear()
    yield
