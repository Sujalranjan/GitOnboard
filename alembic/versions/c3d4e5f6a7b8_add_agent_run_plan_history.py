"""add_agent_run_plan_history

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-08-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema to add agent_run_plan_history table."""
    op.create_table(
        "agent_run_plan_history",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("agent_run_id", sa.String(), nullable=False),
        sa.Column("plan_id", sa.String(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "DRAFT",
                "VALIDATING",
                "READY_FOR_APPROVAL",
                "APPROVED",
                "REJECTED",
                "INVALID",
                "SUPERSEDED",
                name="agent_run_plan_history_status",
            ),
            nullable=False,
        ),
        sa.Column("resolved_by", sa.String(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("superseded_by_plan_id", sa.String(), nullable=True),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "plan_json",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_id", name="uq_agent_run_plan_history_plan_id"),
    )

    # Add self-referential FK after table creation and unique constraint exists
    op.create_foreign_key(
        "fk_agent_run_plan_history_superseded",
        "agent_run_plan_history",
        "agent_run_plan_history",
        ["superseded_by_plan_id"],
        ["plan_id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_agent_run_plan_history_agent_run_id"),
        "agent_run_plan_history",
        ["agent_run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_run_plan_history_plan_id"),
        "agent_run_plan_history",
        ["plan_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_agent_run_plan_history_version"),
        "agent_run_plan_history",
        ["version"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_run_plan_history_status"),
        "agent_run_plan_history",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_run_plan_history_created_at"),
        "agent_run_plan_history",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema to remove agent_run_plan_history table."""
    # Drop self-referential FK first
    op.drop_constraint(
        "fk_agent_run_plan_history_superseded",
        "agent_run_plan_history",
        type_="foreignkey",
    )

    op.drop_index(
        op.f("ix_agent_run_plan_history_created_at"),
        table_name="agent_run_plan_history",
    )
    op.drop_index(
        op.f("ix_agent_run_plan_history_status"), table_name="agent_run_plan_history"
    )
    op.drop_index(
        op.f("ix_agent_run_plan_history_version"), table_name="agent_run_plan_history"
    )
    op.drop_index(
        op.f("ix_agent_run_plan_history_plan_id"), table_name="agent_run_plan_history"
    )
    op.drop_index(
        op.f("ix_agent_run_plan_history_agent_run_id"),
        table_name="agent_run_plan_history",
    )
    op.drop_table("agent_run_plan_history")
    op.execute("DROP TYPE IF EXISTS agent_run_plan_history_status")
