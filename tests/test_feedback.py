"""Tests for feedback loop — chat trace + rating + export."""

from __future__ import annotations

import json

import pytest

from core.intelligence.feedback import get_by_trace_id, list_feedback
from core.intelligence.feedback_store import (
    apply_user_rating,
    export_training_dataset,
    save_chat_trace,
)


@pytest.fixture(autouse=True)
def clear_feedback():
    from core.intelligence import feedback

    feedback._feedback_by_trace.clear()
    yield
    feedback._feedback_by_trace.clear()


def test_save_chat_trace_and_rate():
    save_chat_trace(
        trace_id="t1",
        session_id="s1",
        user_message="Xin chào",
        response="Chào bạn!",
        eval_score=0.85,
    )
    rec = get_by_trace_id("t1")
    assert rec is not None
    assert rec.user_message == "Xin chào"
    assert rec.eval_score == 0.85
    assert rec.rating is None

    assert apply_user_rating(trace_id="t1", rating=5, comment="tốt")
    rec = get_by_trace_id("t1")
    assert rec.rating == 5
    assert rec.comment == "tốt"


def test_rate_unknown_trace_fails_without_db():
    assert not apply_user_rating(trace_id="missing", rating=3)


def test_export_openai_format():
    save_chat_trace(
        trace_id="t2",
        session_id="s1",
        user_message="Hỏi",
        response="Đáp",
        eval_score=0.9,
    )
    apply_user_rating(trace_id="t2", rating=5)

    out = export_training_dataset(min_rating=4, fmt="openai", limit=10)
    lines = [json.loads(ln) for ln in out.strip().split("\n")]
    assert len(lines) == 1
    assert lines[0]["messages"][0]["role"] == "user"
    assert lines[0]["messages"][1]["content"] == "Đáp"


def test_export_filters_low_rating():
    save_chat_trace(
        trace_id="good",
        session_id="s",
        user_message="a",
        response="b",
        eval_score=1.0,
    )
    apply_user_rating(trace_id="good", rating=5)

    save_chat_trace(
        trace_id="bad",
        session_id="s",
        user_message="c",
        response="d",
        eval_score=1.0,
    )
    apply_user_rating(trace_id="bad", rating=2)

    out = export_training_dataset(min_rating=4, fmt="pairs", limit=10)
    lines = [json.loads(ln) for ln in out.strip().split("\n")]
    assert len(lines) == 1
    assert lines[0]["trace_id"] == "good"
