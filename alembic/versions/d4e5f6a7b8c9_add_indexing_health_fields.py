"""add_indexing_health_fields

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-09-03 13:06:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema to add indexing health fields to analyses table."""
    # Add new columns for indexing health tracking (Phase 4-B)
    op.add_column(
        "analyses",
        sa.Column(
            "indexing_status",
            sa.String(),
            nullable=False,
            server_default="PENDING",
        ),
    )
    op.add_column(
        "analyses",
        sa.Column(
            "indexing_details",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
    )

    # Add fact_store_version for staleness detection (Phase 4-C)
    op.add_column(
        "analyses",
        sa.Column("fact_store_version", sa.String(), nullable=True),
    )

    # Add indexed_at timestamp to track when indexing completed (Phase 4-B)
    op.add_column(
        "analyses",
        sa.Column(
            "indexed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    # Alter indexing_status to drop default after initial data is populated
    op.alter_column(
        "analyses",
        "indexing_status",
        existing_type=sa.String(),
        server_default=None,
    )


def downgrade() -> None:
    """Downgrade schema to remove indexing health fields from analyses table."""
    op.drop_column("analyses", "indexed_at")
    op.drop_column("analyses", "fact_store_version")
    op.drop_column("analyses", "indexing_details")
    op.drop_column("analyses", "indexing_status")
