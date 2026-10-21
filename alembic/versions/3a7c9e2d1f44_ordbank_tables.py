"""ordbank tables

Revision ID: 3a7c9e2d1f44
Revises: 8f1b4b1c6b0a
Create Date: 2026-10-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "3a7c9e2d1f44"
down_revision: Union[str, None] = "8f1b4b1c6b0a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ordbank_lemma",
        sa.Column("lemma_id", sa.Integer(), primary_key=True),
        sa.Column("grunnform", sa.Text(), nullable=False),
    )
    op.create_table(
        "ordbank_paradigme",
        sa.Column("paradigme_id", sa.Text(), primary_key=True),
        sa.Column("boy_gruppe", sa.Text(), nullable=False),
        sa.Column("ordklasse", sa.Text(), nullable=False),
    )
    op.create_table(
        "ordbank_boying",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("boy_gruppe", sa.Text(), nullable=False),
        sa.Column("boy_nummer", sa.Integer(), nullable=False),
        sa.Column("ordbok_tekst", sa.Text(), nullable=False),
        sa.UniqueConstraint("boy_gruppe", "boy_nummer", name="uq_ordbank_boying_gruppe_nummer"),
    )
    op.create_table(
        "ordbank_fullform",
        sa.Column("loepenr", sa.Integer(), primary_key=True),
        # lemma_id/paradigme_id are plain columns, not FKs — the source
        # export has referential gaps (see db/models.py's OrdbankFullform
        # docstring).
        sa.Column("lemma_id", sa.Integer(), nullable=False),
        sa.Column("oppslag", sa.Text(), nullable=False),
        sa.Column("paradigme_id", sa.Text(), nullable=False),
        sa.Column("boy_nummer", sa.Integer(), nullable=False),
        sa.Column("fradato", sa.Text(), nullable=False),
        sa.Column("tildato", sa.Text(), nullable=False),
        sa.Column("normering", sa.Text(), nullable=False),
    )
    op.create_index("ix_ordbank_fullform_oppslag", "ordbank_fullform", ["oppslag"])
    op.create_index("ix_ordbank_fullform_lemma_paradigme", "ordbank_fullform", ["lemma_id", "paradigme_id"])


def downgrade() -> None:
    op.drop_index("ix_ordbank_fullform_lemma_paradigme", table_name="ordbank_fullform")
    op.drop_index("ix_ordbank_fullform_oppslag", table_name="ordbank_fullform")
    op.drop_table("ordbank_fullform")
    op.drop_table("ordbank_boying")
    op.drop_table("ordbank_paradigme")
    op.drop_table("ordbank_lemma")
