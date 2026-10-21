"""
db/models.py — SQLAlchemy ORM models for smia's own Postgres database.

D42: no cross-service foreign keys — smia's schema never references another
service's tables.

`LookupCache` is the one table every endpoint (`/inflections`, `/ipa`,
`/tts`, `/translations`, `/stt`) shares, per D-S3 (one runner, not five).
Two distinct hashes live on this row, not one, because they answer two
different questions:
  - `input_hash` = sha256(canonicalized input only) — the cache-key
    component the lookup-cache spec calls out ("(kind, provider,
    sha256(input))"); used to detect "have we already asked this provider
    this exact question".
  - `id` = sha256(kind, provider, input_hash) — the opaque external
    resource id from D-S2, used for `GET /<kind>/{id}` and for `/tts`'s
    byte-serving endpoint. It's a separate value because it folds in
    `kind`/`provider` too, which `input_hash` deliberately doesn't (so the
    same input under two providers/kinds collides on `input_hash` lookup
    intent but not on resource identity).
"""

from __future__ import annotations

import datetime

from sqlalchemy import DateTime, Integer, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class LookupCache(Base):
    __tablename__ = "lookup_cache"
    __table_args__ = (
        UniqueConstraint("kind", "provider", "input_hash", name="uq_lookup_cache_kind_provider_input"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    input_hash: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ── Norsk Ordbank import (task 3.1) ──────────────────────────────────────
#
# Four tables mirroring the source export's four files, kept close to the
# original column names (LEMMA_ID, PARADIGME_ID, ...) so the import job and
# `tun/docs`'s `09-open-questions.md` Q10 answer stay traceable back to
# `norsk_ordbank.pdf`'s own documentation. `ordbank_fullform.oppslag` is the
# reverse-lookup key (surface form -> candidates); `(lemma_id, paradigme_id)`
# is the candidate-grouping key the adapter uses (adapters/ordbank.py).


class OrdbankLemma(Base):
    __tablename__ = "ordbank_lemma"

    lemma_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    grunnform: Mapped[str] = mapped_column(Text, nullable=False)


class OrdbankParadigme(Base):
    __tablename__ = "ordbank_paradigme"

    paradigme_id: Mapped[str] = mapped_column(Text, primary_key=True)
    boy_gruppe: Mapped[str] = mapped_column(Text, nullable=False)
    ordklasse: Mapped[str] = mapped_column(Text, nullable=False)


class OrdbankBoying(Base):
    __tablename__ = "ordbank_boying"
    __table_args__ = (UniqueConstraint("boy_gruppe", "boy_nummer", name="uq_ordbank_boying_gruppe_nummer"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    boy_gruppe: Mapped[str] = mapped_column(Text, nullable=False)
    boy_nummer: Mapped[int] = mapped_column(Integer, nullable=False)
    ordbok_tekst: Mapped[str] = mapped_column(Text, nullable=False)


class KaikkiEntry(Base):
    """One row per kaikki.org/Wiktionary dump entry (D-S4: imported once,
    queried by three adapters — `kaikki` for `/inflections` via `forms`,
    and later `/ipa`/`/tts` via `sounds`, which is why both raw `jsonb`
    blobs are kept as-imported rather than normalized into their own
    tables up front)."""

    __tablename__ = "kaikki_entry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    word: Mapped[str] = mapped_column(Text, nullable=False)
    pos: Mapped[str] = mapped_column(Text, nullable=False)
    gender: Mapped[str | None] = mapped_column(Text, nullable=True)
    forms: Mapped[list] = mapped_column(JSONB, nullable=False)
    sounds: Mapped[list] = mapped_column(JSONB, nullable=False)


class OrdbankFullform(Base):
    """`lemma_id`/`paradigme_id` are plain columns, not foreign keys: the
    source export itself has referential gaps (some `fullformsliste.txt`
    rows cite a `LEMMA_ID` absent from `lemma.txt` — e.g. 156248 for the
    symbol `$`), discovered when the real import hit a FK violation."""

    __tablename__ = "ordbank_fullform"

    loepenr: Mapped[int] = mapped_column(Integer, primary_key=True)
    lemma_id: Mapped[int] = mapped_column(Integer, nullable=False)
    oppslag: Mapped[str] = mapped_column(Text, nullable=False)
    paradigme_id: Mapped[str] = mapped_column(Text, nullable=False)
    boy_nummer: Mapped[int] = mapped_column(Integer, nullable=False)
    fradato: Mapped[str] = mapped_column(Text, nullable=False)
    tildato: Mapped[str] = mapped_column(Text, nullable=False)
    normering: Mapped[str] = mapped_column(Text, nullable=False)
