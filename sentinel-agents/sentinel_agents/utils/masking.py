"""Rule-based field masking for sensitive data (GDPR/CCPA storage hygiene).

Masking is applied to analysis results *before* persistence so that sensitive
values are never written to the database in the clear ("store masked").

Strategies:
  * ``redact``  — replace the whole value with ``***``
  * ``hash``    — replace with a truncated SHA-256 hex digest (stable, unlinkable)
  * ``partial`` — keep a safe prefix; for IPv4 keeps the first two octets,
                  otherwise keeps the first N characters then ``***``

Fields are selected by dotted path (``user.name``, ``source.ip``,
``process.command_line``). A YAML config (see ``config/masking.yml``) plus the
``MASKING_ENABLED`` env var control behaviour; when disabled the payload is
returned untouched.
"""

from __future__ import annotations

import hashlib
import os
from typing import Any

from .dotpath import get_path, set_path
from .yamlutil import load_mapping

REDACTED = "***"


def _mask_value(value: Any, strategy: str) -> Any:
    """Apply one masking strategy to a single value."""
    if value is None:
        return value
    text = str(value)
    if strategy == "redact":
        return REDACTED
    if strategy == "hash":
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    if strategy == "partial":
        # IPv4: keep first two octets (192.168.***.***)
        parts = text.split(".")
        if len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
            return f"{parts[0]}.{parts[1]}.{REDACTED}.{REDACTED}"
        # Generic: keep first 3 chars
        keep = text[:3]
        return f"{keep}{REDACTED}"
    # Unknown strategy -> safe default: redact
    return REDACTED


class Masker:
    """Apply configured masking rules to a payload dict."""

    def __init__(self, rules: list[dict[str, str]] | None = None, enabled: bool = True):
        """
        Args:
            rules: list of ``{"path": dotted.path, "strategy": redact|hash|partial}``
            enabled: when False, masking is a pass-through.
        """
        self.rules = rules or []
        self.enabled = enabled

    def mask(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Return a masked copy of the payload. Disabled -> returns the input
        unchanged (same object, zero overhead).
        """
        if not self.enabled or not self.rules:
            return payload
        import copy

        out = copy.deepcopy(payload)
        for rule in self.rules:
            path = rule.get("path", "")
            strategy = rule.get("strategy", "redact")
            if not path:
                continue
            current = get_path(out, path)
            if current is not None:
                set_path(out, path, _mask_value(current, strategy))
        return out

    @classmethod
    def from_yaml(cls, path: str, enabled: bool | None = None) -> "Masker":
        """
        Build a Masker from a YAML config.

        Config shape::

            enabled: true
            rules:
              - {path: user.name, strategy: redact}
              - {path: source.ip, strategy: partial}

        ``enabled`` arg overrides the file; the ``MASKING_ENABLED`` env var
        overrides both when set.
        """
        cfg = load_mapping(path, "masking config")
        rules = cfg.get("rules", [])
        if not isinstance(rules, list):
            raise ValueError("masking 'rules' must be a list")

        eff_enabled = cfg.get("enabled", True) if enabled is None else enabled
        env = os.getenv("MASKING_ENABLED")
        if env is not None:
            eff_enabled = env.lower() == "true"
        return cls(rules=rules, enabled=bool(eff_enabled))


# ---------------------------------------------------------------------------
# Lazy global masker
# ---------------------------------------------------------------------------

_MASKER: Masker | None = None
_LOADED = False


def get_masker() -> Masker:
    """
    Return the configured masker.

    Enabled only when ``MASKING_ENABLED=true``. Config path from
    ``SENTINEL_MASKING_CONFIG`` (default ``config/masking.yml``). Any config
    problem yields a *disabled* pass-through masker so analysis never breaks.
    """
    global _MASKER, _LOADED
    if _LOADED:
        return _MASKER or Masker(enabled=False)

    _LOADED = True
    if os.getenv("MASKING_ENABLED", "false").lower() != "true":
        _MASKER = Masker(enabled=False)
        return _MASKER

    path = os.getenv("SENTINEL_MASKING_CONFIG", os.path.join("config", "masking.yml"))
    try:
        _MASKER = Masker.from_yaml(path, enabled=True)
    except Exception as e:
        print(f"⚠️  masking config invalid ({e}); masking disabled")
        _MASKER = Masker(enabled=False)
    return _MASKER


def reset_masker() -> None:
    """Reset the cached masker (used by tests)."""
    global _MASKER, _LOADED
    _MASKER = None
    _LOADED = False


def mask(payload: dict[str, Any]) -> dict[str, Any]:
    """Module-level helper: mask a payload with the configured masker."""
    return get_masker().mask(payload)
