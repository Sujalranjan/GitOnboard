"""add_blob_storage_fields_to_files

Revision ID: a1b2c3d4e5f6
Revises: 44dad75b8d13
Create Date: 2026-08-17 02:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "44dad75b8d13"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("files", sa.Column("blob_name", sa.String(), nullable=True))
    op.add_column("files", sa.Column("snapshot_id", sa.String(), nullable=True))
    op.add_column("files", sa.Column("content_type", sa.String(), nullable=True))
    op.add_column("files", sa.Column("size", sa.Integer(), nullable=True, server_default="0"))
    op.add_column("files", sa.Column("is_binary", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("files", sa.Column("is_generated", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("files", sa.Column("is_test", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("files", sa.Column("is_documentation", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("files", sa.Column("is_agent_instruction", sa.Boolean(), nullable=False, server_default=sa.text("false")))

    op.create_index(op.f("ix_files_blob_name"), "files", ["blob_name"], unique=False)
    op.create_index(op.f("ix_files_snapshot_id"), "files", ["snapshot_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_files_snapshot_id"), table_name="files")
    op.drop_index(op.f("ix_files_blob_name"), table_name="files")
    op.drop_column("files", "is_agent_instruction")
    op.drop_column("files", "is_documentation")
    op.drop_column("files", "is_test")
    op.drop_column("files", "is_generated")
    op.drop_column("files", "is_binary")
    op.drop_column("files", "size")
    op.drop_column("files", "content_type")
    op.drop_column("files", "snapshot_id")
    op.drop_column("files", "blob_name")
