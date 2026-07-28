"""Eval runner — chạy test cases từ eval/cases/*.yaml."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import yaml

from eval.models import EvalCase, EvalCaseResult
from workflows.runner import run_agent_workflow

CASES_DIR = Path(__file__).resolve().parent / "cases"


def _normalize(text: str) -> str:
    lower = text.lower()
    nfkd = unicodedata.normalize("NFKD", lower)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def load_cases(path: Path | None = None) -> list[EvalCase]:
    path = path or CASES_DIR / "basic.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [EvalCase(**item) for item in data.get("cases", [])]


async def run_case(case: EvalCase) -> EvalCaseResult:
    result = await run_agent_workflow(case.input)
    failures: list[str] = []
    expected = case.expected

    triage = result.get("triage") or {}
    triage_intent = triage.get("intent")

    if expected.blocked:
        if not triage.get("blocked"):
            failures.append("expected blocked=true")
    elif triage.get("blocked"):
        failures.append(f"unexpected blocked: {triage.get('block_reason')}")

    if expected.triage_intent and triage_intent != expected.triage_intent:
        failures.append(f"triage intent: got {triage_intent}, want {expected.triage_intent}")

    workers = [w["agent"] for w in result.get("worker_results", [])]
    if expected.workers_called:
        for agent in expected.workers_called:
            if agent not in workers:
                failures.append(f"missing worker: {agent}")

    if expected.tools_called:
        all_tools = []
        for w in result.get("worker_results", []):
            all_tools.extend(w.get("tools_called", []))
        for tool in expected.tools_called:
            if tool not in all_tools:
                failures.append(f"missing tool: {tool}")

    response = _normalize(result.get("response", ""))
    for fragment in expected.response_contains:
        if _normalize(fragment) not in response:
            failures.append(f"response missing: {fragment}")

    eval_data = result.get("eval") or {}
    score = eval_data.get("score")
    if score is not None and score < expected.eval_min_score:
        failures.append(f"eval score {score} < {expected.eval_min_score}")

    return EvalCaseResult(
        id=case.id,
        passed=len(failures) == 0,
        failures=failures,
        trace_id=result.get("trace_id", ""),
        triage_intent=triage_intent,
        workers_called=workers,
        eval_score=score,
    )


async def run_all_cases(path: Path | None = None) -> list[EvalCaseResult]:
    results = []
    for case in load_cases(path):
        results.append(await run_case(case))
    return results
