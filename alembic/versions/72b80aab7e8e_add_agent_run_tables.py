"""add_agent_run_tables

Revision ID: 72b80aab7e8e
Revises: a1b2c3d4e5f6
Create Date: 2026-08-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "72b80aab7e8e"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("implementation_id", sa.String(), nullable=True),
        sa.Column("task_id", sa.String(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "QUEUED", "RUNNING", "VERIFYING", "REPAIRING", "COMPLETED", "FAILED",
                name="agent_run_status",
            ),
            nullable=False,
        ),
        sa.Column("iteration", sa.Integer(), nullable=False),
        sa.Column("worktree_path", sa.String(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["implementation_id"], ["implementations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_agent_runs_implementation_id"), "agent_runs", ["implementation_id"], unique=False)
    op.create_index(op.f("ix_agent_runs_task_id"), "agent_runs", ["task_id"], unique=False)
    op.create_index(op.f("ix_agent_runs_status"), "agent_runs", ["status"], unique=False)

    op.create_table(
        "agent_events",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("agent_run_id", sa.String(), nullable=False),
        sa.Column(
            "event_type",
            sa.Enum(
                "STARTED", "CONTRACT_GENERATED", "CODE_GENERATING", "FILE_WRITTEN",
                "DIFF_CAPTURED", "VERIFICATION_STARTED", "VERIFICATION_COMPLETED",
                "REPAIR_STARTED", "FINISHED", "FAILED",
                name="agent_event_type",
            ),
            nullable=False,
        ),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "payload",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_agent_events_agent_run_id"), "agent_events", ["agent_run_id"], unique=False)
    op.create_index(op.f("ix_agent_events_created_at"), "agent_events", ["created_at"], unique=False)

    op.create_table(
        "file_changes",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("agent_run_id", sa.String(), nullable=False),
        sa.Column("file_path", sa.String(), nullable=False),
        sa.Column(
            "change_type",
            sa.Enum("ADDED", "MODIFIED", "DELETED", name="file_change_type"),
            nullable=False,
        ),
        sa.Column("lines_added", sa.Integer(), nullable=False),
        sa.Column("lines_removed", sa.Integer(), nullable=False),
        sa.Column("diff_patch", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_file_changes_agent_run_id"), "file_changes", ["agent_run_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_file_changes_agent_run_id"), table_name="file_changes")
    op.drop_table("file_changes")
    op.drop_index(op.f("ix_agent_events_created_at"), table_name="agent_events")
    op.drop_index(op.f("ix_agent_events_agent_run_id"), table_name="agent_events")
    op.drop_table("agent_events")
    op.drop_index(op.f("ix_agent_runs_status"), table_name="agent_runs")
    op.drop_index(op.f("ix_agent_runs_task_id"), table_name="agent_runs")
    op.drop_index(op.f("ix_agent_runs_implementation_id"), table_name="agent_runs")
    op.drop_table("agent_runs")
    op.execute("DROP TYPE IF EXISTS file_change_type")
    op.execute("DROP TYPE IF EXISTS agent_event_type")
    op.execute("DROP TYPE IF EXISTS agent_run_status")
