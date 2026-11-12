"""Tests for the `lexin` provider (lexin-provider tasks 6.1-6.7): the shared
client and the /translations, /ipa and /examples adapters. All network is
mocked with trimmed real responses from `tests/fixtures/lexin/`."""

from __future__ import annotations

import json
import pathlib

import pytest
import requests

from adapters import _lexin
from adapters.lexin_examples import LexinExamplesAdapter
from adapters.lexin_ipa import LexinIpaAdapter
from adapters.lexin_translate import LexinTranslateAdapter
from cache import ProviderLookupError
from registry import registry

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "lexin"


class _Resp:
    def __init__(self, body, status=200):
        self.body, self.status_code = body, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")

    def json(self):
        return self.body


@pytest.fixture(autouse=True)
def no_pacing(monkeypatch):
    monkeypatch.setenv("LEXIN_MIN_INTERVAL_SECONDS", "0")
    monkeypatch.setattr(_lexin, "_last_call", None)


@pytest.fixture
def serve(monkeypatch):
    """serve("nb_nb_avlyse.json") makes every LEXIN call return that fixture and
    returns the list of recorded `(params, headers)` calls."""

    def _serve(name, status=200):
        body = json.loads((FIXTURES / name).read_text())
        calls = []

        def fake_get(url, params=None, headers=None, timeout=None):
            calls.append({"url": url, "params": params, "headers": headers})
            return _Resp(body, status)

        monkeypatch.setattr(_lexin.requests, "get", fake_get)
        return calls

    return _serve


# --- 6.1 prepare_query -----------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Avlyse", "avlyse"),
        ("  avlyse  ", "avlyse"),
        ("av og til", "av og til"),
        ("hund (dyr)", "hund dyr"),
        ("a|b;c/d,e", "a b c d e"),
        ('"hund"', "hund"),
        ("", ""),
    ],
)
def test_prepare_query(raw, expected):
    assert _lexin.prepare_query(raw) == expected


def test_empty_query_makes_no_request(serve):
    calls = serve("nb_nb_avlyse.json")
    assert _lexin.find("  ", "bokmål") == []
    assert calls == []


# --- 6.2 client ------------------------------------------------------------


def test_origin_header_and_params_are_sent(serve):
    calls = serve("nb_nb_avlyse.json")
    _lexin.find("Avlyse", "bokmål")
    assert calls[0]["headers"]["Origin"] == "https://lexin.oslomet.no"
    assert calls[0]["params"] == {
        "searchWord": "avlyse",
        "lang": "bokmål",
        "page": 1,
        "selectLang": "bokmål",
        "includeEngLang": 0,
    }


def test_access_denied_body_is_a_provider_failure_not_an_empty_result(serve):
    serve("access_denied.json")
    with pytest.raises(ProviderLookupError, match="Access denied"):
        _lexin.find("avlyse", "bokmål")


def test_http_403_is_a_provider_failure(serve):
    serve("nb_nb_avlyse.json", status=403)
    with pytest.raises(ProviderLookupError):
        _lexin.find("avlyse", "bokmål")


def test_network_error_is_wrapped(monkeypatch):
    def boom(*a, **k):
        raise requests.ConnectionError("down")

    monkeypatch.setattr(_lexin.requests, "get", boom)
    with pytest.raises(ProviderLookupError):
        _lexin.find("avlyse", "bokmål")


def test_non_json_body_is_a_provider_failure(monkeypatch):
    class _Bad(_Resp):
        def json(self):
            raise ValueError("not json")

    monkeypatch.setattr(_lexin.requests, "get", lambda *a, **k: _Bad(None))
    with pytest.raises(ProviderLookupError):
        _lexin.find("avlyse", "bokmål")


def test_empty_result_is_a_valid_empty_answer(monkeypatch):
    monkeypatch.setattr(_lexin.requests, "get", lambda *a, **k: _Resp({"result": [[]], "resArray": []}))
    assert _lexin.find("xyzzy", "bokmål") == []


def test_non_contiguous_rows_group_into_one_entry_and_markers_are_stripped(serve):
    serve("nb_nb_avlyse.json")
    entries = {e.id: e for e in _lexin.find("avlyse", "bokmål")}
    # 18211's `E-lem` row arrives after other entries' rows in the response.
    assert entries[18211].lemma == "ut~gå"
    assert entries[18211].headword == "utgå"
    assert entries[18211].definitions == ["gå ut, stryke, kansellere, avlyse"]
    assert entries[18211].pronunciations == ["u:tgå"]
    assert len(entries) == 4


def test_empty_text_rows_are_dropped(serve):
    serve("nb_nb_avlyse.json")
    entries = {e.id: e for e in _lexin.find("avlyse", "bokmål")}
    assert entries[47897].examples == ["flyvningen ble kansellert på grunn av tekniske feil", "kansellere en avtale"]
    assert "" not in entries[47897].definitions


def test_inflected_forms_expand_compound_shorthand_and_drop_noise(serve):
    serve("nb_nb_avlyse.json")
    entries = {e.id: e for e in _lexin.find("avlyse", "bokmål")}
    assert "utgår" in _lexin.inflected_forms(entries[18211])  # `-går` of ut~gå
    assert "utgikk" in _lexin.inflected_forms(entries[18211])
    forms = _lexin.inflected_forms(entries[26805])
    assert {"avlyse", "avlyser", "avlyste", "avlyst"} <= forms
    assert "å" not in forms and "har" not in forms


# --- 6.3 rate limiter ------------------------------------------------------


def test_second_call_within_the_interval_waits(serve, monkeypatch):
    serve("nb_nb_avlyse.json")
    monkeypatch.setenv("LEXIN_MIN_INTERVAL_SECONDS", "0.5")
    clock = {"t": 100.0}
    slept = []
    monkeypatch.setattr(_lexin, "_now", lambda: clock["t"])
    monkeypatch.setattr(_lexin, "_sleep", lambda s: (slept.append(s), clock.__setitem__("t", clock["t"] + s)))

    _lexin.find("avlyse", "bokmål")
    assert slept == []  # first call never waits
    clock["t"] += 0.2
    _lexin.find("avlyse", "bokmål")
    assert slept == [pytest.approx(0.3)]


def test_a_call_after_the_interval_does_not_wait(serve, monkeypatch):
    serve("nb_nb_avlyse.json")
    monkeypatch.setenv("LEXIN_MIN_INTERVAL_SECONDS", "0.5")
    clock = {"t": 100.0}
    slept = []
    monkeypatch.setattr(_lexin, "_now", lambda: clock["t"])
    monkeypatch.setattr(_lexin, "_sleep", slept.append)

    _lexin.find("avlyse", "bokmål")
    clock["t"] += 2
    _lexin.find("avlyse", "bokmål")
    assert slept == []


def test_zero_interval_never_sleeps(serve, monkeypatch):
    serve("nb_nb_avlyse.json")
    slept = []
    monkeypatch.setattr(_lexin, "_sleep", slept.append)
    _lexin.find("avlyse", "bokmål")
    _lexin.find("avlyse", "bokmål")
    assert slept == []


def test_default_interval_is_one_second(monkeypatch):
    monkeypatch.delenv("LEXIN_MIN_INTERVAL_SECONDS", raising=False)
    assert _lexin._min_interval() == 1.0


# --- 6.4 translations --------------------------------------------------------


def _translate(frm, to, text):
    return LexinTranslateAdapter().lookup({"text": text, "from": frm, "to": to})


def test_nb_nb_returns_definition_with_headword_in_context(serve):
    serve("nb_nb_avlyse.json")
    candidates = _translate("nb", "nb", "avlyse")["candidates"]
    assert {"text": "innstille, stanse, stoppe, skrinlegge", "context": "avlyse, verb"} in candidates


def test_nb_nb_keeps_fuzzy_matches_labelled_by_their_own_headword(serve):
    serve("nb_nb_avlyse.json")
    contexts = {c["context"] for c in _translate("nb", "nb", "avlyse")["candidates"]}
    assert {"avlyse, verb", "utgå, verb", "avblåse, verb", "kansellere, verb"} == contexts


def test_nb_nb_sends_selectlang_bokmaal(serve):
    calls = serve("nb_nb_avlyse.json")
    _translate("nb", "nb", "avlyse")
    assert calls[0]["params"]["selectLang"] == "bokmål"


def test_nb_en_separates_same_headword_senses_by_definition(serve):
    calls = serve("nb_en_hand.json")
    candidates = _translate("nb", "en", "hånd")["candidates"]
    assert calls[0]["params"]["selectLang"] == "engelsk"
    hands = [c for c in candidates if c["text"] == "hand"]
    assert len(hands) == 3
    assert len({c["context"] for c in hands}) == 3
    assert {"text": "hand", "context": "noun: the end part of an arm"} in candidates
    assert {"text": "hind", "context": "noun: a female deer"} in candidates


def test_nb_en_makes_a_single_call(serve):
    calls = serve("nb_en_hand.json")
    _translate("nb", "en", "hånd")
    assert len(calls) == 1


@pytest.mark.parametrize("frm, to", [("nb", "de"), ("en", "nb"), ("nb", "uk"), ("de", "nb")])
def test_unsupported_pairs_fail_and_do_not_call_out(serve, frm, to):
    calls = serve("nb_nb_avlyse.json")
    with pytest.raises(_lexin.UnsupportedPairError):
        _translate(frm, to, "avlyse")
    assert calls == []


def test_unsupported_pair_is_a_provider_lookup_error():
    assert issubclass(_lexin.UnsupportedPairError, ProviderLookupError)


def test_translate_no_match_is_empty_not_an_error(monkeypatch):
    monkeypatch.setattr(_lexin.requests, "get", lambda *a, **k: _Resp({"result": [[]]}))
    assert _translate("nb", "nb", "xyzzy") == {"candidates": []}


# --- 6.5 ipa -----------------------------------------------------------------


def _ipa(text, **extra):
    return LexinIpaAdapter().lookup({"text": text, **extra})["candidates"]


def test_ipa_headword_match_returns_the_notation_as_is(serve):
    serve("nb_nb_avlyse.json")
    assert _ipa("avlyse") == [{"ipa": "'a:vly:se"}]


def test_ipa_excludes_fuzzy_hit_entries(serve):
    serve("nb_nb_avlyse.json")
    notations = [c["ipa"] for c in _ipa("avlyse")]
    assert "u:tgå" not in notations and "a:vblå:se" not in notations


def test_ipa_matches_an_inflected_form_through_the_mor_string(serve):
    serve("nb_nb_skinner.json")
    assert _ipa("skinner") == [{"ipa": "sjine"}]  # skinne (noun) and skinne (verb) collapse


def test_ipa_does_not_return_unrelated_entries(serve):
    serve("nb_nb_skinner.json")
    notations = {c["ipa"] for c in _ipa("skinner")}
    assert "j'æ:rnba:ne" not in notations  # jernbane
    assert "sj'ø'yte" not in notations  # skøyte


def test_ipa_compound_shorthand_form_matches(serve):
    serve("nb_nb_avlyse.json")
    assert _ipa("utgår") == [{"ipa": "u:tgå"}]


def test_ipa_noise_tokens_do_not_match(serve):
    serve("nb_nb_avlyse.json")
    assert _ipa("å") == [] and _ipa("har") == []


def test_ipa_candidates_carry_only_ipa(serve):
    serve("nb_nb_avlyse.json")
    assert all(set(c) == {"ipa"} for c in _ipa("avlyse"))


def test_ipa_non_nb_lang_is_empty_and_makes_no_call(serve):
    calls = serve("nb_nb_avlyse.json")
    assert _ipa("avlyse", lang="en") == []
    assert calls == []


def test_ipa_miss_is_empty(serve):
    serve("nb_nb_avlyse.json")
    assert _ipa("zzzz") == []


# --- 6.6 examples ------------------------------------------------------------


def _examples(text, **extra):
    return LexinExamplesAdapter().lookup({"text": text, "limit": 10, **extra})["candidates"]


def test_examples_carry_the_entry_definition_as_sense(serve):
    serve("nb_nb_avlyse.json")
    assert {
        "text": "konserten ble avlyst",
        "sense": "innstille, stanse, stoppe, skrinlegge",
    } in _examples("avlyse")


def test_examples_keep_source_order(serve):
    serve("nb_nb_avlyse.json")
    texts = [c["text"] for c in _examples("avlyse")]
    assert texts[0] == "konserten ble avlyst"
    assert texts == [
        "konserten ble avlyst",
        "programinnslaget utgår",
        "streiken ble avblåst i går",
        "flyvningen ble kansellert på grunn av tekniske feil",
        "kansellere en avtale",
    ]


def test_examples_never_carry_a_translation_field(serve):
    serve("nb_nb_avlyse.json")
    assert all(set(c) <= {"text", "sense"} for c in _examples("avlyse"))


def test_examples_default_limit_is_three(serve):
    serve("nb_nb_avlyse.json")
    assert len(LexinExamplesAdapter().lookup({"text": "avlyse"})["candidates"]) == 3


def test_examples_limit_is_honoured(serve):
    serve("nb_nb_avlyse.json")
    assert len(_examples("avlyse", limit=2)) == 2


def test_examples_entry_without_definition_keeps_its_examples_without_sense(monkeypatch):
    rows = [
        {"id": 1, "sub_id": 1, "type": "N-lem", "text": "foo"},
        {"id": 1, "sub_id": 2, "type": "N-eks", "text": "et eksempel"},
    ]
    monkeypatch.setattr(_lexin.requests, "get", lambda *a, **k: _Resp({"result": [rows]}))
    assert _examples("foo") == [{"text": "et eksempel"}]


def test_examples_non_nb_lang_is_empty(serve):
    calls = serve("nb_nb_avlyse.json")
    assert _examples("avlyse", lang="en") == []
    assert calls == []


# --- 6.7 registry --------------------------------------------------------------


@pytest.mark.parametrize("kind", ["translations", "ipa", "examples"])
def test_lexin_is_registered_for_the_three_kinds(kind):
    assert "lexin" in registry.providers_for(kind)


@pytest.mark.parametrize("kind", ["tts", "inflections"])
def test_lexin_is_not_registered_for_tts_or_inflections(kind):
    assert "lexin" not in registry.providers_for(kind)
