"""Multi-tenancy: tenants table + tenant_id on analysis_results/audit_logs

Revision ID: 002_multitenancy
Revises: 001_initial
Create Date: 2026-08-18

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002_multitenancy"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Tenants table
    op.create_table(
        "tenants",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("max_requests_per_minute", sa.Integer(), server_default="0"),
        sa.Column("max_analyses_per_day", sa.Integer(), server_default="0"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("idx_tenant_slug", "tenants", ["slug"])
    op.create_index("idx_tenant_active", "tenants", ["active"])

    # tenant_id on analysis_results
    op.add_column(
        "analysis_results",
        sa.Column(
            "tenant_id",
            sa.String(length=64),
            nullable=False,
            server_default="default",
        ),
    )
    op.create_index("idx_analysis_tenant_id", "analysis_results", ["tenant_id"])
    op.create_index(
        "idx_analysis_tenant_created",
        "analysis_results",
        ["tenant_id", "created_at"],
    )

    # tenant_id on audit_logs
    op.add_column(
        "audit_logs",
        sa.Column(
            "tenant_id",
            sa.String(length=64),
            nullable=False,
            server_default="default",
        ),
    )
    op.create_index("idx_audit_tenant_id", "audit_logs", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("idx_audit_tenant_id", table_name="audit_logs")
    op.drop_column("audit_logs", "tenant_id")

    op.drop_index("idx_analysis_tenant_created", table_name="analysis_results")
    op.drop_index("idx_analysis_tenant_id", table_name="analysis_results")
    op.drop_column("analysis_results", "tenant_id")

    op.drop_index("idx_tenant_active", table_name="tenants")
    op.drop_index("idx_tenant_slug", table_name="tenants")
    op.drop_table("tenants")
