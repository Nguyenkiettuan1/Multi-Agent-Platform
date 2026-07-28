"""Feedback loop — chat traces → eval → training dataset."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class FeedbackRecord:
    trace_id: str
    session_id: str
    user_message: str
    response: str
    rating: int | None = None  # 1-5 thumbs
    comment: str = ""
    eval_score: float | None = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


_feedback_by_trace: dict[str, FeedbackRecord] = {}


def upsert_feedback(record: FeedbackRecord) -> None:
    _feedback_by_trace[record.trace_id] = record


def record_feedback(record: FeedbackRecord) -> None:
    upsert_feedback(record)


def get_by_trace_id(trace_id: str) -> FeedbackRecord | None:
    return _feedback_by_trace.get(trace_id)


def list_feedback(*, trace_id: str | None = None, limit: int = 50) -> list[FeedbackRecord]:
    items = list(_feedback_by_trace.values())
    if trace_id:
        items = [f for f in items if f.trace_id == trace_id]
    items.sort(key=lambda f: f.created_at, reverse=True)
    return items[:limit]
