"""Config-driven log preprocessing pipeline.

A ``Pipeline`` applies an ordered set of stages to each raw log dict before it
reaches the analysis graph:

  * ``field_mapping`` — rename / extract fields (``new_name: dotted.source.path``)
  * ``filters``       — drop rules; a log matching any rule is discarded
  * ``enrichment``    — static geo mapping + a threat-intel hook

Configuration lives in a YAML file (see ``config/preprocessing.yml``). When no
config file is present the pipeline is a zero-overhead no-op, so enabling it is
purely opt-in via the ``SENTINEL_PREPROCESSING_CONFIG`` env var or an explicit
path.

Typical use::

    pipeline = Pipeline.from_yaml("config/preprocessing.yml")
    result = pipeline.apply(log)   # None means the log was dropped by a filter
"""

from __future__ import annotations

import os
from typing import Any, Callable

import yaml

# A log that survives preprocessing unchanged; filters may return None to drop.
DropType = None


def _get_path(log: dict[str, Any], dotted: str) -> Any:
    """Fetch a value by dotted path (``a.b.c``); missing -> None."""
    cur: Any = log
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _set_path(log: dict[str, Any], dotted: str, value: Any) -> None:
    """Set a value by dotted path, creating intermediate dicts."""
    parts = dotted.split(".")
    cur = log
    for part in parts[:-1]:
        nxt = cur.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[part] = nxt
        cur = nxt
    cur[parts[-1]] = value


class FieldMapper:
    """Rename / extract fields: ``{new_field: "dotted.source.path"}``."""

    def __init__(self, mapping: dict[str, str]):
        self.mapping = mapping or {}

    def apply(self, log: dict[str, Any]) -> dict[str, Any]:
        for new_field, source in self.mapping.items():
            value = _get_path(log, source)
            if value is not None:
                _set_path(log, new_field, value)
        return log


class DropFilter:
    """
    Drop a log when it matches any rule.

    Each rule is ``{dotted.field.path: expected_value}``; a log matches a rule
    when *all* key/value pairs in that rule are equal. Matching any rule drops
    the log (``apply`` returns None).
    """

    def __init__(self, rules: list[dict[str, Any]]):
        self.rules = rules or []

    def apply(self, log: dict[str, Any]) -> dict[str, Any] | None:
        for rule in self.rules:
            if all(_get_path(log, k) == v for k, v in rule.items()):
                return None
        return log


class GeoEnricher:
    """Attach a static geo label to IPs via a lookup table."""

    def __init__(self, ip_field: str, table: dict[str, dict[str, Any]], out_field: str = "geo"):
        self.ip_field = ip_field
        self.table = table or {}
        self.out_field = out_field

    def apply(self, log: dict[str, Any]) -> dict[str, Any]:
        ip = _get_path(log, self.ip_field)
        if ip is not None and str(ip) in self.table:
            _set_path(log, self.out_field, self.table[str(ip)])
        return log


class ThreatIntelEnricher:
    """
    Mark logs whose extracted IOCs are on a static denylist, and (optionally)
    call a threat-intel hook. When no intel source is configured / credentialed
    the hook is skipped gracefully and only the static denylist applies.
    """

    def __init__(
        self,
        denylist: list[str] | None = None,
        hook: Callable[[dict[str, Any]], dict[str, Any] | None] | None = None,
        out_field: str = "threat_intel",
    ):
        self.denylist = set(denylist or [])
        self.hook = hook
        self.out_field = out_field

    def apply(self, log: dict[str, Any]) -> dict[str, Any]:
        hits: list[str] = []

        # Static denylist over extracted IOCs (no credentials required).
        try:
            from sentinel_agents.intelligence.ioc_extractor import IOCExtractor

            iocs = IOCExtractor.extract(log)
            flat = {v for values in iocs.values() for v in values}
            hits.extend(sorted(flat & self.denylist))
        except Exception:
            # Intelligence module unavailable -> skip static extraction.
            pass

        # Optional live hook (e.g. an intel API). Skipped silently on failure.
        if self.hook is not None:
            try:
                extra = self.hook(log) or {}
                if extra:
                    _set_path(log, self.out_field, {**(_get_path(log, self.out_field) or {}), **extra})
            except Exception:
                pass

        if hits:
            existing = _get_path(log, self.out_field) or {}
            existing = dict(existing) if isinstance(existing, dict) else {}
            existing["denylist_hits"] = hits
            _set_path(log, self.out_field, existing)
        return log


class Pipeline:
    """Ordered preprocessing stages applied to each log."""

    def __init__(self, stages: list[Any] | None = None):
        self.stages = stages or []

    def apply(self, log: dict[str, Any]) -> dict[str, Any] | None:
        """
        Run all stages. Returns the transformed log, or None if a filter
        dropped it. No stages -> the input dict is returned unchanged.
        """
        current: dict[str, Any] | None = log
        for stage in self.stages:
            if current is None:
                return None
            current = stage.apply(current)
        return current

    @classmethod
    def from_yaml(cls, path: str) -> "Pipeline":
        """
        Build a pipeline from a YAML config file.

        Raises:
            FileNotFoundError: if the config does not exist.
            ValueError: if the YAML is malformed or has unknown stage types.
        """
        if not os.path.exists(path):
            raise FileNotFoundError(f"preprocessing config not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        if not isinstance(cfg, dict):
            raise ValueError("preprocessing config must be a mapping")

        stages: list[Any] = []

        mapping = cfg.get("field_mapping")
        if mapping:
            if not isinstance(mapping, dict):
                raise ValueError("field_mapping must be a mapping of new: source")
            stages.append(FieldMapper(mapping))

        filters = cfg.get("filters")
        if filters:
            if not isinstance(filters, list):
                raise ValueError("filters must be a list of drop rules")
            stages.append(DropFilter(filters))

        enrichment = cfg.get("enrichment") or {}
        if enrichment:
            geo = enrichment.get("geo")
            if geo:
                stages.append(
                    GeoEnricher(
                        ip_field=geo.get("ip_field", "source.ip"),
                        table=geo.get("table", {}),
                        out_field=geo.get("out_field", "geo"),
                    )
                )
            intel = enrichment.get("threat_intel")
            if intel:
                stages.append(
                    ThreatIntelEnricher(
                        denylist=intel.get("denylist", []),
                        out_field=intel.get("out_field", "threat_intel"),
                    )
                )

        return cls(stages)


# ---------------------------------------------------------------------------
# Lazy global pipeline (zero-overhead no-op when unconfigured)
# ---------------------------------------------------------------------------

_PIPELINE: Pipeline | None = None
_LOADED = False


def get_pipeline() -> Pipeline:
    """
    Return the configured pipeline, or an empty (no-op) pipeline.

    Resolution order:
      1. ``SENTINEL_PREPROCESSING_CONFIG`` env var (explicit path)
      2. ``config/preprocessing.yml`` beside the repo root, if present
      3. empty no-op pipeline
    """
    global _PIPELINE, _LOADED
    if _LOADED:
        return _PIPELINE or Pipeline()

    _LOADED = True
    path = os.getenv("SENTINEL_PREPROCESSING_CONFIG")
    if not path:
        default = os.path.join("config", "preprocessing.yml")
        path = default if os.path.exists(default) else None

    if path and os.path.exists(path):
        try:
            _PIPELINE = Pipeline.from_yaml(path)
        except Exception as e:  # bad config must not break analysis
            print(f"⚠️  preprocessing config invalid ({e}); running without preprocessing")
            _PIPELINE = Pipeline()
    else:
        _PIPELINE = Pipeline()
    return _PIPELINE


def reset_pipeline() -> None:
    """Reset the cached pipeline (used by tests)."""
    global _PIPELINE, _LOADED
    _PIPELINE = None
    _LOADED = False


def preprocess(log: dict[str, Any]) -> dict[str, Any] | None:
    """Module-level helper: apply the configured pipeline to one log."""
    return get_pipeline().apply(log)
