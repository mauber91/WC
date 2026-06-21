"""update squad season columns for 25-26 window

Revision ID: c4d8e2f1a903
Revises: 88b0b3c50e5c
Create Date: 2026-06-21 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c4d8e2f1a903"
down_revision: Union[str, Sequence[str], None] = "88b0b3c50e5c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("squad_players") as batch_op:
        batch_op.add_column(sa.Column("season_rating_2025_26", sa.Float(), nullable=True))
        batch_op.drop_column("season_rating_2022_23")


def downgrade() -> None:
    with op.batch_alter_table("squad_players") as batch_op:
        batch_op.add_column(sa.Column("season_rating_2022_23", sa.Float(), nullable=True))
        batch_op.drop_column("season_rating_2025_26")
