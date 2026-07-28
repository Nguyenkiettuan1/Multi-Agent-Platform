"""Planner — tạo TaskPlan từ triage result."""

from __future__ import annotations

import uuid

from core.control.triage import analyze_triage
from core.registry.agents import format_registry_for_planner, load_registry
from workflows.state import AgentId, IntentType, SubTask, TaskPlan, TopologyMode, TriageResult


def plan_from_triage(user_message: str, triage: TriageResult) -> TaskPlan:
    """Tạo plan tối thiểu dựa trên intent — không over-orchestrate."""
    if triage.blocked:
        return TaskPlan(
            main_task=user_message,
            subtasks=[],
            complexity_score=0.0,
            topology_mode=TopologyMode.DIRECT,
        )

    if triage.intent == IntentType.GREETING:
        return TaskPlan(
            main_task=user_message,
            subtasks=[],
            complexity_score=0.0,
            topology_mode=TopologyMode.DIRECT,
            is_greeting=True,
        )

    intent_to_agent = {
        IntentType.DB_ONLY: AgentId.DB_WORKER,
        IntentType.LEGAL: AgentId.LEGAL_WORKER,
        IntentType.RESEARCH: AgentId.RESEARCH_WORKER,
        IntentType.ACTION: AgentId.ACTION_WORKER,
        IntentType.GENERAL: AgentId.GENERAL,
    }

    subtasks: list[SubTask] = []

    if triage.intent == IntentType.MULTI:
        subtasks = _multi_subtasks(user_message)
    elif triage.intent in intent_to_agent:
        agent = intent_to_agent[triage.intent]
        subtasks = [_subtask(agent.value.split("-")[0], user_message, agent)]
    else:
        subtasks = [_subtask("general", user_message, AgentId.GENERAL)]

    topology = _select_topology(triage.complexity, len(subtasks), triage)

    return TaskPlan(
        main_task=user_message,
        subtasks=subtasks,
        complexity_score=triage.complexity,
        topology_mode=topology,
    )


def plan_tasks(user_message: str) -> TaskPlan:
    triage = analyze_triage(user_message)
    _ = format_registry_for_planner(load_registry())
    return plan_from_triage(user_message, triage)


def _multi_subtasks(user_message: str) -> list[SubTask]:
    from core.control.triage import detect_capabilities

    caps = detect_capabilities(user_message)
    subtasks: list[SubTask] = []

    if caps["db"]:
        subtasks.append(_subtask("db", user_message, AgentId.DB_WORKER))
    if caps["legal"]:
        subtasks.append(_subtask("legal", user_message, AgentId.LEGAL_WORKER))
    elif caps["research"]:
        subtasks.append(_subtask("research", user_message, AgentId.RESEARCH_WORKER))
    if caps["action"]:
        subtasks.append(_subtask("action", user_message, AgentId.ACTION_WORKER))

    if not subtasks:
        subtasks.append(_subtask("general", user_message, AgentId.GENERAL))
    return subtasks


def _subtask(prefix: str, description: str, agent: AgentId) -> SubTask:
    return SubTask(
        id=f"{prefix}-{uuid.uuid4().hex[:8]}",
        description=description,
        assigned_agent=agent,
    )


def _select_topology(
    complexity: float,
    task_count: int,
    triage: TriageResult,
) -> TopologyMode:
    if triage.fast_path and task_count <= 1:
        return TopologyMode.DIRECT
    if complexity >= 0.7:
        return TopologyMode.REVIEWED
    if task_count >= 2:
        return TopologyMode.PLANNED
    return TopologyMode.DIRECT


async def plan_tasks_async(user_message: str, triage: TriageResult | None = None) -> TaskPlan:
    triage = triage or analyze_triage(user_message)

    if triage.fast_path or triage.blocked or not triage.requires_planning:
        return plan_from_triage(user_message, triage)

    from workflows.llm_planner import plan_with_llm

    llm_plan = await plan_with_llm(user_message)
    if llm_plan is not None:
        return llm_plan
    return plan_from_triage(user_message, triage)
