"""tts_audio cache table

Revision ID: 9d3f6c1a4b22
Revises: 7b4f1a8e2c90
Create Date: 2026-10-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "9d3f6c1a4b22"
down_revision: Union[str, None] = "7b4f1a8e2c90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tts_audio",
        sa.Column("sha256", sa.Text(), primary_key=True),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("tts_audio")
