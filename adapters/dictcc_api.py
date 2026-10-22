"""
adapters/dictcc_api.py — the `dictcc_api` provider: dict.cc's mobile-app
backend (`app_translations.php` / `speak.audio.v2.php`), a different access
path than the public website's obfuscated anti-bot JS that blocked the
original `smia-service-foundation` stub (tasks 5.3/6.5, now un-stubbed —
task 1.6).

One `app_translations.php` call backs three kinds (D-S4's established
"one dataset/adapter, several query paths" pattern, same as kaikki.org):
`translations[]` for `/translations`, `inflections_repl` for
`/inflections`, and (via the entry id) a follow-up `speak.audio.v2.php`
call for `/tts`.

## lp/dir (task 1.1)

Confirmed live against the real API (not guessed): `lp=DEEN` (DE↔EN),
`lp=ENNO` (EN↔NO), `lp=DENO` (DE↔NO) — `lp=NODE` does not work, `DENO` is
the only valid order for the Norwegian↔German pair. `dir=1` means the
input word (`s` param) is on the *first* language of `lp`; `dir=2` means
it's on the second — confirmed by both directions on all three pairs.

## Inflection table parsing (task 1.3)

Confirmed shapes, live:
- `NOUN`, Norwegian 4-slot: `indefinite.sg | definite.sg | indefinite.pl |
  definite.pl` (e.g. "kalv"/"hus") — maps onto
  `substantiv {article, sg_indef, sg_def, pl_indef, pl_def}` directly.
- `NOUN`, German 2-slot: `sg | pl` only, no indefinite/definite split
  (e.g. "Haus": "das Haus | die Häuser") — maps onto `sg_indef`/`pl_indef`
  only; `sg_def`/`pl_def` are legitimately absent, not a parsing gap.
- `VERB`, German 3-slot: `infinitive | preterite | pp` (no `presens` slot —
  German doesn't have one fixed present-tense form the way this table
  format expects) and Norwegian 4-slot: `å infinitive | present |
  preterite | pp` — both map onto `verb {infinitiv, presens, preteritum,
  perfektum}` (presens omitted when absent).
- A single query can return *multiple* POS blocks (e.g. "gehen" is both a
  German verb and, as "das Gehen", a noun) — each becomes its own
  candidate, same "never auto-pick" philosophy as every other
  `/inflections` provider.
- `ADJ` (and anything else) is NOT parsed: its declension sub-structure
  (German strong/weak forms split across three sub-blocks, confirmed live
  against "schön") isn't a clean single pipe-delimited label line, and
  doesn't map onto this service's Norwegian-shaped `adjektiv` keys anyway.
  Parsing stops at the first unrecognized POS block — best-effort, not a
  guess.
"""

from __future__ import annotations

import html
import re

import requests

from audio_cache import store
from cache import ProviderLookupError
from db.session import session_scope
from registry import registry

_APP_VERSION_CODE = "260804"
_TRANSLATIONS_URL = "https://www.dict.cc/syn/app_translations.php"
_AUDIO_URL = "https://audio.dict.cc/speak.audio.v2.php"
_HEADERS = {"User-Agent": "Mozilla/5.0"}

# {(from, to): (lp, dir)} — dir is which side of `lp` the FROM language is
# on. Only pairs this service actually has data for (D-DC2) — anything
# else is a clear "unsupported pair" error, not a guess.
_PAIRS = {
    ("de", "en"): ("DEEN", 1),
    ("en", "de"): ("DEEN", 2),
    ("en", "nb"): ("ENNO", 1),
    ("nb", "en"): ("ENNO", 2),
    ("de", "nb"): ("DENO", 1),
    ("nb", "de"): ("DENO", 2),
}

# For /tts and /inflections, which take a single `lang`, not a pair: any
# confirmed lp/dir that puts `lang` on one side works as a self-lookup.
_LANG_SELF_LOOKUP = {
    "nb": ("ENNO", 2),
    "en": ("ENNO", 1),
    "de": ("DEEN", 1),
}

# Norwegian's human-voice recording is confirmed (api.md); other
# languages' voice names aren't — skip the synthetic candidate rather than
# guess one.
_VOICE_FOR_LANG = {"nb": "Liv"}
_DICTCC_LANG_CODE = {"nb": "NO", "en": "EN", "de": "DE"}

_POS_BLOCK_RE = re.compile(r"<b>(NOUN|VERB|ADJ|ADV)</b>(?:\s|&nbsp;)*([^<]*)")

_NOUN_LABELS = {
    "sg": "sg_indef",
    "pl": "pl_indef",
    "indefinite.sg": "sg_indef",
    "definite.sg": "sg_def",
    "indefinite.pl": "pl_indef",
    "definite.pl": "pl_def",
}
_VERB_LABELS = {
    "infinitive": "infinitiv",
    "present": "presens",
    "preterite": "preteritum",
    "pp": "perfektum",
}
_ENTRY_POS = {"NOUN": "substantiv", "VERB": "verb"}


class UnsupportedPairError(ProviderLookupError):
    pass


def _get_json(params: dict) -> dict:
    try:
        resp = requests.get(
            _TRANSLATIONS_URL, params={**params, "appversioncode": _APP_VERSION_CODE},
            headers=_HEADERS, timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except (requests.RequestException, ValueError) as exc:
        raise ProviderLookupError(f"dict.cc request failed: {exc}") from exc


def _normalize_label(label: str) -> str:
    label = label.strip()
    label = re.sub(r"^(article|å)\s+", "", label)
    return label


def _parse_inflection_blocks(inflections_info: str, inflections_repl: str) -> list[dict]:
    if not inflections_info or not inflections_repl:
        return []

    # html.unescape FIRST: naively splitting on ";" would also split inside
    # "&nbsp;" (which contains its own semicolon), shifting every segment
    # after the first by one slot — found live, where "kalv"'s inflection
    # table came back with every value one slot off (e.g. the indefinite
    # singular's value landing under "definite.sg").
    segments = [s.strip() for s in html.unescape(inflections_repl).split(";")]
    seg_idx = 0
    candidates = []

    for m in _POS_BLOCK_RE.finditer(inflections_info):
        pos_tag, label_line = m.group(1), m.group(2)
        labels = [_normalize_label(l) for l in label_line.split("|")]
        n = len(labels)
        block_segments = segments[seg_idx:seg_idx + n]
        seg_idx += n

        if pos_tag not in _ENTRY_POS:
            break  # unrecognized/complex shape (e.g. ADJ) — stop, best-effort

        label_map = _NOUN_LABELS if pos_tag == "NOUN" else _VERB_LABELS
        paradigm = {}
        article = None
        for label, seg in zip(labels, block_segments):
            key = label_map.get(label)
            if key is None:
                continue
            parts = seg.split("\t")
            if len(parts) < 2:
                continue
            display, clean = parts[0].strip(), parts[1].strip()
            if not clean or clean == "-":
                continue
            paradigm[key] = clean
            if key == "sg_indef" and article is None:
                tokens = display.split()
                if len(tokens) > 1:
                    article = tokens[0]

        if pos_tag == "NOUN" and article:
            paradigm = {"article": article, **paradigm}
        candidates.append({"pos": _ENTRY_POS[pos_tag], "paradigm": paradigm})

    return candidates


class DictccApiTranslateAdapter:
    def lookup(self, input_dict: dict) -> dict:
        from_lang, to_lang = input_dict["from"], input_dict["to"]
        pair = _PAIRS.get((from_lang, to_lang))
        if pair is None:
            raise UnsupportedPairError(f"dictcc_api does not support the ({from_lang}, {to_lang}) pair")
        lp, dir_ = pair

        data = _get_json({"s": input_dict["text"], "dir": dir_, "lp": lp})
        translations = data.get("translations", [])
        if not translations:
            return {"text": ""}

        best = translations[0]
        text = best["term2"] if dir_ == 1 else best["term1"]
        result = {"text": text}
        entry_type = best.get("entry_type")
        if entry_type:
            result["context"] = f"[{entry_type}]"
        return result


class DictccApiInflectAdapter:
    def lookup(self, input_dict: dict) -> dict:
        word, lang = input_dict["word"], input_dict["lang"]
        lookup_pair = _LANG_SELF_LOOKUP.get(lang)
        if lookup_pair is None:
            raise UnsupportedPairError(f"dictcc_api does not support language {lang!r}")
        lp, dir_ = lookup_pair

        data = _get_json({"s": word, "dir": dir_, "lp": lp})
        blocks = _parse_inflection_blocks(data.get("inflections_info", ""), data.get("inflections_repl", ""))
        candidates = [{"lemma": word, **block} for block in blocks]
        return {"candidates": candidates}


class DictccApiTtsAdapter:
    def lookup(self, input_dict: dict) -> dict:
        word, lang = input_dict["text"], input_dict["lang"]
        lookup_pair = _LANG_SELF_LOOKUP.get(lang)
        if lookup_pair is None:
            raise UnsupportedPairError(f"dictcc_api does not support language {lang!r}")
        lp, dir_ = lookup_pair
        dictcc_lang = _DICTCC_LANG_CODE[lang]

        data = _get_json({"s": word, "dir": dir_, "lp": lp})
        translations = data.get("translations", [])
        if not translations:
            return {"candidates": []}
        entry_id = translations[0]["id"]

        candidates = []
        with session_scope() as db:
            human = self._fetch_audio(
                {"id": entry_id, "lang": f"{dictcc_lang}_rec_ip", "lp": lp, "text": word}
            )
            if human is not None:
                sha256 = store(db, human, "audio/mpeg")
                candidates.append({"sha256": sha256, "source": "human"})

            voice = _VOICE_FOR_LANG.get(lang)
            if voice:
                synthetic = self._fetch_audio({"id": entry_id, "lang": dictcc_lang, "lp": lp, "voice": voice})
                if synthetic is not None:
                    sha256 = store(db, synthetic, "audio/mpeg")
                    candidates.append({"sha256": sha256, "source": "synthetic", "voice": voice})

        return {"candidates": candidates}

    def _fetch_audio(self, params: dict) -> bytes | None:
        try:
            resp = requests.get(
                _AUDIO_URL,
                params={**params, "error_as_text": "1", "type": "mp3", "appversioncode": _APP_VERSION_CODE},
                headers=_HEADERS, timeout=10,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise ProviderLookupError(f"dict.cc audio request failed: {exc}") from exc
        # error_as_text=1 makes dict.cc return a plain-text error instead of
        # a failed download — a short non-audio response, not an HTTP error.
        if resp.headers.get("Content-Type", "").startswith("text/"):
            return None
        return resp.content


registry.register("translations", "dictcc_api", DictccApiTranslateAdapter())
registry.register("inflections", "dictcc_api", DictccApiInflectAdapter())
registry.register("tts", "dictcc_api", DictccApiTtsAdapter())
