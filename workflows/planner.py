"""Planner — tạo TaskPlan từ triage result."""

from __future__ import annotations

import logging
import uuid

from core.control.triage import analyze_triage
from core.planning.media_tasks import plan_media_action, plan_media_action_async, should_attempt_media_plan
from core.registry.agents import format_registry_for_planner, load_registry
from workflows.state import AgentId, IntentType, SubTask, TaskPlan, TopologyMode, TriageResult

logger = logging.getLogger(__name__)


async def plan_from_triage(
    user_message: str,
    triage: TriageResult,
    *,
    attachments: list[dict] | None = None,
    chat_history: list[dict] | None = None,
) -> TaskPlan:
    """Tạo plan — media task bind tool tại đây (LLM classify)."""
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

    media_plan = await _plan_media_subtask(
        user_message,
        attachments,
        chat_history=chat_history,
    )
    if media_plan is not None:
        topology = TopologyMode.DIRECT if triage.fast_path else _select_topology(
            triage.complexity, 1, triage
        )
        return TaskPlan(
            main_task=user_message,
            subtasks=[media_plan],
            complexity_score=triage.complexity,
            topology_mode=topology,
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
        subtasks = await _multi_subtasks(user_message, attachments=attachments, chat_history=chat_history)
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


async def _plan_media_subtask(
    user_message: str,
    attachments: list[dict] | None,
    *,
    chat_history: list[dict] | None = None,
) -> SubTask | None:
    """Plan stage: LLM phân loại OCR/translate/merge + bind tool args."""
    if not should_attempt_media_plan(user_message, attachments):
        return None

    agent = load_registry().get(AgentId.ACTION_WORKER)
    allowed = set(agent.tools) if agent and agent.tools else {
        "builtin-translate",
        "builtin-ocr",
        "builtin-image",
        "paddleocr",
    }

    from core.mcp.hub import get_tool_hub

    hub = get_tool_hub()
    available_ids = {t.id for t in hub.list_tools(server_filter=allowed)}

    media = await plan_media_action_async(
        user_message,
        attachments,
        available_tool_ids=available_ids,
        chat_history=chat_history,
    )
    if not media:
        return None

    logger.info(
        "Plan media task kind=%s tool=%s source=%s has_file=%s",
        media.task_kind,
        media.tool_id,
        media.classify_source,
        bool(media.tool_arguments.get("file_path")),
    )

    return SubTask(
        id=f"{media.task_kind}-{uuid.uuid4().hex[:8]}",
        description=user_message,
        assigned_agent=AgentId.ACTION_WORKER,
        task_kind=media.task_kind,
        tool_id=media.tool_id,
        tool_arguments=media.tool_arguments,
        high_accuracy=media.high_accuracy,
    )


def plan_tasks_sync(user_message: str, *, attachments: list[dict] | None = None) -> TaskPlan:
    """Sync plan — structural media fallback only (tests)."""
    triage = analyze_triage(user_message, attachments=attachments)
    _ = format_registry_for_planner(load_registry())
    return _plan_from_triage_sync(user_message, triage, attachments=attachments)


def _plan_from_triage_sync(
    user_message: str,
    triage: TriageResult,
    *,
    attachments: list[dict] | None = None,
) -> TaskPlan:
    if triage.blocked or triage.intent == IntentType.GREETING:
        return TaskPlan(
            main_task=user_message,
            subtasks=[],
            complexity_score=0.0,
            topology_mode=TopologyMode.DIRECT,
            is_greeting=triage.intent == IntentType.GREETING,
        )

    media = plan_media_action(user_message, attachments)
    if media:
        return TaskPlan(
            main_task=user_message,
            subtasks=[
                SubTask(
                    id=f"{media.task_kind}-{uuid.uuid4().hex[:8]}",
                    description=user_message,
                    assigned_agent=AgentId.ACTION_WORKER,
                    task_kind=media.task_kind,
                    tool_id=media.tool_id,
                    tool_arguments=media.tool_arguments,
                    high_accuracy=media.high_accuracy,
                )
            ],
            complexity_score=triage.complexity,
            topology_mode=TopologyMode.DIRECT,
        )

    intent_to_agent = {
        IntentType.DB_ONLY: AgentId.DB_WORKER,
        IntentType.ACTION: AgentId.ACTION_WORKER,
        IntentType.GENERAL: AgentId.GENERAL,
    }
    agent = intent_to_agent.get(triage.intent, AgentId.GENERAL)
    return TaskPlan(
        main_task=user_message,
        subtasks=[_subtask("task", user_message, agent)],
        complexity_score=triage.complexity,
        topology_mode=TopologyMode.DIRECT,
    )


async def _multi_subtasks(
    user_message: str,
    *,
    attachments: list[dict] | None = None,
    chat_history: list[dict] | None = None,
) -> list[SubTask]:
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
        media = await _plan_media_subtask(user_message, attachments, chat_history=chat_history)
        if media:
            subtasks.append(media)
        else:
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


async def plan_tasks_async(
    user_message: str,
    triage: TriageResult | None = None,
    *,
    attachments: list[dict] | None = None,
    chat_history: list[dict] | None = None,
) -> TaskPlan:
    triage = triage or analyze_triage(user_message, attachments=attachments)

    if triage.fast_path or triage.blocked or not triage.requires_planning:
        return await plan_from_triage(
            user_message,
            triage,
            attachments=attachments,
            chat_history=chat_history,
        )

    from workflows.llm_planner import plan_with_llm

    llm_plan = await plan_with_llm(user_message)
    if llm_plan is not None:
        return llm_plan
    return await plan_from_triage(
        user_message,
        triage,
        attachments=attachments,
        chat_history=chat_history,
    )
