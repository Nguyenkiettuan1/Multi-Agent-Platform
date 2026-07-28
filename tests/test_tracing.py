"""Tests for tracing layer — noop fallback when Langfuse disabled."""

from __future__ import annotations

from unittest.mock import patch

from core.observability.tracing import record_llm_generation, trace_span, tracing_enabled


def test_tracing_disabled_by_default():
    assert tracing_enabled() is False


def test_trace_span_noop():
    with patch("core.observability.tracing.get_trace_id", return_value="trace-1"):
        with trace_span("test_span", user_id="u1") as ctx:
            assert ctx.trace_id == "trace-1"
            assert ctx.name == "test_span"


def test_record_llm_generation_noop_without_trace():
    record_llm_generation(
        role="assistant",
        model="gpt-4",
        messages=[{"role": "user", "content": "hi"}],
        output="hello",
    )
