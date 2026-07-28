"""Eval case models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class EvalExpected(BaseModel):
    tools_called: list[str] = Field(default_factory=list)
    workers_called: list[str] = Field(default_factory=list)
    triage_intent: str | None = None
    blocked: bool = False
    response_contains: list[str] = Field(default_factory=list)
    eval_min_score: float = 0.6


class EvalCase(BaseModel):
    id: str
    description: str
    input: str
    expected: EvalExpected


class EvalCaseResult(BaseModel):
    id: str
    passed: bool
    failures: list[str] = Field(default_factory=list)
    trace_id: str = ""
    triage_intent: str | None = None
    workers_called: list[str] = Field(default_factory=list)
    eval_score: float | None = None
