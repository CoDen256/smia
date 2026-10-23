"""Live network test for the `ordbokene` /ipa provider (task 4.4) — hits
the real ord.uib.no API. Marked separately from test_ipa_adapters.py since
it needs network access."""

from __future__ import annotations

import pytest

from adapters.ordbokene import OrdbokeneAdapter
from cache import ProviderLookupError


def test_live_pronunciation_lookup():
    try:
        result = OrdbokeneAdapter().lookup({"text": "sjanger", "lang": "nb"})
    except ProviderLookupError:
        pytest.skip("ord.uib.no not reachable")
    assert any(c["ipa"] for c in result["candidates"])
