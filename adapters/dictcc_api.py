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
# `nb` gets two entries — dict.cc has no monolingual Norwegian dictionary,
# only bilingual pairs, so a word filed only under NO<->EN (not NO<->DE)
# would otherwise never be found (dictcc-norwegian-multi-pair). `en`/`de`
# keep a single pair each — this service only cares about their Norwegian-
# touching side.
_LANG_SELF_LOOKUP_PAIRS: dict[str, list[tuple[str, int]]] = {
    "nb": [("DENO", 2), ("ENNO", 1)],
    "en": [("ENNO", 1)],
    "de": [("DEEN", 1)],
}

# Norwegian's human-voice recording is confirmed (api.md); other
# languages' voice names aren't — skip the synthetic candidate rather than
# guess one.
_VOICE_FOR_LANG = {"nb": "Liv"}
_DICTCC_LANG_CODE = {"nb": "NO", "en": "EN", "de": "DE"}

_POS_MAP = {
    "NOUN": "substantiv",
    "VERB": "verb",
    "ADJ": "adjektiv",
}

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
_ADJ_LABELS = {
    "m/f": "positiv",
    "n": "nøytrum",
    "pl/definite": "flertall",
    "comparative": "komparativ",
    "superlative": "superlativ",
}


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


_ANNOTATION_RE = re.compile(r"[\{\[][^}\]]*[\}\]]")


def _strip_infinitive_marker(phrase: str) -> str:
    return phrase[2:].lstrip() if phrase.lower().startswith("å ") else phrase


def _normalize_dictcc_phrase(phrase: str) -> str:
    """For comparing a dict.cc source-language field against the bare query
    word: strips grammar annotations dict.cc appends to the word itself
    (`"kalv {m}"` -> `"kalv"`) and the verb infinitive marker (`"å komme"`
    -> `"komme"`), so a direct word match isn't mistaken for a distinct
    phrase just because of that annotation/marker."""
    return _strip_infinitive_marker(_ANNOTATION_RE.sub("", phrase).strip()).strip().lower()


def _display_dictcc_phrase(phrase: str) -> str:
    """For showing a source phrase as context: only strips the infinitive
    marker (annotations like "{m}" are kept — they're part of what's
    actually being displayed, unlike in `_normalize_dictcc_phrase`)."""
    return _strip_infinitive_marker(phrase)



def _parse_inflection_blocks(inflections: str) -> list[dict]:
    if not inflections:
        return []

    candidates = []
    row_pattern = re.compile(r'<tr[^>]*title="([^"]*)"[^>]*>(.*?)</tr>', re.DOTALL)

    for m_row in row_pattern.finditer(inflections):
        title_attr = html.unescape(m_row.group(1))
        row_content = m_row.group(2)

        pos_m = re.search(r'<b>(NOUN|VERB|ADJ|ADV)</b>', row_content)
        if not pos_m:
            continue
        pos_tag = pos_m.group(1)
        if pos_tag not in _POS_MAP:
            continue

        # Extract all table cells and grab the inflection data cell dynamically (independent of attributes)
        tds = re.findall(r'<td[^>]*>(.*?)</td>', row_content, re.DOTALL)
        cell_html = tds[-1] if tds else ""

        # Normalize pipe separators into a common delimiter
        normalized_cells = re.sub(r'<span[^>]*class=["\']infl_pipe["\'][^>]*>\s*\|\s*</span>', '|||', cell_html)
        normalized_cells = normalized_cells.replace('|', '|||')

        cell_list = normalized_cells.split('|||')
        segments = []
        for cell in cell_list:
            # Split individual cell content by <br> if a cell spans multiple labels
            sub_parts = re.split(r'<br\s*/?>', cell, flags=re.IGNORECASE)
            for part in sub_parts:
                clean_part = re.sub(r'<[^>]+>', '', part)
                clean_part = html.unescape(clean_part)
                clean_part = re.sub(r'\s+', ' ', clean_part).strip()
                if clean_part:
                    segments.append(clean_part)

        # Extract and expand labels from the title attribute
        raw_labels = [l.strip() for l in title_attr.split("|")]
        has_article = any("article" in l.lower() for l in raw_labels)

        expanded_labels = []
        for l in raw_labels:
            clean_l = l.replace("article", "").strip().lower()
            if not clean_l:
                continue
            if "pl/definitecomparative" in clean_l:
                expanded_labels.extend(["pl/definite", "comparative"])
            else:
                expanded_labels.append(clean_l.replace("å ", ""))

        label_map = {
            "NOUN": _NOUN_LABELS,
            "VERB": _VERB_LABELS,
            "ADJ": _ADJ_LABELS,
        }[pos_tag]

        paradigm = {}
        for label, seg in zip(expanded_labels, segments):
            key = label_map.get(label)
            if not key or not seg or seg == "-":
                continue

            if pos_tag == "NOUN" and key == "sg_indef" and has_article:
                tokens = seg.split(maxsplit=1)
                if len(tokens) > 1:
                    paradigm["article"] = tokens[0]
                    paradigm[key] = tokens[1]
                else:
                    paradigm[key] = seg
            elif pos_tag == "VERB" and key == "infinitiv":
                paradigm[key] = re.sub(r'^å\s+', '', seg)
            else:
                paradigm[key] = seg

        candidates.append({"pos": _POS_MAP[pos_tag], "paradigm": paradigm})

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

        # Group by (entry_type, source phrase) — translate-multi-candidate
        # D-TM1/D-TM2 — NOT by entry_type alone (the earlier approach):
        # live-confirmed querying "komme" returns 18 entries all tagged
        # "verb", covering a dozen distinct phrasal-verb senses ("å komme",
        # "å komme over", "å komme i vei", ...), which entry_type-only
        # grouping collapsed into one unreadable giant candidate. The
        # source-language field (the side matching the query's language —
        # term2 here, term1 if dir_==1) is dict.cc's own notion of "which
        # exact phrase was matched"; only entries matching the identical
        # source phrase (verbatim string — e.g. three entries all reading
        # "å komme i vei") are true same-sense synonyms and join with "/".
        # Entries sharing just an entry_type but a different source phrase
        # become separate candidates, each carrying that phrase in its
        # context so it's clear which bigger expression it came from.
        text_field = "term2" if dir_ == 1 else "term1"
        source_field = "term1" if dir_ == 1 else "term2"
        query_norm = _normalize_dictcc_phrase(input_dict["text"])

        groups: dict[tuple[str | None, str], list[str]] = {}
        order: list[tuple[str | None, str]] = []
        for entry in translations:
            entry_type = entry.get("entry_type") or None
            source = entry[source_field] # term2
            key = (entry_type, source)
            if key not in groups:
                groups[key] = []
                order.append(key)
            groups[key].append(entry[text_field])

        candidates = []
        for entry_type, source in order:
            candidate = {"text": "/".join(groups[(entry_type, source)])}
            context_parts = []
            if entry_type:
                context_parts.append(f"[{entry_type}]")
            # Only surface the source phrase when it's more than the bare
            # query word (stripped of dict.cc's own grammar annotations
            # like "{m}" and the verb infinitive marker "å ") — a direct
            # word match doesn't need its own text echoed back.
            if _normalize_dictcc_phrase(source) != query_norm:
                context_parts.append(_display_dictcc_phrase(source))
            elif source:
                context_parts.append(f"{source}")

            if context_parts:
                candidate["context"] = " ".join(context_parts)
            candidates.append(candidate)
        return {"candidates": candidates}


class DictccApiInflectAdapter:
    def lookup(self, input_dict: dict) -> dict:
        word, lang = input_dict["word"], input_dict["lang"]
        pairs = _LANG_SELF_LOOKUP_PAIRS.get(lang)
        if pairs is None:
            raise UnsupportedPairError(f"dictcc_api does not support language {lang!r}")

        # Each Norwegian-touching pair is an independent dataset — a pair
        # with no table for this word is a normal empty result, not a
        # failure; only every pair erroring out fails the whole lookup
        # (dictcc-norwegian-multi-pair design.md D2), so one pair's
        # transient hiccup doesn't sink a lookup the other pair would have
        # answered.
        candidates: list[dict] = []
        seen: set[tuple] = set()
        errors: list[ProviderLookupError] = []
        for lp, dir_ in pairs:
            try:
                data = _get_json({"s": word, "dir": dir_, "lp": lp})
            except ProviderLookupError as exc:
                errors.append(exc)
                continue
            blocks = _parse_inflection_blocks(data.get("inflections"))
            for block in blocks:
                candidate = {"lemma": word, **block}
                # Identity for dedup is (pos, paradigm) — two pairs
                # resolving to the exact same table collapse into one
                # candidate; different paradigms for the same lemma (one
                # pair fills a gap the other has) both survive, same as any
                # other inflections provider's "never silently merge"
                # philosophy.
                key = (candidate["pos"], tuple(sorted(candidate["paradigm"].items())))
                if key in seen:
                    continue
                seen.add(key)
                candidates.append(candidate)

        if errors and len(errors) == len(pairs):
            raise errors[0]

        return {"candidates": candidates}


class DictccApiTtsAdapter:
    def lookup(self, input_dict: dict) -> dict:
        word, lang = input_dict["text"], input_dict["lang"]
        pairs = _LANG_SELF_LOOKUP_PAIRS.get(lang)
        if pairs is None:
            raise UnsupportedPairError(f"dictcc_api does not support language {lang!r}")
        dictcc_lang = _DICTCC_LANG_CODE[lang]

        candidates: list[dict] = []
        seen_sha: set[str] = set()
        errors: list[ProviderLookupError] = []
        with session_scope() as db:
            for lp, dir_ in pairs:
                try:
                    data = _get_json({"s": word, "dir": dir_, "lp": lp})
                    translations = data.get("translations", [])
                    if not translations:
                        continue
                    entry_id = translations[0]["id"]

                    human = self._fetch_audio(
                        {"id": entry_id, "lang": f"{dictcc_lang}_rec_ip", "lp": lp, "text": word}
                    )
                    if human is not None:
                        sha256 = store(db, human, "audio/mpeg")
                        if sha256 not in seen_sha:
                            seen_sha.add(sha256)
                            candidates.append({"sha256": sha256, "source": "human"})

                    voice = _VOICE_FOR_LANG.get(lang)
                    if voice:
                        synthetic = self._fetch_audio({"id": entry_id, "lang": dictcc_lang, "lp": lp, "voice": voice})
                        if synthetic is not None:
                            sha256 = store(db, synthetic, "audio/mpeg")
                            # Content-addressed identity (audio_cache.store)
                            # is enough dedup — two pairs resolving to
                            # byte-identical audio collapse naturally.
                            if sha256 not in seen_sha:
                                seen_sha.add(sha256)
                                candidates.append({"sha256": sha256, "source": "synthetic", "voice": voice})
                except ProviderLookupError as exc:
                    errors.append(exc)
                    continue

        if errors and len(errors) == len(pairs):
            raise errors[0]

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
