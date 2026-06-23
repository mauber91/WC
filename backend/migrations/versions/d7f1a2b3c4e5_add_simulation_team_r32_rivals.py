"""add simulation team r32 rivals

Revision ID: d7f1a2b3c4e5
Revises: c4d8e2f1a903
Create Date: 2026-06-20 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d7f1a2b3c4e5"
down_revision: Union[str, Sequence[str], None] = "c4d8e2f1a903"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "simulation_team_r32_rivals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("simulation_id", sa.String(length=36), nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("finish_position", sa.Integer(), nullable=False),
        sa.Column("opponent_team_id", sa.Integer(), nullable=False),
        sa.Column("meeting_count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["opponent_team_id"], ["teams.id"]),
        sa.ForeignKeyConstraint(["simulation_id"], ["simulations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "simulation_id",
            "team_id",
            "finish_position",
            "opponent_team_id",
            name="uq_sim_team_r32_rival",
        ),
    )
    op.create_index(
        "ix_sim_team_r32_rival",
        "simulation_team_r32_rivals",
        ["simulation_id", "team_id", "finish_position"],
        unique=False,
    )
    op.create_index(
        op.f("ix_simulation_team_r32_rivals_opponent_team_id"),
        "simulation_team_r32_rivals",
        ["opponent_team_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_simulation_team_r32_rivals_team_id"),
        "simulation_team_r32_rivals",
        ["team_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_simulation_team_r32_rivals_team_id"), table_name="simulation_team_r32_rivals")
    op.drop_index(op.f("ix_simulation_team_r32_rivals_opponent_team_id"), table_name="simulation_team_r32_rivals")
    op.drop_index("ix_sim_team_r32_rival", table_name="simulation_team_r32_rivals")
    op.drop_table("simulation_team_r32_rivals")
