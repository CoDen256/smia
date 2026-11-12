"""
adapters/_lexin.py — shared client for LEXIN (lexin.oslomet.no), used by the
`lexin` /translations, /ipa and /examples adapters (lexin-provider design D1).
Not an adapter: nothing registers from here.

The API is undocumented. One GET returns a flat list of rows
`{id, sub_id, type, text}` where `type` is `<prefix>-<field>` (`N-`/`E-` for
the Norwegian dictionary, `B-` for the English one). Rows of one entry share
an `id` but are NOT contiguous, so entries are grouped by `id` (design D3).

A request without `Origin: https://lexin.oslomet.no` is refused — sometimes as
HTTP 200 `{"err": "Access denied", "error_exist": true}`, sometimes as HTTP
403. Either way that is a provider failure and must never look like an empty
result, or the lookup cache would remember "no answer" (design D2).
"""

from __future__ import annotations

import os
import re
import threading
import time
from dataclasses import dataclass, field

import requests

from cache import ProviderLookupError

_URL = "https://editorportal.oslomet.no/api/v1/findwords"
_HEADERS = {
    "Origin": "https://lexin.oslomet.no",
    "User-Agent": "smia/1.0 (private research client)",
    "Accept": "application/json",
}
_TIMEOUT = 10
_DEFAULT_MIN_INTERVAL = 1.0


class UnsupportedPairError(ProviderLookupError):
    pass


# --- query preparation (design D8) ----------------------------------------

_QUERY_SEPARATORS = re.compile(r'[, ^|;/"()]+')


def prepare_query(text: str) -> str:
    """What LEXIN's own search box does before it calls the API: lowercase,
    separators and parentheses become spaces, trim."""
    return _QUERY_SEPARATORS.sub(" ", text.lower()).strip()


# --- rate limiter (design D7) -----------------------------------------------

_lock = threading.Lock()
_last_call: float | None = None
_now = time.monotonic  # patched in tests
_sleep = time.sleep


def _min_interval() -> float:
    raw = os.environ.get("LEXIN_MIN_INTERVAL_SECONDS")
    if raw is None:
        return _DEFAULT_MIN_INTERVAL
    try:
        return max(0.0, float(raw))
    except ValueError:
        return _DEFAULT_MIN_INTERVAL


def _pace() -> None:
    """Block until `min_interval` has passed since the previous LEXIN call in
    this process. The lock is held across the sleep so concurrent callers queue
    rather than all firing at once."""
    global _last_call
    with _lock:
        interval = _min_interval()
        if interval > 0 and _last_call is not None:
            wait = interval - (_now() - _last_call)
            if wait > 0:
                _sleep(wait)
        _last_call = _now()


# --- entries -----------------------------------------------------------------


@dataclass
class Entry:
    id: int
    lemma: str = ""  # as LEXIN writes it: `ut~gå`
    pos: str = ""
    definitions: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)
    inflections: list[str] = field(default_factory=list)  # raw `mor` strings
    pronunciations: list[str] = field(default_factory=list)

    @property
    def headword(self) -> str:
        """The word itself: `~` is a syllable/compound hint in the source."""
        return self.lemma.replace("~", "")

    @property
    def compound_prefix(self) -> str:
        """`ut` for `ut~gå`; what a `-går` shorthand in `mor` is attached to."""
        head, sep, _ = self.lemma.rpartition("~")
        return head.replace("~", "") if sep else ""


def _append_distinct(items: list[str], value: str) -> None:
    if value not in items:
        items.append(value)


def parse_entries(rows: list[dict]) -> list[Entry]:
    entries: dict[int, Entry] = {}
    for row in rows:
        text = (row.get("text") or "").strip()
        if not text:
            continue
        _, _, field_name = (row.get("type") or "").partition("-")
        entry = entries.setdefault(row["id"], Entry(id=row["id"]))
        if field_name == "lem":
            entry.lemma = entry.lemma or text
        elif field_name == "kat":
            entry.pos = entry.pos or text
        elif field_name == "def":
            _append_distinct(entry.definitions, text)
        elif field_name == "eks":
            _append_distinct(entry.examples, text)
        elif field_name == "mor":
            _append_distinct(entry.inflections, text)
        elif field_name == "utt":
            _append_distinct(entry.pronunciations, text)
        # sms / idi / kom / grm / alt / til / div …: not used by any kind.
    return list(entries.values())


# `mor` noise that is not a form of the word. Safe to drop from *form*
# matching because headwords are matched separately.
_MOR_NOISE = {"å", "en", "ei", "et", "har", "el", "eller", "og"}


def inflected_forms(entry: Entry) -> set[str]:
    """Casefolded forms listed in the entry's `mor` strings. A `-x` token is a
    shorthand for the compound prefix + `x` (`ut~gå`: `-går` = `utgår`)."""
    forms: set[str] = set()
    for mor in entry.inflections:
        for token in mor.replace("(", " ").replace(")", " ").split():
            token = token.casefold()
            if token in _MOR_NOISE:
                continue
            if token.startswith("-"):
                token = entry.compound_prefix.casefold() + token[1:]
            if token:
                forms.add(token)
    return forms


# --- the request ---------------------------------------------------------------


def find(word: str, select_lang: str) -> list[Entry]:
    """One paced `findwords` call. `select_lang` is LEXIN's own value for the
    target dictionary (`bokmål`, `engelsk`). Returns entries in response order;
    raises `ProviderLookupError` for any refusal or malformed reply."""
    query = prepare_query(word)
    if not query:
        return []

    _pace()
    try:
        resp = requests.get(
            _URL,
            params={
                "searchWord": query,
                "lang": "bokmål",
                "page": 1,
                "selectLang": select_lang,
                "includeEngLang": 0,
            },
            headers=_HEADERS,
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        raise ProviderLookupError(f"lexin request failed: {exc}") from exc
    except ValueError as exc:
        raise ProviderLookupError(f"lexin returned a non-JSON body: {exc}") from exc

    if not isinstance(data, dict) or data.get("error_exist") or "result" not in data:
        reason = data.get("err") if isinstance(data, dict) else None
        raise ProviderLookupError(f"lexin refused the request: {reason or 'unexpected response'}")

    result = data["result"]
    rows = result[0] if result else []
    return parse_entries(rows)
