"""LLM prompts for security analysis.

Prompt *templates* are externalized to Markdown files (see
``sentinel-agents/prompts/``) and loaded via
:mod:`sentinel_agents.llm.prompt_loader`. Operators can override them with the
``SENTINEL_PROMPTS_DIR`` env var; built-in defaults are used as a fallback.
These builder functions keep their original signatures and output semantics.
"""

from sentinel_agents.llm.prompt_loader import load_template


def _format_log(log: dict) -> str:
    """Format log dictionary as readable string."""
    lines = []
    for key, value in log.items():
        lines.append(f"  {key}: {value}")
    return "\n".join(lines)


def build_analysis_prompt(log: dict, context: str = "") -> str:
    """
    Build prompt for security log analysis.

    Args:
        log: Log event dictionary
        context: Additional context (e.g., from rule hits)

    Returns:
        Formatted prompt
    """
    context_block = ""
    if context:
        context_block = f"""
Additional Context:
{context}
"""
    template = load_template("analysis")
    return template.format(log=_format_log(log), context_block=context_block)


def build_hunting_prompt(verdict: dict) -> str:
    """
    Build prompt for threat hunting query generation.

    Args:
        verdict: Verdict dictionary

    Returns:
        Formatted prompt
    """
    template = load_template("hunting")
    return template.format(verdict=_format_log(verdict))


def build_report_prompt(state: dict) -> str:
    """
    Build prompt for incident report generation.

    Args:
        state: Complete analysis state

    Returns:
        Formatted prompt
    """
    template = load_template("report")
    return template.format(state=_format_log(state))
