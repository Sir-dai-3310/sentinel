"""Import tasks table for bulk log ingestion.

Revision ID: 003_import_tasks
Revises: 002_multitenancy
Create Date: 2026-08-18

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003_import_tasks"
down_revision: Union[str, None] = "002_multitenancy"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "import_tasks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("filename", sa.String(length=255), nullable=True),
        sa.Column("format", sa.String(length=10), nullable=True),
        sa.Column("total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "tenant_id",
            sa.String(length=64),
            nullable=False,
            server_default="default",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id"),
    )
    op.create_index("idx_import_task_id", "import_tasks", ["task_id"])
    op.create_index("idx_import_status", "import_tasks", ["status"])
    op.create_index("idx_import_tenant_id", "import_tasks", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("idx_import_tenant_id", table_name="import_tasks")
    op.drop_index("idx_import_status", table_name="import_tasks")
    op.drop_index("idx_import_task_id", table_name="import_tasks")
    op.drop_table("import_tasks")
