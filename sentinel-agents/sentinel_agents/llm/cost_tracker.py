"""LLM cost tracking and token usage statistics."""

import os
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TokenUsage:
    """Token usage for a single LLM call."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    model: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class CostStats:
    """Aggregated cost statistics."""

    total_calls: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    calls_by_model: dict[str, int] = field(default_factory=dict)
    tokens_by_model: dict[str, int] = field(default_factory=dict)


# Pricing per 1K tokens (approximate, USD)
MODEL_PRICING = {
    "gpt-4-turbo-preview": {"prompt": 0.01, "completion": 0.03},
    "gpt-4": {"prompt": 0.03, "completion": 0.06},
    "gpt-4o": {"prompt": 0.005, "completion": 0.015},
    "gpt-4o-mini": {"prompt": 0.00015, "completion": 0.0006},
    "gpt-3.5-turbo": {"prompt": 0.0005, "completion": 0.0015},
    "claude-sonnet-4-20250514": {"prompt": 0.003, "completion": 0.015},
    "claude-opus-4-20250514": {"prompt": 0.015, "completion": 0.075},
    "claude-haiku-4-5-20251001": {"prompt": 0.001, "completion": 0.005},
    "deepseek-v3": {"prompt": 0.00027, "completion": 0.0011},
    "llama3": {"prompt": 0.0, "completion": 0.0},  # Local model, free
}


class CostTracker:
    """Track LLM API costs and token usage."""

    def __init__(self):
        self.stats = CostStats()
        self._usage_log: list[TokenUsage] = []

    def record(self, usage: TokenUsage) -> None:
        """Record a token usage event."""
        self._usage_log.append(usage)
        self.stats.total_calls += 1
        self.stats.total_prompt_tokens += usage.prompt_tokens
        self.stats.total_completion_tokens += usage.completion_tokens
        self.stats.total_tokens += usage.total_tokens

        model = usage.model or "unknown"
        self.stats.calls_by_model[model] = self.stats.calls_by_model.get(model, 0) + 1
        self.stats.tokens_by_model[model] = (
            self.stats.tokens_by_model.get(model, 0) + usage.total_tokens
        )

        # Estimate cost
        pricing = MODEL_PRICING.get(model, {"prompt": 0.0, "completion": 0.0})
        cost = (
            usage.prompt_tokens / 1000 * pricing["prompt"]
            + usage.completion_tokens / 1000 * pricing["completion"]
        )
        self.stats.total_cost_usd += cost

    def get_summary(self) -> dict[str, Any]:
        """Get cost summary."""
        return {
            "total_calls": self.stats.total_calls,
            "total_tokens": self.stats.total_tokens,
            "total_prompt_tokens": self.stats.total_prompt_tokens,
            "total_completion_tokens": self.stats.total_completion_tokens,
            "estimated_cost_usd": round(self.stats.total_cost_usd, 4),
            "calls_by_model": self.stats.calls_by_model,
            "tokens_by_model": self.stats.tokens_by_model,
        }

    def reset(self) -> None:
        """Reset all statistics."""
        self.stats = CostStats()
        self._usage_log.clear()


# Global cost tracker
_tracker = None


def get_cost_tracker() -> CostTracker:
    """Get or create the global cost tracker."""
    global _tracker
    if _tracker is None:
        _tracker = CostTracker()
    return _tracker
