"""Shared YAML helpers.

Consolidates the ``open + safe_load + mapping validation`` pattern that was
duplicated in ``preprocessing``, ``llm.config`` and ``utils.masking``.
"""

from __future__ import annotations

import os
from typing import Any

import yaml

__all__ = ["load_mapping"]


def load_mapping(path: str, what: str = "config") -> dict[str, Any]:
    """Read a YAML file that must contain a top-level mapping.

    Missing file -> ``{}`` (callers decide whether absence is an error).
    Malformed YAML / non-mapping root -> ``ValueError``.
    """
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    if not isinstance(cfg, dict):
        raise ValueError(f"{what} must be a mapping (got {type(cfg).__name__})")
    return cfg
