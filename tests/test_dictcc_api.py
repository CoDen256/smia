"""Tests for the `dictcc_api` adapter (tasks 3.1-3.3, 3.5), mocking HTTP
against fixtures captured from the real API (providers/dict/api.md and
live probes run while implementing this adapter) rather than depending on
network access in CI."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from adapters.dictcc_api import (
    DictccApiInflectAdapter,
    DictccApiTranslateAdapter,
    DictccApiTtsAdapter,
    UnsupportedPairError,
)

# Captured from providers/dict/api.md's own documented example.
_KALV_RESPONSE = {
    "translations": [
        {"id": 528676, "term1": "calf", "term2": "kalv {m}", "entry_type": "noun",
         "subj_ids": ",25,", "vt_usage": 0, "sort_num": 16}
    ],
    "dir": 2,
    "inflections": "<tr>...</tr>",
    "inflections_repl": (
        " en&nbsp;kalv \tkalv\t;\t kalven \tkalven\t;\t kalver \tkalver\t;\t kalvene \tkalvene\t;\t"
    ),
    "inflections_info": "<br><b>NOUN</b> &nbsp; article indefinite.sg | definite.sg | indefinite.pl | definite.pl",
}

# Captured live: a German noun with a 2-slot (no indef/def split) table.
_HAUS_RESPONSE = {
    "translations": [{"id": 67085, "term1": "Haus {n}", "term2": "hus {n}", "entry_type": "noun",
                       "subj_ids": "", "vt_usage": 28, "sort_num": 16}],
    "dir": 1,
    "inflections": "<tr>...</tr>",
    "inflections_repl": " das&nbsp;Haus \tHaus\t;\t die&nbsp;Häuser \tHäuser\t;\t",
    "inflections_info": "<br><b>NOUN</b>&nbsp;&nbsp;article sg | article pl",
}

# Captured live: a homograph with both a NOUN and VERB inflection block.
_GEHEN_RESPONSE = {
    "translations": [],
    "dir": 1,
    "inflections": "<tr>...</tr>",
    "inflections_repl": (
        " das&nbsp;Gehen \tGehen\t;\t - \t-\t;\t gehen \tgehen\t;\t ging \tging\t;\t gegangen \tgegangen\t;\t"
    ),
    "inflections_info": "<br><b>NOUN</b> &nbsp; article sg | article pl<br><b>VERB</b> &nbsp; infinitive | preterite | pp",
}

_NO_TABLE_RESPONSE = {
    "translations": [], "dir": 1, "inflections": "", "inflections_repl": "", "inflections_info": "",
}

# Captured live: "hus"'s definite-plural cell has two alternates ("husa",
# "husene") — the raw `inflections` HTML shows them as one cell joined by
# "/", but `inflections_repl` flattens that into an extra ";"-delimited
# segment with no label of its own.
_HUS_RESPONSE = {
    "translations": [{"id": 1, "term1": "hus", "term2": "house {n}", "entry_type": "noun",
                       "subj_ids": "", "vt_usage": 0, "sort_num": 16}],
    "dir": 2,
    "inflections": (
        '<tr title="article indefinite.sg | definite.sg | indefinite.pl | definite.pl">'
        '<td valign="top"></td><td valign="top"><b>NOUN</b>&nbsp;&nbsp;</td>'
        '<td width="95%" > et&nbsp;hus <span class="infl_pipe">|</span> huset '
        '<span class="infl_pipe">|</span> hus <span class="infl_pipe">|</span> husa / husene </td></tr>'
    ),
    "inflections_repl": (
        " et&nbsp;hus \thus\t;\t huset \thuset\t;\t hus \thus\t;\t husa \thusa\t;\t husene \thusene\t;\t"
    ),
    "inflections_info": "<br><b>NOUN</b> &nbsp; article indefinite.sg | definite.sg | indefinite.pl | definite.pl",
}


def _mock_response(json_data):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = json_data
    return resp


def test_translate_parses_best_match():
    with patch("adapters.dictcc_api.requests.get", return_value=_mock_response(_KALV_RESPONSE)):
        result = DictccApiTranslateAdapter().lookup({"text": "kalv", "from": "nb", "to": "en"})
    assert result == {"candidates": [{"text": "calf", "context": "[noun]"}]}


def test_translate_unsupported_pair_raises():
    with pytest.raises(UnsupportedPairError):
        DictccApiTranslateAdapter().lookup({"text": "hus", "from": "nb", "to": "fr"})


def test_translate_no_match_returns_empty_candidates():
    with patch("adapters.dictcc_api.requests.get", return_value=_mock_response(_NO_TABLE_RESPONSE)):
        result = DictccApiTranslateAdapter().lookup({"text": "zzz", "from": "nb", "to": "en"})
    assert result == {"candidates": []}


def test_translate_untyped_phrase_entry_gets_source_phrase_as_context():
    # Captured live: querying "igjen" (dir=2, nb from-side on term2)
    # surfaces "Kom igjen!" -> "Come on!", an entry_type="" phrase entry
    # unrelated to "igjen" as a standalone word — the source phrase (the
    # from-language field, term2 here) becomes this candidate's context so
    # it's clear which bigger phrase "Come on!" actually translates.
    response = {
        "translations": [
            {"id": 1, "term1": "again", "term2": "igjen", "entry_type": "adv", "subj_ids": "", "vt_usage": 0, "sort_num": 12},
            {"id": 2, "term1": "Come on!", "term2": "Kom igjen!", "entry_type": "", "subj_ids": "", "vt_usage": 0, "sort_num": 22},
        ],
        "dir": 2, "inflections": "", "inflections_repl": "", "inflections_info": "",
    }
    with patch("adapters.dictcc_api.requests.get", return_value=_mock_response(response)):
        result = DictccApiTranslateAdapter().lookup({"text": "igjen", "from": "nb", "to": "en"})
    assert result == {
        "candidates": [
            {"text": "again", "context": "[adv]"},
            {"text": "Come on!", "context": "Kom igjen!"},
        ]
    }


def test_translate_groups_same_entry_type_into_one_candidate():
    # Two "noun" entries for the same lemma must join into one candidate's
    # text with "/", not become two separate candidates (translate-multi-
    # candidate D-TM3's grouping rule, mirrored from dictcc_static).
    response = {
        "translations": [
            {"id": 1, "term1": "calf", "term2": "kalv {m}", "entry_type": "noun", "subj_ids": "", "vt_usage": 0, "sort_num": 16},
            {"id": 2, "term1": "calf", "term2": "kalve {m}", "entry_type": "noun", "subj_ids": "", "vt_usage": 0, "sort_num": 17},
        ],
        "dir": 2, "inflections": "", "inflections_repl": "", "inflections_info": "",
    }
    with patch("adapters.dictcc_api.requests.get", return_value=_mock_response(response)):
        result = DictccApiTranslateAdapter().lookup({"text": "calf", "from": "en", "to": "nb"})
    assert result == {"candidates": [{"text": "kalv {m}/kalve {m}", "context": "[noun]"}]}


def test_inflect_noun_full_four_slot_shape():
    with patch("adapters.dictcc_api.requests.get", return_value=_mock_response(_KALV_RESPONSE)):
        result = DictccApiInflectAdapter().lookup({"word": "kalv", "lang": "nb"})
    assert result["candidates"] == [{
        "lemma": "kalv", "pos": "substantiv",
        "paradigm": {"article": "en", "sg_indef": "kalv", "sg_def": "kalven", "pl_indef": "kalver", "pl_def": "kalvene"},
    }]


def test_inflect_noun_two_slot_shape_omits_def_keys():
    with patch("adapters.dictcc_api.requests.get", return_value=_mock_response(_HAUS_RESPONSE)):
        result = DictccApiInflectAdapter().lookup({"word": "Haus", "lang": "de"})
    candidate = result["candidates"][0]
    assert candidate["paradigm"] == {"article": "das", "sg_indef": "Haus", "pl_indef": "Häuser"}
    assert "sg_def" not in candidate["paradigm"]
    assert "pl_def" not in candidate["paradigm"]


def test_inflect_multiple_pos_blocks_are_separate_candidates():
    with patch("adapters.dictcc_api.requests.get", return_value=_mock_response(_GEHEN_RESPONSE)):
        result = DictccApiInflectAdapter().lookup({"word": "gehen", "lang": "de"})
    poses = {c["pos"] for c in result["candidates"]}
    assert poses == {"substantiv", "verb"}
    verb = next(c for c in result["candidates"] if c["pos"] == "verb")
    assert verb["paradigm"] == {"infinitiv": "gehen", "preteritum": "ging", "perfektum": "gegangen"}
    noun = next(c for c in result["candidates"] if c["pos"] == "substantiv")
    assert noun["paradigm"] == {"article": "das", "sg_indef": "Gehen"}  # "-" plural dropped, not "-"


def test_inflect_cell_with_slash_alternates_keeps_both():
    # Regression: inflections_repl flattens "husa / husene" (one cell) into
    # an extra untagged segment beyond the label count — a strict
    # 1-segment-per-label read silently dropped "husene".
    with patch("adapters.dictcc_api.requests.get", return_value=_mock_response(_HUS_RESPONSE)):
        result = DictccApiInflectAdapter().lookup({"word": "hus", "lang": "nb"})
    candidate = result["candidates"][0]
    assert candidate["paradigm"]["pl_def"] == "husa / husene"


def test_inflect_no_table_returns_empty_candidates():
    with patch("adapters.dictcc_api.requests.get", return_value=_mock_response(_NO_TABLE_RESPONSE)):
        result = DictccApiInflectAdapter().lookup({"word": "zzz", "lang": "nb"})
    assert result == {"candidates": []}


def test_inflect_unsupported_language_raises():
    with pytest.raises(UnsupportedPairError):
        DictccApiInflectAdapter().lookup({"word": "chat", "lang": "fr"})


def test_tts_two_step_flow_human_and_synthetic(monkeypatch):
    translations_resp = _mock_response(_KALV_RESPONSE)

    audio_calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        if "app_translations" in url:
            return translations_resp
        audio_calls.append(params)
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.headers = {"Content-Type": "audio/mpeg"}
        resp.content = b"fake-mp3-bytes-%d" % len(audio_calls)
        return resp

    with patch("adapters.dictcc_api.requests.get", side_effect=fake_get):
        result = DictccApiTtsAdapter().lookup({"text": "kalv", "lang": "nb"})

    assert len(result["candidates"]) == 2
    sources = {c["source"] for c in result["candidates"]}
    assert sources == {"human", "synthetic"}
    synthetic = next(c for c in result["candidates"] if c["source"] == "synthetic")
    assert synthetic["voice"] == "Liv"
    # both audio calls were keyed by the translation entry's id
    assert all(p["id"] == 528676 for p in audio_calls)


def test_tts_skips_synthetic_voice_for_unconfirmed_language(monkeypatch):
    def fake_get(url, params=None, headers=None, timeout=None):
        if "app_translations" in url:
            return _mock_response(_HAUS_RESPONSE)
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.headers = {"Content-Type": "audio/mpeg"}
        resp.content = b"fake-mp3-bytes"
        return resp

    with patch("adapters.dictcc_api.requests.get", side_effect=fake_get):
        result = DictccApiTtsAdapter().lookup({"text": "Haus", "lang": "de"})

    assert len(result["candidates"]) == 1
    assert result["candidates"][0]["source"] == "human"


def test_tts_unsupported_language_raises():
    with pytest.raises(UnsupportedPairError):
        DictccApiTtsAdapter().lookup({"text": "chat", "lang": "fr"})
