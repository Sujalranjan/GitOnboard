"""multi_tenant_repo_uniqueness_and_agent_run_user

Revision ID: b2c3d4e5f6a7
Revises: 72b80aab7e8e
Create Date: 2026-08-23 01:25:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "72b80aab7e8e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: multi-tenant composite uniqueness & agent_runs user association."""
    # 1. Drop global unique constraints if present
    try:
        op.drop_constraint("repositories_url_key", "repositories", type_="unique")
    except Exception:
        pass

    try:
        op.drop_constraint("repositories_github_repo_id_key", "repositories", type_="unique")
    except Exception:
        pass

    # Drop unique indexes if created as indexes
    try:
        op.drop_index("ix_repositories_url", table_name="repositories")
        op.create_index("ix_repositories_url", "repositories", ["url"], unique=False)
    except Exception:
        pass

    try:
        op.drop_index("ix_repositories_github_repo_id", table_name="repositories")
        op.create_index("ix_repositories_github_repo_id", "repositories", ["github_repo_id"], unique=False)
    except Exception:
        pass

    # 2. Create composite unique constraints for multi-tenant isolation
    try:
        op.create_unique_constraint("uq_user_repo_url", "repositories", ["user_id", "url"])
    except Exception:
        pass

    try:
        op.create_unique_constraint("uq_user_github_repo", "repositories", ["user_id", "github_repo_id"])
    except Exception:
        pass

    # 3. Add user_id column to agent_runs if not exists
    try:
        op.add_column(
            "agent_runs",
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        )
        op.create_index("ix_agent_runs_user_id", "agent_runs", ["user_id"])
    except Exception:
        pass


def downgrade() -> None:
    """Downgrade schema."""
    try:
        op.drop_constraint("uq_user_github_repo", "repositories", type_="unique")
        op.drop_constraint("uq_user_repo_url", "repositories", type_="unique")
    except Exception:
        pass

    try:
        op.drop_index("ix_agent_runs_user_id", table_name="agent_runs")
        op.drop_column("agent_runs", "user_id")
    except Exception:
        pass

    try:
        op.create_unique_constraint("repositories_github_repo_id_key", "repositories", ["github_repo_id"])
        op.create_unique_constraint("repositories_url_key", "repositories", ["url"])
    except Exception:
        pass
