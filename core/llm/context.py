"""Per-request LLM usage tracking."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field


@dataclass
class LLMUsageTracker:
    """Track model calls trong một request."""

    calls: list[dict] = field(default_factory=list)

    def record(self, response) -> None:
        self.calls.append({
            "role": response.role,
            "provider": response.provider,
            "model_ref": response.model_ref,
            "model_id": response.model_id,
            "tags": response.tags or [],
            "resolve_source": getattr(response, "resolve_source", ""),
            "fallback_used": getattr(response, "fallback_used", False),
            "prompt_tokens": response.prompt_tokens,
            "completion_tokens": response.completion_tokens,
            "used_llm": response.used_llm,
        })

    def to_list(self) -> list[dict]:
        return self.calls


_usage_ctx: ContextVar[LLMUsageTracker | None] = ContextVar("llm_usage", default=None)


def reset_usage_tracker() -> LLMUsageTracker:
    tracker = LLMUsageTracker()
    _usage_ctx.set(tracker)
    return tracker


def get_usage_tracker() -> LLMUsageTracker:
    tracker = _usage_ctx.get()
    if tracker is None:
        tracker = reset_usage_tracker()
    return tracker
