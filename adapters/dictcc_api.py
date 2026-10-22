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

## Why this adapter stays on raw HTTP (`provider-client-policy`)

No published client exists for dict.cc's mobile-app backend at all — it's
a reverse-engineered, undocumented surface (`app_translations.php` /
`speak.audio.v2.php`), not a product dict.cc publishes an SDK for. Nothing
to swap to.
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
    while segments and not segments[-1]:
        segments.pop()  # trailing empty segment after the format's final ";"

    blocks = list(_POS_BLOCK_RE.finditer(inflections_info))
    seg_idx = 0
    candidates = []

    for block_num, m in enumerate(blocks):
        pos_tag, label_line = m.group(1), m.group(2)
        labels = [_normalize_label(l) for l in label_line.split("|")]
        n = len(labels)

        if pos_tag not in _ENTRY_POS:
            break  # unrecognized/complex shape (e.g. ADJ) — stop, best-effort

        # The raw HTML (`inflections`, not `inflections_repl`) shows a cell
        # can itself hold multiple alternates joined by "/" — e.g. "hus"'s
        # definite-plural cell is literally "husa / husene" one cell, one
        # label. `inflections_repl` flattens that into an extra ";"-
        # delimited segment with no label of its own, which a strict
        # 1-segment-per-label read silently dropped (confirmed live,
        # comparing the two fields side by side). Only the LAST block can
        # safely claim its leftover segments — if another recognized block
        # follows, exactly `n` segments are consumed to not misalign it.
        is_last_block = block_num == len(blocks) - 1
        block_segments = segments[seg_idx:] if is_last_block else segments[seg_idx:seg_idx + n]
        seg_idx += len(block_segments)
        extra_segments, block_segments = block_segments[n:], block_segments[:n]

        label_map = _NOUN_LABELS if pos_tag == "NOUN" else _VERB_LABELS
        values_by_key: dict[str, list[str]] = {}
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
            values_by_key[key] = [clean]
            if key == "sg_indef" and article is None:
                tokens = display.split()
                if len(tokens) > 1:
                    article = tokens[0]

        last_key = label_map.get(labels[-1]) if labels else None
        for seg in extra_segments:
            parts = seg.split("\t")
            if len(parts) < 2 or last_key is None:
                continue
            clean = parts[1].strip()
            if clean and clean != "-":
                values_by_key.setdefault(last_key, []).append(clean)

        paradigm = {key: " / ".join(values) for key, values in values_by_key.items()}
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
            return {"candidates": []}

        # Group by entry_type (translate-multi-candidate D-TM1/D-TM2):
        # every entry reaches the caller, nothing picked or dropped —
        # same-entry_type entries join into one candidate's text with "/";
        # different entry_types become separate candidates. Order follows
        # dict.cc's own translations[] order (its sort_num ranking), via
        # first-seen insertion order of each entry_type group.
        text_field = "term2" if dir_ == 1 else "term1"
        source_field = "term1" if dir_ == 1 else "term2"

        texts_by_type: dict[str | None, list[str]] = {}
        # entry_type is "" (not just absent) for idiom/phrase entries
        # dict.cc doesn't tag with a POS at all — e.g. querying "igjen"
        # (just the word) surfaces "Kom igjen!" -> "Come on!" among the
        # results, an entry_type-less phrase entry that happens to contain
        # the query word, not a sense of "igjen" itself. A bare
        # untagged "Come on!" candidate reads as an unexplained mismatch;
        # the actual matched phrase (the source-language field, e.g.
        # "Kom igjen!") is kept here as that candidate's context so it's
        # clear which bigger phrase this translation came from (confirmed
        # live against the real API, not guessed).
        phrases_by_untyped: list[str] = []
        for entry in translations:
            entry_type = entry.get("entry_type") or None
            texts_by_type.setdefault(entry_type, []).append(entry[text_field])
            if entry_type is None:
                phrases_by_untyped.append(entry[source_field])

        candidates = []
        for entry_type, texts in texts_by_type.items():
            candidate = {"text": "/".join(texts)}
            if entry_type:
                candidate["context"] = f"[{entry_type}]"
            elif phrases_by_untyped:
                candidate["context"] = "/".join(phrases_by_untyped)
            candidates.append(candidate)
        return {"candidates": candidates}


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
