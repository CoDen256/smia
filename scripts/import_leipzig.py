"""
scripts/import_leipzig.py — one-shot import of the three Leipzig Corpora
Collection Norwegian Bokmål archives into `corpus_sentence` (examples-api
task 2.2), mapped to `corpus` values `web_2020`/`news_2013`/`wikipedia_2014`.

Each archive bundles its own co-occurrence/inverted-index products
(`-inv_w.txt`, `-co_s.txt`, `-co_n.txt`, `-words.txt`, `-sources.txt`,
`-inv_so.txt`, `-import.sql`) alongside the one file this change actually
needs — `*-sentences.txt` (`id \\t sentence`). Only that member is ever
extracted; the rest (~1.9 GB of the ~2.2 GB unpacked footprint) is Leipzig's
own index, which this change replaces with a Postgres GIN index instead
(proposal's Impact section). 1,000,000 rows expected per archive.

Deletes only the three Leipzig `corpus` partitions (not `tatoeba`'s), so a
reimport of one doesn't disturb the other.

Run:
  python -m scripts.import_leipzig \\
    providers/leipzig/nob-no_web_2020_1M.tar.gz \\
    providers/leipzig/nob_news_2013_1M.tar.gz \\
    providers/leipzig/nob_wikipedia_2014_1M.tar.gz
"""

from __future__ import annotations

import argparse
import tarfile

from db.session import get_engine
from scripts._corpus_import import delete_corpus_partitions, ensure_gin_index, insert_sentences

# filename substring -> corpus value
_CORPUS_FOR_SUBSTRING = (
    ("web_2020", "web_2020"),
    ("news_2013", "news_2013"),
    ("wikipedia_2014", "wikipedia_2014"),
)


def _corpus_for_path(path: str) -> str:
    for substring, corpus in _CORPUS_FOR_SUBSTRING:
        if substring in path:
            return corpus
    raise ValueError(f"cannot determine Leipzig corpus from filename: {path}")


def _sentences_member(tar: tarfile.TarFile) -> str:
    for name in tar.getnames():
        if name.endswith("-sentences.txt"):
            return name
    raise FileNotFoundError("no *-sentences.txt member found in archive")


def _rows(archive_path: str, corpus: str):
    with tarfile.open(archive_path, "r:gz") as tar:
        member = _sentences_member(tar)
        f = tar.extractfile(member)
        for raw_line in f:
            line = raw_line.decode("utf-8").rstrip("\n")
            if not line:
                continue
            ext_id, sentence_text = line.split("\t", 1)
            word_count = len(sentence_text.split())
            yield corpus, ext_id, sentence_text, word_count


def run(*archive_paths: str) -> None:
    engine = get_engine()
    conn = engine.raw_connection()
    try:
        corpora = [_corpus_for_path(p) for p in archive_paths]
        delete_corpus_partitions(conn, corpora)
        for archive_path, corpus in zip(archive_paths, corpora):
            total = insert_sentences(conn, _rows(archive_path, corpus))
            print(f"corpus_sentence ({corpus}): {total}")
        ensure_gin_index(conn)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archives", nargs="+", help="path(s) to Leipzig *_1M.tar.gz archives")
    args = parser.parse_args()
    run(*args.archives)


if __name__ == "__main__":
    main()
