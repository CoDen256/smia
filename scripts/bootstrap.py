"""
scripts/bootstrap.py — the Docker image's entrypoint (`CMD` in `Dockerfile`):
runs migrations, imports each provider's data only if its table is still
empty (so a container restart against an already-populated Postgres volume
doesn't re-import ~9M rows every time), then starts the Flask app.

Missing source files (e.g. `providers/` not bind-mounted) are warned about,
not fatal — the service still starts with those providers simply returning
no candidates, same as any other "unknown word" response.
"""

from __future__ import annotations

import glob
import os
import subprocess
import sys

from sqlalchemy import text

from db.session import get_engine
from scripts import (
    import_dictcc_static,
    import_ipadict,
    import_kaikki,
    import_leipzig,
    import_nst,
    import_ordbank,
    import_pygmalion,
    import_tatoeba,
    import_wikipron,
)

# dict.cc's dump filenames are download tokens, not stable names (e.g.
# "cnsfdgcgdd-8413511861-79ieio.txt") — identify NO-EN/NO-DE/DE-EN by each
# file's own header line instead of assuming a filename.
_DICTCC_PAIR_HEADERS = {
    "# NO-EN vocabulary database": "no_en",
    "# NO-DE vocabulary database": "no_de",
    "# DE-EN vocabulary database": "de_en",
}


def _find_dictcc_static_args() -> list[str]:
    args = []
    for path in sorted(glob.glob("providers/dict/*.txt")):
        with open(path, encoding="utf-8") as f:
            first_line = f.readline().strip()
        # The real dump's first line is itself two tab-separated columns
        # ("# NO-EN vocabulary database\tcompiled by dict.cc"), not the bare
        # key alone — an exact-equality match against the whole line never
        # matched any real file (confirmed: only ever silently masked by an
        # already-populated table skipping this check entirely on every
        # prior run; a genuinely empty database hits this for real).
        header = first_line.split("\t", 1)[0]
        pair = _DICTCC_PAIR_HEADERS.get(header)
        if pair:
            args += [path, pair]
    if not args:
        raise FileNotFoundError("no providers/dict/*.txt files with a recognized NO-EN/NO-DE/DE-EN header")
    return args


def _corpus_partition_empty(corpora: list[str]):
    """Returns an `is_empty` check scoped to a `corpus_sentence` partition
    — `tatoeba`/`leipzig` share one table (design D4), so a plain
    table-wide emptiness check would make importing one skip the other."""
    def _check() -> bool:
        engine = get_engine()
        with engine.connect() as conn:
            return (
                conn.execute(
                    text("SELECT COUNT(*) FROM corpus_sentence WHERE corpus = ANY(:corpora)"),
                    {"corpora": corpora},
                ).scalar()
                == 0
            )
    return _check


_IMPORTS = [
    ("ordbank_fullform", import_ordbank.run, ["providers/nbno/20220201_norsk_ordbank_nob_2005.tar.gz"]),
    ("kaikki_entry", import_kaikki.run, ["providers/kaikii/nb.jsonl"]),
    (
        "nst_lexicon",
        import_nst.run,
        ["providers/nbno/nb_uttale_tillegg.zip", "providers/nbno/nb_uttale_leksika.zip"],
    ),
    ("ipa_dict_entry", import_ipadict.run, ["providers/open-dict/nb.txt"]),
    ("wikipron_entry", import_wikipron.run, ["providers/wikipron/nob_latn_broad.tsv"]),
    ("pygmalion_audio", import_pygmalion.run, ["providers/pygmalion/audio/manifest.jsonl"]),
    ("dictcc_static_entry", import_dictcc_static.run, _find_dictcc_static_args),
    (
        _corpus_partition_empty(["tatoeba"]),
        import_tatoeba.run,
        ["providers/tatoeba/nob_sentences.tsv.bz2"],
    ),
    (
        _corpus_partition_empty(["web_2020", "news_2013", "wikipedia_2014"]),
        import_leipzig.run,
        [
            "providers/leipzig/nob-no_web_2020_1M.tar.gz",
            "providers/leipzig/nob_news_2013_1M.tar.gz",
            "providers/leipzig/nob_wikipedia_2014_1M.tar.gz",
        ],
    ),
]


def _table_is_empty(table: str) -> bool:
    engine = get_engine()
    with engine.connect() as conn:
        return conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() == 0


def main() -> None:
    subprocess.run(["alembic", "upgrade", "head"], check=True)

    for table, run, args in _IMPORTS:
        is_empty = table() if callable(table) else _table_is_empty(table)
        if not is_empty:
            label = table.__name__ if callable(table) else table
            print(f"[bootstrap] {label} already populated, skipping import", file=sys.stderr)
            continue
        try:
            resolved_args = args() if callable(args) else args
            run(*resolved_args)
        except FileNotFoundError as exc:
            print(f"[bootstrap] skipping {run.__module__}: {exc}", file=sys.stderr)

    # exec, not subprocess.run: replaces this process (PID 1 in the
    # container) so signals (SIGTERM on `docker stop`) reach the Flask
    # process directly, and the full inherited environment (DATABASE_URL,
    # SMIA_AUTH_TOKEN, ...) carries over automatically.
    os.execvp("python", ["python", "app.py"])


if __name__ == "__main__":
    main()
