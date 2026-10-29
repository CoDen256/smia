"""scripts/bootstrap.py's dict.cc header-matching — the real dump's first
line is itself two tab-separated columns ("# NO-EN vocabulary database\\t
compiled by dict.cc"), not the bare key alone. An exact-equality match
against the whole line never matched any real file; this went unnoticed
because an already-populated dictcc_static_entry table skips the check
entirely on every subsequent run, only ever exercised for real on a
genuinely empty database (confirmed live, D120)."""

from __future__ import annotations

from scripts.bootstrap import _find_dictcc_static_args


def test_matches_real_header_line_with_trailing_metadata_column(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "providers" / "dict").mkdir(parents=True)
    (tmp_path / "providers" / "dict" / "no-en.txt").write_text(
        "# NO-EN vocabulary database\tcompiled by dict.cc\nhus\thouse\tnoun\n"
    )
    (tmp_path / "providers" / "dict" / "no-de.txt").write_text(
        "# NO-DE vocabulary database\tcompiled by dict.cc\nhus\tHaus\tnoun\n"
    )
    (tmp_path / "providers" / "dict" / "de-en.txt").write_text(
        "# DE-EN vocabulary database\tcompiled by dict.cc\nHaus\thouse\tnoun\n"
    )

    args = _find_dictcc_static_args()

    assert args == [
        "providers/dict/de-en.txt", "de_en",
        "providers/dict/no-de.txt", "no_de",
        "providers/dict/no-en.txt", "no_en",
    ]


def test_raises_when_no_file_has_a_recognized_header(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "providers" / "dict").mkdir(parents=True)
    (tmp_path / "providers" / "dict" / "unrelated.txt").write_text("not a dict.cc dump\n")

    try:
        _find_dictcc_static_args()
        assert False, "expected FileNotFoundError"
    except FileNotFoundError:
        pass
