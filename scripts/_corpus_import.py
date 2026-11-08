"""
scripts/_corpus_import.py — shared bulk-insert/index-build helpers for
`scripts/import_tatoeba.py` and `scripts/import_leipzig.py`, since both
load into the same `corpus_sentence` table (examples-api design D4) and
share the same import shape: delete only their own `corpus` partition(s),
bulk-insert with `word_count`/`tsv` computed per row, then build the GIN
index once at the end.

`tsv` is computed here, not by the migration, and the index is created
after the bulk insert (not before) — a GIN build over ~3M rows is the
slow step of the whole import, and building it row-by-row during a bulk
insert, or against an empty table at migration time, would both be
strictly slower than building it once over the finished data.
"""

from __future__ import annotations

import time

from psycopg2.extras import execute_values


def delete_corpus_partitions(conn, corpora: list[str]) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM corpus_sentence WHERE corpus = ANY(%s)", (corpora,))


def insert_sentences(conn, rows, *, batch_size: int = 5000) -> int:
    """`rows` yields `(corpus, ext_id, text, word_count)` tuples. `tsv` is
    computed in SQL (`to_tsvector('simple', text)`) rather than in Python,
    per design D3's `simple`-config decision."""
    total = 0
    batch = []
    with conn.cursor() as cur:
        for corpus, ext_id, sentence_text, word_count in rows:
            batch.append((corpus, ext_id, sentence_text, word_count, sentence_text))
            if len(batch) >= batch_size:
                execute_values(
                    cur,
                    "INSERT INTO corpus_sentence (corpus, ext_id, text, word_count, tsv) VALUES %s",
                    batch,
                    template="(%s, %s, %s, %s, to_tsvector('simple', %s))",
                )
                total += len(batch)
                batch.clear()
        if batch:
            execute_values(
                cur,
                "INSERT INTO corpus_sentence (corpus, ext_id, text, word_count, tsv) VALUES %s",
                batch,
                template="(%s, %s, %s, %s, to_tsvector('simple', %s))",
            )
            total += len(batch)
    return total


def ensure_gin_index(conn) -> None:
    start = time.monotonic()
    with conn.cursor() as cur:
        cur.execute("CREATE INDEX IF NOT EXISTS ix_corpus_sentence_tsv ON corpus_sentence USING gin(tsv)")
    elapsed = time.monotonic() - start
    print(f"corpus_sentence GIN index build: {elapsed:.1f}s")
