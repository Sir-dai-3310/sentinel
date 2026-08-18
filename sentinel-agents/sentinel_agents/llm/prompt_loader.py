"""Prompt template loader.

Loads versioned prompt templates from Markdown files. Each template file may
carry a header comment (``<!-- prompt: <name>  version: X.Y.Z -->``) used for
versioning/auditing.

Resolution order for a template named ``<name>``:
  1. ``$SENTINEL_PROMPTS_DIR/<name>.md``  (operator override directory)
  2. ``<package>/prompts/<name>.md``       (bundled defaults, repo: sentinel-agents/prompts)
  3. built-in default string               (fallback if files are missing/corrupt)

This guarantees the agents keep working even with no template files present.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

# Built-in defaults — the last-resort fallback when no file is readable.
DEFAULT_TEMPLATES: dict[str, str] = {
    "analysis": (
        "You are a security analyst AI. Analyze this security log and provide a "
        "structured verdict.\n\nLog Event:\n{log}\n{context_block}\n"
        "Provide your analysis in the following format:\n"
        "- malicious: true/false (whether this log indicates malicious activity)\n"
        "- danger_level: 0-100 (0=benign, 100=critical threat)\n"
        "- reason: detailed explanation of your verdict\n"
        "- mitre_techniques: list of relevant MITRE ATT&CK technique IDs (e.g., [\"T1059.001\"])\n"
        "- recommended_actions: list of recommended response actions\n\n"
        "Be precise and base your verdict on evidence in the log.\n"
    ),
    "hunting": (
        "Based on this security verdict, generate threat hunting queries to validate "
        "and expand the finding.\n\nVerdict:\n{verdict}\n\n"
        "Generate 3-5 specific, actionable hunting queries that a security analyst could run to:\n"
        "1. Validate this finding\n2. Find related malicious activity\n3. Assess the scope of compromise\n\n"
        "Format each query as a clear, executable statement.\n"
    ),
    "report": (
        "Generate a professional security incident report based on this analysis:\n\n{state}\n\n"
        "Include:\n1. Executive Summary\n2. Technical Details\n3. MITRE ATT&CK Mapping\n"
        "4. Recommended Actions\n5. Indicators of Compromise (IOCs)\n\n"
        "Format as structured Markdown.\n"
    ),
}

_VERSION_RE = re.compile(r"version:\s*([0-9]+\.[0-9]+\.[0-9]+)")

# Bundled prompts dir: sentinel-agents/prompts (one level above the package).
_BUNDLED_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"


def template_version(text: str) -> str | None:
    """Extract the version from a template's header comment, if present."""
    first_line = text.splitlines()[0] if text else ""
    m = _VERSION_RE.search(first_line)
    return m.group(1) if m else None


def _read_file(path: Path) -> str | None:
    """Read a template file, returning None on any failure."""
    try:
        if path.is_file():
            return path.read_text(encoding="utf-8")
    except Exception:
        return None
    return None


def load_template(name: str) -> str:
    """
    Load a prompt template by name.

    Returns the template body (header comment stripped). Falls back to the
    built-in default when files are missing or unreadable.
    """
    # 1. Operator override directory
    override_dir = os.getenv("SENTINEL_PROMPTS_DIR")
    if override_dir:
        text = _read_file(Path(override_dir) / f"{name}.md")
        if text is not None:
            return _strip_header(text)

    # 2. Bundled defaults
    text = _read_file(_BUNDLED_DIR / f"{name}.md")
    if text is not None:
        return _strip_header(text)

    # 3. Built-in fallback
    return DEFAULT_TEMPLATES.get(name, "")


def _strip_header(text: str) -> str:
    """Remove a leading HTML-comment header line from a template."""
    lines = text.splitlines(keepends=True)
    if lines and lines[0].lstrip().startswith("<!--"):
        return "".join(lines[1:])
    return text
