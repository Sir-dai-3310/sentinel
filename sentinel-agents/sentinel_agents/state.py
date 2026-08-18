"""State definitions for LangGraph."""

from typing import Any

from pydantic import BaseModel, Field


class RuleHit(BaseModel):
    """A rule hit from the Sigma engine."""

    rule_id: str
    rule_name: str
    technique: str
    confidence: int
    severity: str
    reason: str


class ThreatIntel(BaseModel):
    """Threat intelligence data."""

    source: str
    ioc_type: str  # ip, domain, hash, url
    ioc_value: str
    malicious: bool
    confidence: int
    details: dict[str, Any] = Field(default_factory=dict)


class Verdict(BaseModel):
    """Final analysis verdict."""

    malicious: bool
    danger_level: int = Field(ge=0, le=100)
    reason: str
    mitre_techniques: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)


class IncidentState(BaseModel):
    """State passed between agents in the graph."""

    # Input
    log: dict[str, Any]

    # Rule engine results
    rule_hits: list[RuleHit] = Field(default_factory=list)
    skipped_llm: bool = False

    # Threat intelligence
    threat_intel: list[ThreatIntel] = Field(default_factory=list)

    # LLM analysis
    llm_reasoning: str = ""

    # Final output
    verdict: Verdict | None = None

    # Agent execution trace (list of agent names, NOT LLM messages)
    agent_trace: list[str] = Field(default_factory=list)

    # Metadata
    metadata: dict[str, Any] = Field(default_factory=dict)

    class Config:
        arbitrary_types_allowed = True
