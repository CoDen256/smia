"""pygmalion_audio: word -> recording map for the `pygmalion` /tts provider

Revision ID: e6b3a9d2f401
Revises: a2f7c8e1d3b6
Create Date: 2026-11-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e6b3a9d2f401"
down_revision: Union[str, None] = "a2f7c8e1d3b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pygmalion_audio",
        sa.Column("word", sa.Text(), nullable=False),
        sa.Column("dialect", sa.Text(), nullable=False),
        sa.Column("take", sa.Integer(), nullable=False, autoincrement=False),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("word", "dialect", "take"),
    )
    op.create_index("ix_pygmalion_audio_word", "pygmalion_audio", ["word"])


def downgrade() -> None:
    op.drop_index("ix_pygmalion_audio_word", table_name="pygmalion_audio")
    op.drop_table("pygmalion_audio")
