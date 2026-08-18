"""LLM prompts for security analysis."""


def build_analysis_prompt(log: dict, context: str = "") -> str:
    """
    Build prompt for security log analysis.

    Args:
        log: Log event dictionary
        context: Additional context (e.g., from rule hits)

    Returns:
        Formatted prompt
    """
    base_prompt = f"""You are a security analyst AI. Analyze this security log and provide a structured verdict.

Log Event:
{_format_log(log)}
"""

    if context:
        base_prompt += f"""
Additional Context:
{context}
"""

    base_prompt += """
Provide your analysis in the following format:
- malicious: true/false (whether this log indicates malicious activity)
- danger_level: 0-100 (0=benign, 100=critical threat)
- reason: detailed explanation of your verdict
- mitre_techniques: list of relevant MITRE ATT&CK technique IDs (e.g., ["T1059.001"])
- recommended_actions: list of recommended response actions

Be precise and base your verdict on evidence in the log.
"""

    return base_prompt


def _format_log(log: dict) -> str:
    """Format log dictionary as readable string."""
    lines = []
    for key, value in log.items():
        lines.append(f"  {key}: {value}")
    return "\n".join(lines)


def build_hunting_prompt(verdict: dict) -> str:
    """
    Build prompt for threat hunting query generation.

    Args:
        verdict: Verdict dictionary

    Returns:
        Formatted prompt
    """
    return f"""Based on this security verdict, generate threat hunting queries to validate and expand the finding.

Verdict:
{_format_log(verdict)}

Generate 3-5 specific, actionable hunting queries that a security analyst could run to:
1. Validate this finding
2. Find related malicious activity
3. Assess the scope of compromise

Format each query as a clear, executable statement.
"""


def build_report_prompt(state: dict) -> str:
    """
    Build prompt for incident report generation.

    Args:
        state: Complete analysis state

    Returns:
        Formatted prompt
    """
    return f"""Generate a professional security incident report based on this analysis:

{_format_log(state)}

Include:
1. Executive Summary
2. Technical Details
3. MITRE ATT&CK Mapping
4. Recommended Actions
5. Indicators of Compromise (IOCs)

Format as structured Markdown.
"""
