"""Agent implementations with real LLM integration."""

import os
from abc import ABC, abstractmethod

from sentinel_agents.llm import LLMClient, get_default_client
from sentinel_agents.state import IncidentState, RuleHit, Verdict


class BaseAgent(ABC):
    """Base class for all agents."""

    def __init__(self, llm_client: LLMClient | None = None):
        """
        Initialize agent.

        Args:
            llm_client: LLM client (if None, uses default)
        """
        self.llm = llm_client or get_default_client()

    @abstractmethod
    async def __call__(self, state: IncidentState) -> IncidentState:
        """Process the state and return updated state."""
        pass

    def record_trace(self, state: IncidentState, agent_name: str) -> None:
        """Record agent execution in trace."""
        state.agent_trace.append(agent_name)


class TriageAgent(BaseAgent):
    """
    First-level triage: run Sigma rules, decide if LLM is needed.

    Uses the Rust Sigma engine for high-performance rule matching.
    """

    def __init__(self, llm_client: LLMClient | None = None, rules_dir: str = "rules"):
        super().__init__(llm_client)
        self.rules_dir = rules_dir
        self._engine = None

    def _get_engine(self):
        """Lazy-load Sigma engine."""
        if self._engine is None:
            try:
                # Import Rust core (requires maturin build)
                import sentinel_core

                self._engine = sentinel_core.SigmaEngine(self.rules_dir)
            except ImportError:
                # Fallback: Python-based rule matching
                print("Warning: sentinel_core not available, using Python fallback")
                self._engine = None
        return self._engine

    async def __call__(self, state: IncidentState) -> IncidentState:
        self.record_trace(state, "TriageAgent")

        # Run Sigma rules
        engine = self._get_engine()
        if engine:
            # Use Rust engine
            # hits = engine.evaluate(state.log)
            # For now, placeholder until Rust-Python integration is complete
            state.rule_hits = self._python_rule_fallback(state.log)
        else:
            # Python fallback
            state.rule_hits = self._python_rule_fallback(state.log)

        # If high confidence hit, create verdict directly
        if any(hit.confidence >= 90 for hit in state.rule_hits):
            top_hit = max(state.rule_hits, key=lambda h: h.confidence)
            state.verdict = Verdict(
                malicious=True,
                danger_level=top_hit.confidence,
                reason=f"[{top_hit.rule_id}] {top_hit.reason}",
                mitre_techniques=[top_hit.technique],
                recommended_actions=[
                    "Isolate affected host",
                    "Collect forensic evidence",
                    "Review similar events in the environment",
                ],
            )
            state.skipped_llm = True

        return state

    def _python_rule_fallback(self, log: dict) -> list[RuleHit]:
        """
        Fallback rule matching in Python (when Rust engine not available).

        This is a simplified implementation for the 4 example rules.
        """
        hits = []
        cmd = str(log.get("CommandLine", "")).lower()
        image = str(log.get("Image", "")).lower()

        # R001: PowerShell encoded
        if "powershell" in image and ("-enc" in cmd or "-encodedcommand" in cmd):
            hits.append(
                RuleHit(
                    rule_id="R001",
                    rule_name="PowerShell Encoded Command",
                    technique="T1059.001",
                    confidence=85,
                    severity="high",
                    reason="PowerShell with encoded command detected",
                )
            )

        # R011: Mimikatz
        if any(kw in cmd for kw in ["sekurlsa::", "lsad::dump", "mimikatz"]):
            hits.append(
                RuleHit(
                    rule_id="R011",
                    rule_name="Mimikatz Command Line",
                    technique="T1003",
                    confidence=96,
                    severity="critical",
                    reason="Mimikatz credential dumping tool detected",
                )
            )

        return hits


class AnalystAgent(BaseAgent):
    """
    Deep LLM analysis with threat intelligence enrichment.
    """

    def __init__(self, llm_client=None, enable_threat_intel: bool = True):
        super().__init__(llm_client)
        self.enable_threat_intel = enable_threat_intel
        self._intel_aggregator = None

    def _get_intel_aggregator(self):
        """Lazy-load threat intelligence aggregator."""
        if self._intel_aggregator is None and self.enable_threat_intel:
            from sentinel_agents.intelligence import (
                AbuseIPDBProvider,
                IntelligenceAggregator,
                VirusTotalProvider,
            )

            providers = []
            if os.getenv("VT_API_KEY"):
                providers.append(VirusTotalProvider())
            if os.getenv("ABUSEIPDB_API_KEY"):
                providers.append(AbuseIPDBProvider())

            if providers:
                self._intel_aggregator = IntelligenceAggregator(providers)

        return self._intel_aggregator

    async def __call__(self, state: IncidentState) -> IncidentState:
        self.record_trace(state, "AnalystAgent")

        if state.skipped_llm:
            return state

        # Enrich with threat intelligence
        if self.enable_threat_intel:
            await self._enrich_with_threat_intel(state)

        # Build context from rule hits and threat intel
        context = self._build_context(state)

        # Import here to avoid circular dependency
        from sentinel_agents.llm.prompts import build_analysis_prompt

        # Call LLM with structured output
        try:
            prompt = build_analysis_prompt(state.log, context)
            verdict = await self.llm.ainvoke_structured(prompt, Verdict)
            state.verdict = verdict

        except Exception as e:
            # Graceful degradation on LLM failure
            state.verdict = Verdict(
                malicious=False,
                danger_level=0,
                reason=f"LLM analysis failed: {str(e)}. Manual review required.",
                mitre_techniques=[],
                recommended_actions=["Manual analysis required due to LLM failure"],
            )

        return state

    async def _enrich_with_threat_intel(self, state: IncidentState) -> None:
        """Extract IOCs and lookup threat intelligence."""
        from sentinel_agents.intelligence.ioc_extractor import IOCExtractor

        aggregator = self._get_intel_aggregator()
        if not aggregator:
            return

        # Extract IOCs
        iocs = IOCExtractor.extract(state.log)

        # Lookup each IOC type
        for ip in iocs["ips"][:3]:  # Limit to 3 IPs to avoid rate limits
            results = await aggregator.lookup_ip(ip)
            state.threat_intel.extend(results)

        for file_hash in iocs["hashes"][:3]:
            results = await aggregator.lookup_hash(file_hash)
            state.threat_intel.extend(results)

        for domain in iocs["domains"][:3]:
            results = await aggregator.lookup_domain(domain)
            state.threat_intel.extend(results)

    def _build_context(self, state: IncidentState) -> str:
        """Build context string from rule hits and threat intel."""
        parts = []

        if state.rule_hits:
            hits_str = "; ".join(
                f"{hit.rule_name} ({hit.technique}, confidence: {hit.confidence})"
                for hit in state.rule_hits
            )
            parts.append(f"Rule engine detected: {hits_str}")

        if state.threat_intel:
            malicious_iocs = [ti for ti in state.threat_intel if ti.malicious]
            if malicious_iocs:
                ti_str = "; ".join(
                    f"{ti.ioc_type} {ti.ioc_value} flagged by {ti.source}"
                    for ti in malicious_iocs
                )
                parts.append(f"Threat intelligence: {ti_str}")

        return "\n".join(parts)


class HunterAgent(BaseAgent):
    """
    Generate threat hunting hypotheses.
    """

    async def __call__(self, state: IncidentState) -> IncidentState:
        self.record_trace(state, "HunterAgent")

        if not state.verdict or not state.verdict.malicious:
            return state

        # Generate hunting queries
        from sentinel_agents.llm.prompts import build_hunting_prompt

        try:
            prompt = build_hunting_prompt(state.verdict.model_dump())
            queries = await self.llm.ainvoke(prompt)
            state.metadata["hunting_queries"] = queries
        except Exception as e:
            state.metadata["hunting_queries_error"] = str(e)

        return state


class ReporterAgent(BaseAgent):
    """
    Generate final structured report.
    """

    async def __call__(self, state: IncidentState) -> IncidentState:
        self.record_trace(state, "ReporterAgent")

        if not state.verdict:
            return state

        # Generate comprehensive report
        from sentinel_agents.llm.prompts import build_report_prompt

        try:
            prompt = build_report_prompt(state.model_dump())
            report = await self.llm.ainvoke(prompt)
            state.metadata["report"] = report
        except Exception as e:
            state.metadata["report_error"] = str(e)

        return state
