"""
scripts/import_wikipron.py — import wikipron's bundled
`nob_latn_broad.tsv` (task 4.5's other local part) into `wikipron_entry`.
Format is `word\\tspace-separated-IPA-segments`; segments are joined
without spaces into one contiguous phonemic string (wikipron's segmentation
is a tokenization choice for its own tooling, not part of the IPA itself).
A word can have multiple pronunciation-variant rows (one per line) — all
are imported and the adapter returns one candidate per row.

Run: python -m scripts.import_wikipron providers/wikipron/data/scrape/tsv/nob_latn_broad.tsv
"""

from __future__ import annotations

import argparse

from psycopg2.extras import execute_values

from db.session import get_engine


def run(path: str) -> None:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line:
                continue
            word, segments = line.split("\t", 1)
            rows.append((word, segments.replace(" ", "")))

    engine = get_engine()
    conn = engine.raw_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE wikipron_entry")
            execute_values(cur, "INSERT INTO wikipron_entry (wordform, ipa) VALUES %s", rows)
        conn.commit()
        print(f"wikipron_entry: {len(rows)}")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path")
    args = parser.parse_args()
    run(args.path)


if __name__ == "__main__":
    main()
