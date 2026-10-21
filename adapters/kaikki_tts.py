"""
adapters/kaikki_tts.py — the `kaikki` /tts provider: downloads the real
recordings referenced by `kaikki_entry.sounds[].mp3_url` (D-S4, same shared
table as the `/inflections` and `/ipa` kaikki adapters) and stores them in
smia's private audio cache. One candidate per `sounds[]` entry that has an
`mp3_url` (a word can have more than one recording — tts-api spec's
"one candidate per recording" rule).
"""

from __future__ import annotations

import requests
from sqlalchemy import text

from audio_cache import store
from cache import ProviderLookupError
from db.session import session_scope
from registry import registry

# Wikimedia Commons (where kaikki.org's mp3_urls point) rejects requests
# with no User-Agent or a generic one (its User-Agent policy requires
# identifying the client) — discovered as a live 403 when this adapter was
# first tested.
_HEADERS = {"User-Agent": "smia/0.1 (linguistics service; Tun ecosystem)"}


class KaikkiTtsAdapter:
    def lookup(self, input_dict: dict) -> dict:
        word = input_dict["text"]
        with session_scope() as db:
            rows = db.execute(
                text("SELECT sounds FROM kaikki_entry WHERE word = :word"), {"word": word}
            ).all()

            candidates = []
            for (sounds,) in rows:
                for sound in sounds:
                    mp3_url = sound.get("mp3_url")
                    if not mp3_url:
                        continue
                    try:
                        resp = requests.get(mp3_url, timeout=10, headers=_HEADERS)
                        resp.raise_for_status()
                    except requests.RequestException as exc:
                        raise ProviderLookupError(f"failed to fetch {mp3_url}: {exc}") from exc
                    sha256 = store(db, resp.content, "audio/mpeg")
                    candidates.append({"sha256": sha256})

        return {"candidates": candidates}


registry.register("tts", "kaikki", KaikkiTtsAdapter())
