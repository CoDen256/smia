"""kaikki_entry table

Revision ID: 5c2e8a0b9d31
Revises: 3a7c9e2d1f44
Create Date: 2026-10-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "5c2e8a0b9d31"
down_revision: Union[str, None] = "3a7c9e2d1f44"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "kaikki_entry",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("word", sa.Text(), nullable=False),
        sa.Column("pos", sa.Text(), nullable=False),
        sa.Column("gender", sa.Text(), nullable=True),
        sa.Column("forms", postgresql.JSONB(), nullable=False),
        sa.Column("sounds", postgresql.JSONB(), nullable=False),
    )
    op.create_index("ix_kaikki_entry_word", "kaikki_entry", ["word"])


def downgrade() -> None:
    op.drop_index("ix_kaikki_entry_word", table_name="kaikki_entry")
    op.drop_table("kaikki_entry")
