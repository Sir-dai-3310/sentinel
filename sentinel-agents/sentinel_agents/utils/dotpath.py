"""Shared dotted-path helpers for reading/writing nested dict values.

Previously duplicated verbatim in ``utils.masking`` and ``preprocessing``; the
only behavioural difference was whether ``set_path`` creates missing parent
dicts, which is now controlled by the ``create_missing`` flag.
"""

from __future__ import annotations

from typing import Any

__all__ = ["get_path", "set_path"]


def get_path(obj: dict[str, Any], dotted: str) -> Any:
    """Fetch a value by dotted path (``a.b.c``); missing -> ``None``."""
    cur: Any = obj
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def set_path(
    obj: dict[str, Any],
    dotted: str,
    value: Any,
    *,
    create_missing: bool = False,
) -> None:
    """Set a value by dotted path.

    Args:
        create_missing: when True, intermediate dicts are created as needed
            (preprocessing semantics). When False, a missing parent path is a
            no-op and, additionally, the leaf is only written if it already
            exists (masking semantics: never introduce new keys).
    """
    parts = dotted.split(".")
    cur = obj
    for part in parts[:-1]:
        nxt = cur.get(part)
        if not isinstance(nxt, dict):
            if not create_missing:
                return  # parent path missing -> nothing to do
            nxt = {}
            cur[part] = nxt
        cur = nxt
    if create_missing or parts[-1] in cur:
        cur[parts[-1]] = value
