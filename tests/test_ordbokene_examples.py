"""Tests for the `ordbokene` `/examples` adapter (examples-api tasks
5.1-5.5, 7.9). `_resolve_placeholders`/`_collect_examples` are pure
functions tested directly; the live-API round trip mirrors
`tests/test_ordbokene.py`'s network-skip pattern."""

from __future__ import annotations

import pytest

from adapters.ordbokene_examples import OrdbokeneExamplesAdapter, _collect_examples, _resolve_placeholders
from cache import ProviderLookupError


def test_placeholder_resolved_from_single_item():
    assert _resolve_placeholders("slakte en $", [{"text": "kalv"}]) == "slakte en kalv"


def test_no_placeholder_is_verbatim():
    assert _resolve_placeholders("både kua og kalven står i fjøset", []) == "både kua og kalven står i fjøset"


def test_multiple_placeholders_resolved_in_order():
    assert _resolve_placeholders("om folk: $, $", [{"text": "flink"}, {"text": "rask"}]) == "om folk: flink, rask"


def test_mismatched_placeholder_count_is_skipped():
    assert _resolve_placeholders("slakte en $", []) is None
    assert _resolve_placeholders("om folk: $, $", [{"text": "flink"}]) is None


def test_nested_sub_definition_example_is_found():
    elements = [
        {
            "type_": "explanation",
            "content": "outer sense",
        },
        {
            "type_": "definition",
            "elements": [
                {"type_": "explanation", "content": "inner sense"},
                {"type_": "example", "quote": {"content": "en kalv", "items": []}},
            ],
        },
    ]
    out = []
    _collect_examples(elements, None, out)
    assert out == [{"text": "en kalv", "sense": "inner sense"}]


def test_sense_inherited_when_no_closer_explanation():
    elements = [
        {"type_": "explanation", "content": "outer sense"},
        {
            "type_": "definition",
            "elements": [
                {"type_": "example", "quote": {"content": "en kalv", "items": []}},
            ],
        },
    ]
    out = []
    _collect_examples(elements, None, out)
    assert out == [{"text": "en kalv", "sense": "outer sense"}]


def test_live_kalv_lookup():
    try:
        result = OrdbokeneExamplesAdapter().lookup({"text": "kalv", "lang": "nb", "limit": 10})
    except ProviderLookupError:
        pytest.skip("ord.uib.no not reachable")
    texts = [c["text"] for c in result["candidates"]]
    assert "slakte en kalv" in texts
    assert all("$" not in c["text"] for c in result["candidates"])
