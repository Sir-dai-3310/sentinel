"""Response models for the Sentinel SDK.

Plain dataclasses with ``from_dict`` constructors — no third-party deps
beyond httpx at runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _get(data: dict[str, Any], key: str, default: Any = None) -> Any:
    value = data.get(key, default)
    return default if value is None else value


@dataclass
class Token:
    """JWT token response."""

    access_token: str
    token_type: str = "bearer"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Token":
        return cls(access_token=data["access_token"], token_type=_get(data, "token_type", "bearer"))


@dataclass
class Health:
    """Health check response."""

    status: str
    version: str
    services: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Health":
        return cls(
            status=data.get("status", "unknown"),
            version=data.get("version", "unknown"),
            services=_get(data, "services", {}),
        )


@dataclass
class RuleSummary:
    """Rule entry as returned by the list endpoint."""

    id: str
    title: str
    level: str
    file_path: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RuleSummary":
        return cls(
            id=data.get("id", "unknown"),
            title=data.get("title", "Untitled"),
            level=data.get("level", "medium"),
            file_path=data.get("file_path", ""),
        )


@dataclass
class Rule:
    """Full Sigma rule."""

    id: str
    title: str
    logsource: dict[str, Any] = field(default_factory=dict)
    detection: dict[str, Any] = field(default_factory=dict)
    description: str | None = None
    level: str = "medium"
    status: str = "stable"
    author: str | None = None
    tags: list[str] = field(default_factory=list)
    falsepositives: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Rule":
        return cls(
            id=data.get("id", ""),
            title=data.get("title", ""),
            logsource=_get(data, "logsource", {}),
            detection=_get(data, "detection", {}),
            description=data.get("description"),
            level=_get(data, "level", "medium"),
            status=_get(data, "status", "stable"),
            author=data.get("author"),
            tags=_get(data, "tags", []),
            falsepositives=_get(data, "falsepositives", []),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize for create/update payloads (omit Nones like the API does)."""
        out: dict[str, Any] = {
            "id": self.id,
            "title": self.title,
            "level": self.level,
            "status": self.status,
            "logsource": self.logsource,
            "detection": self.detection,
            "tags": self.tags,
            "falsepositives": self.falsepositives,
        }
        if self.description is not None:
            out["description"] = self.description
        if self.author is not None:
            out["author"] = self.author
        return out


@dataclass
class RuleList:
    """Rule listing response."""

    total: int
    rules: list[RuleSummary]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RuleList":
        return cls(
            total=data.get("total", 0),
            rules=[RuleSummary.from_dict(r) for r in _get(data, "rules", [])],
        )


@dataclass
class AnalysisResult:
    """Result of analyzing a single log event."""

    verdict: dict[str, Any] | None
    rule_hits: list[dict[str, Any]] = field(default_factory=list)
    threat_intel: list[dict[str, Any]] = field(default_factory=list)
    agent_trace: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    skipped_llm: bool = False
    analysis_status: str = "completed"
    analysis_error: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AnalysisResult":
        return cls(
            verdict=data.get("verdict"),
            rule_hits=_get(data, "rule_hits", []),
            threat_intel=_get(data, "threat_intel", []),
            agent_trace=_get(data, "agent_trace", []),
            metadata=_get(data, "metadata", {}),
            skipped_llm=_get(data, "skipped_llm", False),
            analysis_status=_get(data, "analysis_status", "completed"),
            analysis_error=data.get("analysis_error"),
        )


@dataclass
class BatchAnalysisResult:
    """Result of a batch analysis."""

    results: list[dict[str, Any]]
    total: int
    successful: int
    failed: int
    throughput_eps: float

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BatchAnalysisResult":
        return cls(
            results=_get(data, "results", []),
            total=data.get("total", 0),
            successful=data.get("successful", 0),
            failed=data.get("failed", 0),
            throughput_eps=data.get("throughput_eps", 0.0),
        )


@dataclass
class ImportStatus:
    """Bulk-import task progress."""

    task_id: str
    status: str
    total: int = 0
    processed: int = 0
    failed: int = 0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ImportStatus":
        return cls(
            task_id=data.get("task_id", ""),
            status=data.get("status", "unknown"),
            total=data.get("total", 0),
            processed=data.get("processed", 0),
            failed=data.get("failed", 0),
        )


@dataclass
class Stats:
    """Dashboard statistics."""

    total_events: int
    alerts: int
    critical: int
    accuracy: float

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Stats":
        return cls(
            total_events=data.get("total_events", 0),
            alerts=data.get("alerts", 0),
            critical=data.get("critical", 0),
            accuracy=data.get("accuracy", 0.0),
        )
