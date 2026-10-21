"""
scripts/import_ipadict.py — import ipa-dict/nb (`providers/open-dict/nb.txt`,
tab-separated `word\\t/ipa/`) into `ipa_dict_entry` (task 4.5's local part).
Small (~10k lines); a thin lemma-only fallback /ipa provider.

Run: python -m scripts.import_ipadict providers/open-dict/nb.txt
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
            word, ipa = line.split("\t", 1)
            # entries look like "/ɑbɔɾ/" or "/x/, /y/" for alternate pronunciations
            for variant in ipa.split(", "):
                rows.append((word, variant.strip().strip("/")))

    engine = get_engine()
    conn = engine.raw_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE ipa_dict_entry")
            execute_values(cur, "INSERT INTO ipa_dict_entry (wordform, ipa) VALUES %s", rows)
        conn.commit()
        print(f"ipa_dict_entry: {len(rows)}")
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
