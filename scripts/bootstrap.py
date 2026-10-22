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

import os
import subprocess
import sys

from sqlalchemy import text

from db.session import get_engine
from scripts import import_ipadict, import_kaikki, import_nst, import_ordbank, import_wikipron

_IMPORTS = [
    ("ordbank_fullform", import_ordbank.run, ["providers/nbno/20220201_norsk_ordbank_nob_2005.tar.gz"]),
    ("kaikki_entry", import_kaikki.run, ["providers/kaikii/kaikki.org-dictionary-NorwegianBokmål.jsonl"]),
    (
        "nst_lexicon",
        import_nst.run,
        ["providers/nbno/nb_uttale_tillegg.zip", "providers/nbno/nb_uttale_leksika.zip"],
    ),
    ("ipa_dict_entry", import_ipadict.run, ["providers/open-dict/nb.txt"]),
    ("wikipron_entry", import_wikipron.run, ["providers/wikipron/data/scrape/tsv/nob_latn_broad.tsv"]),
]


def _table_is_empty(table: str) -> bool:
    engine = get_engine()
    with engine.connect() as conn:
        return conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() == 0


def main() -> None:
    subprocess.run(["alembic", "upgrade", "head"], check=True)

    for table, run, args in _IMPORTS:
        if not _table_is_empty(table):
            print(f"[bootstrap] {table} already populated, skipping import", file=sys.stderr)
            continue
        try:
            run(*args)
        except FileNotFoundError as exc:
            print(f"[bootstrap] skipping {run.__module__}: {exc}", file=sys.stderr)

    # exec, not subprocess.run: replaces this process (PID 1 in the
    # container) so signals (SIGTERM on `docker stop`) reach the Flask
    # process directly, and the full inherited environment (DATABASE_URL,
    # SMIA_AUTH_TOKEN, ...) carries over automatically.
    os.execvp("python", ["python", "app.py"])


if __name__ == "__main__":
    main()
