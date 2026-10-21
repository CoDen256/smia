"""ipa provider tables: nst_lexicon, nst_dialect, ipa_dict_entry, wikipron_entry

Revision ID: 7b4f1a8e2c90
Revises: 5c2e8a0b9d31
Create Date: 2026-10-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "7b4f1a8e2c90"
down_revision: Union[str, None] = "5c2e8a0b9d31"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "nst_lexicon",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("wordform", sa.Text(), nullable=False),
        sa.Column("nofabet", sa.Text(), nullable=False),
        sa.Column("ipa", sa.Text(), nullable=False),
    )
    op.create_index("ix_nst_lexicon_wordform", "nst_lexicon", ["wordform"])

    op.create_table(
        "nst_dialect",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("wordform", sa.Text(), nullable=False),
        sa.Column("dialect_area", sa.Text(), nullable=False),
        sa.Column("register", sa.Text(), nullable=False),
        sa.Column("ipa", sa.Text(), nullable=False),
    )
    op.create_index("ix_nst_dialect_wordform", "nst_dialect", ["wordform"])

    op.create_table(
        "ipa_dict_entry",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("wordform", sa.Text(), nullable=False),
        sa.Column("ipa", sa.Text(), nullable=False),
    )
    op.create_index("ix_ipa_dict_entry_wordform", "ipa_dict_entry", ["wordform"])

    op.create_table(
        "wikipron_entry",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("wordform", sa.Text(), nullable=False),
        sa.Column("ipa", sa.Text(), nullable=False),
    )
    op.create_index("ix_wikipron_entry_wordform", "wikipron_entry", ["wordform"])


def downgrade() -> None:
    op.drop_index("ix_wikipron_entry_wordform", table_name="wikipron_entry")
    op.drop_table("wikipron_entry")
    op.drop_index("ix_ipa_dict_entry_wordform", table_name="ipa_dict_entry")
    op.drop_table("ipa_dict_entry")
    op.drop_index("ix_nst_dialect_wordform", table_name="nst_dialect")
    op.drop_table("nst_dialect")
    op.drop_index("ix_nst_lexicon_wordform", table_name="nst_lexicon")
    op.drop_table("nst_lexicon")
