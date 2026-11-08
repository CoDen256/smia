"""
scripts/import_tatoeba.py — one-shot import of Tatoeba's Norwegian Bokmål
sentence export into `corpus_sentence` (examples-api task 2.1), with
`corpus='tatoeba'`.

Reads the bz2 archive directly (no manual unpack) — `id \\t lang \\t text`,
18,898 rows expected. Only deletes its own `corpus='tatoeba'` partition
(not the whole shared table) so a reimport doesn't disturb `leipzig`'s rows.

Run: python -m scripts.import_tatoeba providers/tatoeba/nob_sentences.tsv.bz2
"""

from __future__ import annotations

import argparse
import bz2

from db.session import get_engine
from scripts._corpus_import import delete_corpus_partitions, ensure_gin_index, insert_sentences


def _rows(tsv_bz2_path: str):
    with bz2.open(tsv_bz2_path, "rt", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line:
                continue
            ext_id, _lang, sentence_text = line.split("\t", 2)
            word_count = len(sentence_text.split())
            yield "tatoeba", ext_id, sentence_text, word_count


def run(tsv_bz2_path: str) -> None:
    engine = get_engine()
    conn = engine.raw_connection()
    try:
        delete_corpus_partitions(conn, ["tatoeba"])
        total = insert_sentences(conn, _rows(tsv_bz2_path))
        print(f"corpus_sentence (tatoeba): {total}")
        ensure_gin_index(conn)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tsv_bz2_path", help="path to nob_sentences.tsv.bz2")
    args = parser.parse_args()
    run(args.tsv_bz2_path)


if __name__ == "__main__":
    main()
