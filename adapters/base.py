"""
adapters/base.py — the provider adapter interface (D-S4: a provider can be a
live call (scrape, API) or a query against an imported dataset — the
interface doesn't care which).
"""

from __future__ import annotations

from typing import Protocol


class Adapter(Protocol):
    def lookup(self, input_dict: dict) -> dict:
        """Given the request's identifying fields (everything except
        `provider`), return this endpoint's output shape *excluding* the
        top-level `provider` key — cache.run_lookup adds that. Raise
        cache.ProviderLookupError (or let a real exception propagate) if the
        provider itself fails; the runner never falls back to another
        provider."""
        ...
