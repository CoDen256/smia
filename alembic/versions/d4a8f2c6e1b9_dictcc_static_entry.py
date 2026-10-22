"""dictcc_static_entry table

Revision ID: d4a8f2c6e1b9
Revises: c1e7f9b3a5d6
Create Date: 2026-10-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d4a8f2c6e1b9"
down_revision: Union[str, None] = "c1e7f9b3a5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "dictcc_static_entry",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("pair", sa.Text(), nullable=False),
        sa.Column("term1", sa.Text(), nullable=False),
        sa.Column("term2", sa.Text(), nullable=False),
        sa.Column("term1_clean", sa.Text(), nullable=False),
        sa.Column("term2_clean", sa.Text(), nullable=False),
        sa.Column("pos", sa.Text(), nullable=False),
        sa.Column("tags", sa.Text(), nullable=False),
    )
    op.create_index("ix_dictcc_static_entry_pair_term1_clean", "dictcc_static_entry", ["pair", "term1_clean"])
    op.create_index("ix_dictcc_static_entry_pair_term2_clean", "dictcc_static_entry", ["pair", "term2_clean"])


def downgrade() -> None:
    op.drop_index("ix_dictcc_static_entry_pair_term2_clean", table_name="dictcc_static_entry")
    op.drop_index("ix_dictcc_static_entry_pair_term1_clean", table_name="dictcc_static_entry")
    op.drop_table("dictcc_static_entry")
