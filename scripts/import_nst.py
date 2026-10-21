"""
scripts/import_nst.py — one-shot import of the NST pronunciation lexicon
and its five dialect-area variants (tasks 4.1-4.2) into `nst_lexicon` /
`nst_dialect`. Streams both zips' CSV members directly (never extracts to
disk) and bulk-loads via Postgres COPY.

`original_nst_lexicon_nofabet.csv` has no precomputed IPA column, so IPA is
computed here via the ported conversion table (`adapters/_nofabet_conversion
.convert_nofabet`); the dialect lexica already ship a precomputed
`ipa_transcription` column, so those are copied straight through.

Run:
  python -m scripts.import_nst \\
    providers/nbno/nb_uttale_tillegg.zip \\
    providers/nbno/nb_uttale_leksika.zip
"""

from __future__ import annotations

import argparse
import csv
import io
import zipfile

from adapters._nofabet_conversion import convert_nofabet
from db.session import get_engine

# filename prefix -> dialect area, per NB_Uttale_Work_on_Dialects.pdf
_DIALECT_AREAS = {
    "e": "eastern",
    "sw": "southwestern",
    "w": "western",
    "t": "central",
    "n": "northern",
}


def _csv_rows(zf: zipfile.ZipFile, member: str):
    with zf.open(member) as f:
        text = io.TextIOWrapper(f, encoding="utf-8", newline="")
        reader = csv.reader(text)
        header = next(reader)
        for row in reader:
            if row:
                yield dict(zip(header, row))


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n").replace("\r", "\\r")


def _copy(conn, table: str, columns: list[str], row_tuples) -> int:
    buf = io.StringIO()
    n = 0
    for values in row_tuples:
        buf.write("\t".join(_escape(v) for v in values))
        buf.write("\n")
        n += 1
    buf.seek(0)
    with conn.cursor() as cur:
        cur.copy_expert(f"COPY {table} ({', '.join(columns)}) FROM STDIN WITH (FORMAT text)", buf)
    return n


def _import_main_lexicon(conn, tillegg_zip: str) -> None:
    with zipfile.ZipFile(tillegg_zip) as zf:
        def rows():
            for r in _csv_rows(zf, "nb_uttale_tillegg/original_nst_lexicon_nofabet.csv"):
                nofabet = r["nofabet"]
                try:
                    ipa = convert_nofabet(nofabet, to="ipa")
                except Exception:
                    continue
                yield (r["wordform"], nofabet, ipa)

        n = _copy(conn, "nst_lexicon", ["wordform", "nofabet", "ipa"], rows())
    print(f"nst_lexicon: {n}")


def _import_dialects(conn, leksika_zip: str) -> None:
    total = 0
    with zipfile.ZipFile(leksika_zip) as zf:
        members = [m for m in zf.namelist() if m.endswith(".csv")]
        for member in members:
            # e.g. "nb_uttale_leksika/e_spoken_pronunciation_lexicon.csv"
            name = member.rsplit("/", 1)[-1]
            prefix, register = name.split("_", 1)[0], ("spoken" if "_spoken_" in name else "written")
            area = _DIALECT_AREAS[prefix]

            def rows(member=member, area=area, register=register):
                for r in _csv_rows(zf, member):
                    yield (r["wordform"], area, register, r["ipa_transcription"])

            total += _copy(conn, "nst_dialect", ["wordform", "dialect_area", "register", "ipa"], rows())
    print(f"nst_dialect: {total}")


def run(tillegg_zip: str, leksika_zip: str) -> None:
    engine = get_engine()
    conn = engine.raw_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE nst_lexicon, nst_dialect")
        _import_main_lexicon(conn, tillegg_zip)
        _import_dialects(conn, leksika_zip)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tillegg_zip")
    parser.add_argument("leksika_zip")
    args = parser.parse_args()
    run(args.tillegg_zip, args.leksika_zip)


if __name__ == "__main__":
    main()
