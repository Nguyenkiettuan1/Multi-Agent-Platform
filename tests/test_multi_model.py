"""Tests for 3-layer model resolution."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://agent_reader:agent_reader_local@localhost:5432/phanlaw",
)


@pytest.mark.asyncio
async def test_plan_general_question():
    from workflows.planner import plan_tasks_async

    plan = await plan_tasks_async("What is REST API?")
    assert plan.topology_mode.value == "direct"
    assert len(plan.subtasks) == 1
    assert plan.subtasks[0].assigned_agent.value == "general-agent"


def test_agent_model_from_registry():
    """Lớp 2: agent override — Swarm/CrewAI/Anthropic pattern."""
    from core.llm.resolver import ResolveSource, resolve_model
    from workflows.state import AgentId

    res = resolve_model("general-agent", agent_id=AgentId.GENERAL)
    assert res.source == ResolveSource.AGENT
    assert res.primary.ref == "or-claude-sonnet"  # profile: balanced

    res_db = resolve_model("db-worker", agent_id=AgentId.DB_WORKER)
    assert res_db.primary.ref == "or-deepseek"  # profile: cheap

    res_legal = resolve_model("legal-agent", agent_id=AgentId.LEGAL_WORKER)
    assert res_legal.primary.ref == "or-claude-sonnet"  # direct ref


def test_pipeline_model_from_orchestrator():
    """Lớp 3: pipeline nodes — LangGraph/Anthropic control plane."""
    from core.llm.resolver import ResolveSource, resolve_model

    res = resolve_model("meta-planner")
    assert res.source == ResolveSource.PIPELINE
    assert res.primary.ref == "az-o3"  # profile: reasoning

    res_triage = resolve_model("triage")
    assert res_triage.primary.ref == "or-gpt-4o-mini"  # profile: fast


def test_fallback_chain():
    from core.llm.resolver import resolve_model

    res = resolve_model("meta-planner")
    fallback_refs = [f.ref for f in res.fallbacks]
    assert "or-claude-sonnet" in fallback_refs


def test_model_catalog():
    from core.llm.router import get_router

    router = get_router()
    models = router.list_models()
    assert len(models) >= 5
    assert any(m["ref"] == "or-gpt-4o-mini" for m in models)


@pytest.mark.asyncio
async def test_workflow_without_llm():
    from workflows.runner import run_agent_workflow

    result = await run_agent_workflow("hello")
    assert result["topology_mode"] == "direct"
    assert result["response"]
    assert isinstance(result["model_usage"], list)
