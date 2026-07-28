"""Tests for control plane — triage, guardrails, eval, fast path."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://agent_reader:agent_reader_local@localhost:5432/phanlaw",
)


def test_triage_db_only_fast_path():
    from core.control.triage import analyze_triage
    from workflows.state import IntentType

    t = analyze_triage("Co bao nhieu hop dong dang active?")
    assert t.intent == IntentType.DB_ONLY
    assert t.fast_path is True
    assert t.skip_synthesize is True
    assert t.skip_review is True


def test_triage_blocks_destructive_sql():
    from core.control.triage import analyze_triage
    from workflows.state import IntentType

    t = analyze_triage("DELETE FROM contracts WHERE id=1")
    assert t.intent == IntentType.BLOCKED
    assert t.blocked is True


def test_triage_multi_intent():
    from core.control.triage import analyze_triage
    from workflows.state import IntentType

    t = analyze_triage("Tim hop dong ABC va phan tich dieu khoan thanh toan theo luat va bao nhieu hop dong")
    assert t.intent == IntentType.MULTI
    assert t.fast_path is False


def test_triage_capability_question_not_research():
    from core.control.triage import analyze_triage
    from workflows.state import IntentType

    t = analyze_triage("ban co the search web khong?")
    assert t.intent == IntentType.GENERAL
    assert t.fast_path is True


def test_triage_followup_research_after_company_search():
    from unittest.mock import AsyncMock, patch

    from core.control.triage import analyze_triage_async
    from workflows.state import IntentType

    history = [
        {"role": "user", "content": "tim kiem toan bo thong tin cua phanlaw viet nam"},
        {"role": "assistant", "content": "Phan Law Vietnam duoc thanh lap nam 2010..."},
    ]

    async def _run():
        with patch(
            "core.control.llm_triage.triage_with_llm",
            new_callable=AsyncMock,
        ) as mock_llm:
            from core.control.triage import build_triage_result

            mock_llm.return_value = build_triage_result(IntentType.RESEARCH, complexity=0.35)
            return await analyze_triage_async(
                "CEO cua cong ty tren la ai? cac thanh tuu noi bat",
                chat_history=history,
            )

    import asyncio

    t = asyncio.run(_run())
    assert t.intent == IntentType.RESEARCH


def test_should_use_llm_when_chat_history_exists():
    from core.control.triage import analyze_triage_rules, should_use_llm_triage

    rule = analyze_triage_rules("CEO la ai?")
    assert should_use_llm_triage("CEO la ai?", [{"role": "user", "content": "phanlaw"}], rule)


def test_redact_email():
    from core.control.guardrails import redact_output

    text, types = redact_output("Lien he: user@example.com")
    assert "[EMAIL_REDACTED]" in text
    assert "email" in types


def test_eval_passes_simple_response():
    from core.control.evaluator import evaluate_response
    from workflows.state import IntentType, TriageResult, WorkerResult, AgentId

    triage = TriageResult(intent=IntentType.GENERAL, complexity=0.1)
    workers = [WorkerResult(task_id="t1", agent=AgentId.GENERAL, summary="ok", success=True)]
    ev = evaluate_response(
        user_message="What is REST?",
        response="REST is an API style.",
        triage=triage,
        worker_results=workers,
    )
    assert ev.passed is True
    assert ev.score >= 0.6


@pytest.mark.asyncio
async def test_db_only_plan_single_worker():
    from core.control.triage import analyze_triage
    from workflows.planner import plan_from_triage
    from workflows.state import AgentId, IntentType

    msg = "Co bao nhieu hop dong trong he thong?"
    triage = analyze_triage(msg)
    plan = plan_from_triage(msg, triage)

    assert triage.intent == IntentType.DB_ONLY
    assert triage.fast_path is True
    assert len(plan.subtasks) == 1
    assert plan.subtasks[0].assigned_agent == AgentId.DB_WORKER
