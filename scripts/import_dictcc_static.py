"""
scripts/import_dictcc_static.py — one-shot import of dict.cc's NO-EN/
NO-DE/DE-EN vocabulary dumps into `dictcc_static_entry` (task 2.1).

Each file is tab-separated (`term1, term2, pos, tags`) preceded by `#`
comment/license lines and a blank separator — the license itself is read
and asserted to still say "private use" (task 2.3's "never exposed raw"
guarantee starts with "don't import something whose license changed
underneath us without noticing"), not just skipped.

The dump files themselves live only on disk (`providers/dict/`, gitignored,
bind-mounted into the container same as every other `providers/*` source)
— this script reads them, nothing in smia ever serves them back out.

Run: python -m scripts.import_dictcc_static \\
    providers/dict/<no-en-file>.txt no_en \\
    providers/dict/<no-de-file>.txt no_de \\
    providers/dict/<de-en-file>.txt de_en
"""

from __future__ import annotations

import argparse
import html
import io
import re

from db.session import get_engine

_VALID_PAIRS = {"no_en", "no_de", "de_en"}

# Strips trailing grammar-annotation groups ("Haus {n}" -> "Haus", "Haus
# {n} [arch.]" -> "Haus") so a query for the bare lemma matches — the raw
# dump bakes these directly into the term text, confirmed live when an
# exact-match query for "Haus" matched nothing (every stored row is
# "Haus {n}", never the bare word). Leading parentheticals are left alone;
# matching those is out of scope for a best-effort provider.
_TRAILING_ANNOTATION_RE = re.compile(r"(\s*[\{\[<][^}\]>]*[\}\]>])+\s*$")

# Strips the Norwegian verb infinitive marker ("å komme" -> "komme") the
# same way adapters/dictcc_api.py's _normalize_label does for its own
# inflection-table labels — the raw dump's Norwegian verb entries are
# always stored with this marker, so a bare-infinitive query like "komme"
# wouldn't otherwise match any row.
_LEADING_INFINITIVE_RE = re.compile(r"^å\s+", re.IGNORECASE)


def _clean(term: str) -> str:
    term = _TRAILING_ANNOTATION_RE.sub("", term).strip()
    return _LEADING_INFINITIVE_RE.sub("", term).strip()


def _rows(path: str):
    saw_private_use_license = False
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if line.startswith("#"):
                if "private use" in line.lower():
                    saw_private_use_license = True
                continue
            if not line:
                continue
            parts = line.split("\t")
            parts += [""] * (4 - len(parts))
            term1, term2, pos, tags = (html.unescape(p.strip()) for p in parts[:4])
            if term1 and term2:
                yield term1, term2, _clean(term1), _clean(term2), pos, tags

    if not saw_private_use_license:
        raise ValueError(
            f"{path}: expected license header did not mention 'private use' — "
            "refusing to import a file whose terms may have changed (task 2.3)"
        )


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n").replace("\r", "\\r")


def _copy(conn, pair: str, path: str) -> int:
    buf = io.StringIO()
    n = 0
    for term1, term2, term1_clean, term2_clean, pos, tags in _rows(path):
        buf.write("\t".join(_escape(v) for v in (pair, term1, term2, term1_clean, term2_clean, pos, tags)))
        buf.write("\n")
        n += 1
    buf.seek(0)
    with conn.cursor() as cur:
        cur.copy_expert(
            "COPY dictcc_static_entry (pair, term1, term2, term1_clean, term2_clean, pos, tags) "
            "FROM STDIN WITH (FORMAT text)",
            buf,
        )
    return n


def run(*path_pair_pairs: str) -> None:
    if len(path_pair_pairs) % 2 != 0:
        raise ValueError("expected alternating path, pair arguments")
    jobs = list(zip(path_pair_pairs[0::2], path_pair_pairs[1::2]))
    for _, pair in jobs:
        if pair not in _VALID_PAIRS:
            raise ValueError(f"unknown pair {pair!r}; expected one of {_VALID_PAIRS}")

    engine = get_engine()
    conn = engine.raw_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE dictcc_static_entry")
        for path, pair in jobs:
            n = _copy(conn, pair, path)
            print(f"dictcc_static_entry ({pair}): {n}")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path_pair", nargs="+", help="alternating <path> <pair> arguments")
    args = parser.parse_args()
    run(*args.path_pair)


if __name__ == "__main__":
    main()
