"""Distributed tracing — Langfuse integration with safe fallback."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Generator

from config import get_settings
from core.llm.secrets import resolve_env
from core.observability.logging import get_trace_id

logger = logging.getLogger(__name__)


@dataclass
class SpanContext:
    name: str
    trace_id: str
    span_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    _recorder: Any = None


class _NoOpRecorder:
    @contextmanager
    def span(self, name: str, *, trace_id: str, metadata: dict | None = None) -> Generator[SpanContext, None, None]:
        yield SpanContext(name=name, trace_id=trace_id, metadata=metadata or {})

    def generation(
        self,
        *,
        trace_id: str,
        name: str,
        model: str,
        input_messages: list[dict],
        output: str,
        usage: dict[str, int],
        metadata: dict | None = None,
    ) -> None:
        return None


class _LangfuseRecorder:
    def __init__(self) -> None:
        from langfuse import Langfuse

        settings = get_settings()
        self._client = Langfuse(
            public_key=resolve_env("LANGFUSE_PUBLIC_KEY") or settings.langfuse_public_key,
            secret_key=resolve_env("LANGFUSE_SECRET_KEY") or settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )

    @contextmanager
    def span(
        self,
        name: str,
        *,
        trace_id: str,
        metadata: dict | None = None,
    ) -> Generator[SpanContext, None, None]:
        trace = self._client.trace(id=trace_id, name=name, metadata=metadata or {})
        span = trace.span(name=name, metadata=metadata or {})
        ctx = SpanContext(name=name, trace_id=trace_id, span_id=span.id, metadata=metadata or {}, _recorder=span)
        try:
            yield ctx
        finally:
            span.end()

    def generation(
        self,
        *,
        trace_id: str,
        name: str,
        model: str,
        input_messages: list[dict],
        output: str,
        usage: dict[str, int],
        metadata: dict | None = None,
    ) -> None:
        trace = self._client.trace(id=trace_id)
        trace.generation(
            name=name,
            model=model,
            input=input_messages,
            output=output,
            usage=usage,
            metadata=metadata or {},
        )


@lru_cache
def get_tracer() -> _NoOpRecorder | _LangfuseRecorder:
    settings = get_settings()
    if not tracing_enabled():
        return _NoOpRecorder()
    try:
        return _LangfuseRecorder()
    except Exception as exc:
        logger.warning("Langfuse init failed — tracing disabled: %s", exc)
        return _NoOpRecorder()


def tracing_enabled() -> bool:
    settings = get_settings()
    return bool(
        settings.langfuse_tracing_enabled
        and (
            resolve_env("LANGFUSE_PUBLIC_KEY")
            or settings.langfuse_public_key
        )
        and (
            resolve_env("LANGFUSE_SECRET_KEY")
            or settings.langfuse_secret_key
        )
    )


@contextmanager
def trace_span(name: str, **metadata: Any) -> Generator[SpanContext, None, None]:
    trace_id = get_trace_id() or metadata.pop("trace_id", "")
    with get_tracer().span(name, trace_id=trace_id, metadata=metadata) as ctx:
        yield ctx


def record_llm_generation(
    *,
    role: str,
    model: str,
    messages: list[dict[str, str]],
    output: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    metadata: dict | None = None,
) -> None:
    trace_id = get_trace_id()
    if not trace_id:
        return
    get_tracer().generation(
        trace_id=trace_id,
        name=role,
        model=model,
        input_messages=messages,
        output=output,
        usage={
            "input": prompt_tokens,
            "output": completion_tokens,
            "total": prompt_tokens + completion_tokens,
        },
        metadata=metadata,
    )
