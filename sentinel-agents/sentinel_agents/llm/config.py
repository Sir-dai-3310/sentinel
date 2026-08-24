"""Per-task LLM configuration loader.

Reads ``config/llm.yml`` (path overridable via ``SENTINEL_LLM_CONFIG``) which
maps each agent task (``triage`` / ``analyst`` / ``hunter`` / ``reporter``) to
its provider and generation parameters::

    default: {provider: openai, model: gpt-4o-mini, temperature: 0.2}
    tasks:
      triage:   {provider: ollama, model: llama3, temperature: 0.1, max_tokens: 512}
      analyst:  {provider: openai, model: gpt-4o, temperature: 0.2, top_p: 0.9}
      ...

Any task missing from the file falls back to ``default``; a missing file
yields an empty config and env-var-driven behaviour (unchanged from before).
"""

from __future__ import annotations

import os
from typing import Any

from ..utils.yamlutil import load_mapping

TASKS = ("triage", "analyst", "hunter", "reporter")

_DEFAULT_PATH = os.path.join("config", "llm.yml")


class LLMConfig:
    """Resolved per-task LLM settings."""

    def __init__(self, default: dict[str, Any] | None = None, tasks: dict[str, dict] | None = None):
        self.default = default or {}
        self.tasks = tasks or {}

    def for_task(self, task: str) -> dict[str, Any]:
        """
        Effective settings for a task: ``default`` overlaid with the task's
        own keys (task wins). Unknown tasks return just the default block.
        """
        merged = dict(self.default)
        merged.update(self.tasks.get(task, {}))
        return merged

    @classmethod
    def from_yaml(cls, path: str | None = None) -> "LLMConfig":
        """
        Load config from YAML. Missing file -> empty config (env-driven).
        Malformed YAML -> ValueError.
        """
        path = path or os.getenv("SENTINEL_LLM_CONFIG", _DEFAULT_PATH)
        cfg = load_mapping(path, "llm config")
        tasks = cfg.get("tasks", {})
        if not isinstance(tasks, dict):
            raise ValueError("llm config 'tasks' must be a mapping")
        return cls(default=cfg.get("default", {}), tasks=tasks)


# Lazy global
_CONFIG: LLMConfig | None = None
_LOADED = False


def get_llm_config() -> LLMConfig:
    """Return the cached LLM config (loading on first use)."""
    global _CONFIG, _LOADED
    if not _LOADED:
        _LOADED = True
        try:
            _CONFIG = LLMConfig.from_yaml()
        except Exception as e:
            print(f"⚠️  llm config invalid ({e}); using env-driven defaults")
            _CONFIG = LLMConfig()
    return _CONFIG or LLMConfig()


def reset_llm_config() -> None:
    """Reset the cached config (used by tests)."""
    global _CONFIG, _LOADED
    _CONFIG = None
    _LOADED = False
