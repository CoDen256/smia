"""
scripts/import_ordbank.py — one-shot import of the Norsk Ordbank export
into smia's `ordbank_*` tables (task 3.1).

The export's four files are plain tab-separated, CRLF-terminated, Latin-1
text — NOT quoted/escaped despite `lemma.txt`'s header having a stray pair
of single quotes around its last column name (a cosmetic quirk of the
source file, not a real quoting convention: every data row is quote-free,
confirmed by inspecting the raw bytes). This streams each member straight
out of the tarball (never writes an extracted copy to disk, since
`providers/` itself is gitignored raw data, not part of the repo) and
bulk-loads via Postgres `COPY`, since `fullformsliste.txt` alone is ~1.1M
rows.

Run: python -m scripts.import_ordbank providers/nbno/20220201_norsk_ordbank_nob_2005.tar.gz
"""

from __future__ import annotations

import argparse
import io
import tarfile

from db.session import get_engine


def _read_rows(tar: tarfile.TarFile, member: str):
    f = tar.extractfile(member)
    if f is None:
        raise FileNotFoundError(f"{member} not found in tarball")
    text = f.read().decode("latin-1")
    lines = [line for line in text.split("\r\n") if line]
    header = [col.strip("\"'") for col in lines[0].split("\t")]
    for line in lines[1:]:
        yield dict(zip(header, line.split("\t")))


def _escape(value: str) -> str:
    # Postgres COPY text format escaping — defensive; none of this dataset's
    # fields are expected to contain these characters.
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


def run(tarball_path: str) -> None:
    engine = get_engine()
    conn = engine.raw_connection()
    try:
        with tarfile.open(tarball_path, "r:gz") as tar:
            with conn.cursor() as cur:
                # child-to-parent order for the FKs
                cur.execute(
                    "TRUNCATE ordbank_fullform, ordbank_boying, ordbank_paradigme, ordbank_lemma"
                )

            n = _copy(
                conn, "ordbank_lemma", ["lemma_id", "grunnform"],
                ((r["LEMMA_ID"], r["GRUNNFORM"]) for r in _read_rows(tar, "lemma.txt")),
            )
            print(f"ordbank_lemma: {n}")

            n = _copy(
                conn, "ordbank_paradigme", ["paradigme_id", "boy_gruppe", "ordklasse"],
                (
                    (r["PARADIGME_ID"], r["BOY_GRUPPE"], r["ORDKLASSE"])
                    for r in _read_rows(tar, "paradigme.txt")
                ),
            )
            print(f"ordbank_paradigme: {n}")

            n = _copy(
                conn, "ordbank_boying", ["boy_gruppe", "boy_nummer", "ordbok_tekst"],
                (
                    (r["BOY_GRUPPE"], r["BOY_NUMMER"], r["ORDBOK_TEKST"])
                    for r in _read_rows(tar, "boying.txt")
                ),
            )
            print(f"ordbank_boying: {n}")

            n = _copy(
                conn, "ordbank_fullform",
                ["loepenr", "lemma_id", "oppslag", "paradigme_id", "boy_nummer", "fradato", "tildato", "normering"],
                (
                    (
                        r["LOEPENR"], r["LEMMA_ID"], r["OPPSLAG"], r["PARADIGME_ID"],
                        r["BOY_NUMMER"], r["FRADATO"], r["TILDATO"], r["NORMERING"],
                    )
                    for r in _read_rows(tar, "fullformsliste.txt")
                ),
            )
            print(f"ordbank_fullform: {n}")

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tarball", help="path to the ordbank export tar.gz")
    args = parser.parse_args()
    run(args.tarball)


if __name__ == "__main__":
    main()
