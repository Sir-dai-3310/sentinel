"""Initial schema: analysis_results, audit_logs, rule_metadata, system_stats

Revision ID: 001_initial
Revises:
Create Date: 2026-08-18

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Analysis results table
    op.create_table(
        "analysis_results",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("log_event", sa.JSON(), nullable=False),
        sa.Column("malicious", sa.Boolean(), nullable=True),
        sa.Column("danger_level", sa.Integer(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("mitre_techniques", sa.JSON(), nullable=True),
        sa.Column("recommended_actions", sa.JSON(), nullable=True),
        sa.Column("rule_hits", sa.JSON(), nullable=True),
        sa.Column("rule_hit_count", sa.Integer(), nullable=True),
        sa.Column("agent_trace", sa.JSON(), nullable=True),
        sa.Column("skipped_llm", sa.Boolean(), nullable=True),
        sa.Column("threat_intel", sa.JSON(), nullable=True),
        sa.Column("threat_intel_count", sa.Integer(), nullable=True),
        sa.Column("analysis_duration_ms", sa.Float(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("user_id", sa.String(255), nullable=True),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_analysis_created_at", "analysis_results", ["created_at"])
    op.create_index("idx_analysis_malicious", "analysis_results", ["malicious"])
    op.create_index("idx_analysis_danger_level", "analysis_results", ["danger_level"])
    op.create_index("idx_analysis_user_id", "analysis_results", ["user_id"])

    # Audit logs table
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("resource", sa.String(255), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_audit_timestamp", "audit_logs", ["timestamp"])
    op.create_index("idx_audit_action", "audit_logs", ["action"])
    op.create_index("idx_audit_user_id", "audit_logs", ["user_id"])

    # Rule metadata table
    op.create_table(
        "rule_metadata",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("rule_id", sa.String(50), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("level", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("author", sa.String(255), nullable=True),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("mitre_techniques", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("rule_id"),
    )
    op.create_index("idx_rule_id", "rule_metadata", ["rule_id"])
    op.create_index("idx_rule_level", "rule_metadata", ["level"])

    # System stats table
    op.create_table(
        "system_stats",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("total_events", sa.Integer(), nullable=True),
        sa.Column("total_alerts", sa.Integer(), nullable=True),
        sa.Column("critical_count", sa.Integer(), nullable=True),
        sa.Column("accuracy", sa.Float(), nullable=True),
        sa.Column("avg_latency_ms", sa.Float(), nullable=True),
        sa.Column("throughput_eps", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("system_stats")
    op.drop_table("rule_metadata")
    op.drop_table("audit_logs")
    op.drop_table("analysis_results")
