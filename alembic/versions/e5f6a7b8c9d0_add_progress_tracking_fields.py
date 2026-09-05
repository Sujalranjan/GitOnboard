"""Add progress tracking fields to Analysis and AnalysisJob.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-09-05 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add progress tracking columns to analyses table
    op.add_column(
        "analyses",
        sa.Column("progress_stage", sa.String(), nullable=True),
    )
    op.add_column(
        "analyses",
        sa.Column("progress_substage", sa.String(), nullable=True),
    )
    op.add_column(
        "analyses",
        sa.Column("progress_percentage", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "analyses",
        sa.Column("progress_processed", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "analyses",
        sa.Column("progress_total", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "analyses",
        sa.Column("progress_unit", sa.String(), nullable=True),
    )

    # Add denormalized progress columns to analysis_jobs table
    op.add_column(
        "analysis_jobs",
        sa.Column("progress_percentage", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "analysis_jobs",
        sa.Column("progress_details", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    # Drop columns from analysis_jobs table
    op.drop_column("analysis_jobs", "progress_details")
    op.drop_column("analysis_jobs", "progress_percentage")

    # Drop columns from analyses table
    op.drop_column("analyses", "progress_unit")
    op.drop_column("analyses", "progress_total")
    op.drop_column("analyses", "progress_processed")
    op.drop_column("analyses", "progress_percentage")
    op.drop_column("analyses", "progress_substage")
    op.drop_column("analyses", "progress_stage")
