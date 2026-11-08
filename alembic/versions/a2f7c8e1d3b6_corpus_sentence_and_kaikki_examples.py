"""corpus_sentence table + kaikki_entry.examples column

Revision ID: a2f7c8e1d3b6
Revises: d4a8f2c6e1b9
Create Date: 2026-11-08

The GIN index on corpus_sentence.tsv is deliberately NOT created here —
scripts/import_tatoeba.py and scripts/import_leipzig.py build it themselves
after their bulk insert completes, since a GIN build over ~3M rows is the
slow step of the whole import and doing it here would mean every bootstrap
run pays that cost against an empty table before the real data ever lands.
This migration only creates the (cheap) btree index on `corpus`.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "a2f7c8e1d3b6"
down_revision: Union[str, None] = "d4a8f2c6e1b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "corpus_sentence",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("corpus", sa.Text(), nullable=False),
        sa.Column("ext_id", sa.Text(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("word_count", sa.Integer(), nullable=False),
        sa.Column("tsv", postgresql.TSVECTOR(), nullable=True),
    )
    op.create_index("ix_corpus_sentence_corpus", "corpus_sentence", ["corpus"])

    op.add_column(
        "kaikki_entry",
        sa.Column("examples", postgresql.JSONB(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("kaikki_entry", "examples")
    op.drop_index("ix_corpus_sentence_corpus", table_name="corpus_sentence")
    op.drop_table("corpus_sentence")
