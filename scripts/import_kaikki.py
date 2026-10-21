"""
scripts/import_kaikki.py — one-shot import of the kaikki.org/Wiktionary
Norwegian Bokmål dump into `kaikki_entry` (task 3.6).

One row per dump entry (word+pos), keeping `forms` and `sounds` as-imported
jsonb so `/ipa` and `/tts`'s later kaikki adapters can query the same
table (D-S4) instead of re-parsing the 80MB dump a second and third time.

`forms` is filtered at import time, not query time: any form tagged
`imperative` or `passive` is dropped before it's stored, per the
inflect-api spec's "kaikki candidate excludes imperative/passive forms"
requirement — there's no use for those tags outside `/inflect`, and
dropping them here means every reader downstream only ever sees
paradigm-shape-compatible forms.

Run: python -m scripts.import_kaikki providers/kaikii/kaikki.org-dictionary-NorwegianBokmål.jsonl
"""

from __future__ import annotations

import argparse
import json
import re

from psycopg2.extras import Json, execute_values

from db.session import get_engine

_EXCLUDED_FORM_TAGS = {"imperative", "passive"}

_GENDER_TEMPLATE_RE = re.compile(r"^nb-noun-([mfn])\d*$")


def _gender_for(entry: dict) -> str | None:
    if entry.get("pos") != "noun":
        return None
    word = entry.get("word", "")
    for ht in entry.get("head_templates", []):
        g = ht.get("args", {}).get("g")
        if g in ("m", "f", "n"):
            return g
        m = _GENDER_TEMPLATE_RE.match(ht.get("name", ""))
        if m:
            return m.group(1)
        exp = ht.get("expansion", "")
        m2 = re.match(re.escape(word) + r" ([mfn]) \(", exp)
        if m2:
            return m2.group(1)
    return None


def _filtered_forms(entry: dict) -> list[dict]:
    return [
        f for f in entry.get("forms", [])
        if not (_EXCLUDED_FORM_TAGS & set(f.get("tags", [])))
    ]


def run(jsonl_path: str, batch_size: int = 2000) -> None:
    engine = get_engine()
    conn = engine.raw_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE kaikki_entry")

        total = 0
        batch = []
        with open(jsonl_path, encoding="utf-8") as f, conn.cursor() as cur:
            for line in f:
                entry = json.loads(line)
                batch.append((
                    entry.get("word", ""),
                    entry.get("pos", ""),
                    _gender_for(entry),
                    Json(_filtered_forms(entry)),
                    Json(entry.get("sounds", [])),
                ))
                if len(batch) >= batch_size:
                    execute_values(
                        cur,
                        "INSERT INTO kaikki_entry (word, pos, gender, forms, sounds) VALUES %s",
                        batch,
                    )
                    total += len(batch)
                    batch.clear()
            if batch:
                execute_values(
                    cur,
                    "INSERT INTO kaikki_entry (word, pos, gender, forms, sounds) VALUES %s",
                    batch,
                )
                total += len(batch)

        conn.commit()
        print(f"kaikki_entry: {total}")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("jsonl_path", help="path to the kaikki.org Norwegian Bokmål dictionary dump")
    args = parser.parse_args()
    run(args.jsonl_path)


if __name__ == "__main__":
    main()
