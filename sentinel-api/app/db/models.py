"""Database models for Sentinel."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class Tenant(Base):
    """A tenant (organization) in multi-tenant mode."""

    __tablename__ = "tenants"

    id = Column(Integer, primary_key=True, autoincrement=True)
    slug = Column(String(64), unique=True, nullable=False)  # url-safe id, e.g. "acme-corp"
    name = Column(String(255), nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Quotas (per-tenant limits; 0 = unlimited)
    max_requests_per_minute = Column(Integer, default=0)
    max_analyses_per_day = Column(Integer, default=0)

    __table_args__ = (
        Index("idx_tenant_slug", "slug"),
        Index("idx_tenant_active", "active"),
    )


class AnalysisResult(Base):
    """Stored analysis result."""

    __tablename__ = "analysis_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Input
    log_event = Column(JSON, nullable=False)

    # Verdict
    malicious = Column(Boolean, nullable=True)
    danger_level = Column(Integer, nullable=True)
    reason = Column(Text, nullable=True)
    mitre_techniques = Column(JSON, nullable=True)
    recommended_actions = Column(JSON, nullable=True)

    # Rule hits
    rule_hits = Column(JSON, nullable=True)
    rule_hit_count = Column(Integer, default=0)

    # Agent execution
    agent_trace = Column(JSON, nullable=True)
    skipped_llm = Column(Boolean, default=False)

    # Threat intelligence
    threat_intel = Column(JSON, nullable=True)
    threat_intel_count = Column(Integer, default=0)

    # Performance
    analysis_duration_ms = Column(Float, nullable=True)

    # Metadata
    metadata_json = Column(JSON, nullable=True)
    user_id = Column(String(255), nullable=True)
    request_id = Column(String(64), nullable=True)
    tenant_id = Column(String(64), nullable=False, default="default", server_default="default")

    __table_args__ = (
        Index("idx_analysis_created_at", "created_at"),
        Index("idx_analysis_malicious", "malicious"),
        Index("idx_analysis_danger_level", "danger_level"),
        Index("idx_analysis_user_id", "user_id"),
        Index("idx_analysis_tenant_id", "tenant_id"),
        Index("idx_analysis_tenant_created", "tenant_id", "created_at"),
    )


class AuditLog(Base):
    """Security audit log entry."""

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    action = Column(String(100), nullable=False)
    user_id = Column(String(255), nullable=False)
    resource = Column(String(255), nullable=True)
    ip_address = Column(String(45), nullable=True)
    success = Column(Boolean, default=True)
    details = Column(JSON, nullable=True)
    request_id = Column(String(64), nullable=True)
    tenant_id = Column(String(64), nullable=False, default="default", server_default="default")

    __table_args__ = (
        Index("idx_audit_timestamp", "timestamp"),
        Index("idx_audit_action", "action"),
        Index("idx_audit_user_id", "user_id"),
        Index("idx_audit_tenant_id", "tenant_id"),
    )


class RuleMetadata(Base):
    """Sigma rule metadata (cached from filesystem)."""

    __tablename__ = "rule_metadata"

    id = Column(Integer, primary_key=True, autoincrement=True)
    rule_id = Column(String(50), unique=True, nullable=False)
    title = Column(String(500), nullable=False)
    level = Column(String(20), nullable=False)
    status = Column(String(20), nullable=True)
    description = Column(Text, nullable=True)
    author = Column(String(255), nullable=True)
    file_path = Column(String(500), nullable=False)
    tags = Column(JSON, nullable=True)
    mitre_techniques = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_rule_id", "rule_id"),
        Index("idx_rule_level", "level"),
    )


class SystemStats(Base):
    """Aggregated system statistics."""

    __tablename__ = "system_stats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    total_events = Column(Integer, default=0)
    total_alerts = Column(Integer, default=0)
    critical_count = Column(Integer, default=0)
    accuracy = Column(Float, nullable=True)
    avg_latency_ms = Column(Float, nullable=True)
    throughput_eps = Column(Float, nullable=True)
