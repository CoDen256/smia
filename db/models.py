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

from sqlalchemy import DateTime, Text, UniqueConstraint, func
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
