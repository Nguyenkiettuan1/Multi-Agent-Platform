"""LLM-based planner — T2 reasoning model, structured JSON output."""

from __future__ import annotations

import logging
import uuid

from core.llm.client import get_llm_client
from core.llm.context import get_usage_tracker
from core.registry.agents import format_registry_for_planner, load_registry
from workflows.prompts import render_planner_system
from workflows.state import AgentId, SubTask, TaskPlan, TopologyMode

logger = logging.getLogger(__name__)

_VALID_TOPOLOGY = {m.value for m in TopologyMode}


def _enabled_agent_ids() -> list[str]:
    # load_registry() already drops agents marked `enabled: false`.
    return [a.value for a in load_registry() if a != AgentId.DEFAULT]


def _valid_agent_ids() -> set[str]:
    return set(_enabled_agent_ids())


def _format_history(chat_history: list[dict] | None) -> str:
    if not chat_history:
        return ""
    lines: list[str] = ["## Recent conversation"]
    for msg in chat_history[-8:]:
        role = msg.get("role", "user")
        content = str(msg.get("content", ""))[:1500]
        if content:
            lines.append(f"- {role}: {content}")
    if len(lines) == 1:
        return ""
    return "\n".join(lines) + "\n\n"


async def plan_with_llm(
    user_message: str,
    chat_history: list[dict] | None = None,
) -> TaskPlan | None:
    client = get_llm_client()
    if not client.enabled:
        return None

    registry = load_registry()
    registry_text = format_registry_for_planner(registry)

    messages = [
        {"role": "system", "content": render_planner_system(_enabled_agent_ids())},
        {
            "role": "user",
            "content": (
                f"## Agent fleet\n{registry_text}\n\n"
                f"{_format_history(chat_history)}"
                f"## User request\n{user_message}\n\n"
                "Produce TaskPlan JSON."
            ),
        },
    ]

    data = await client.chat_json("meta-planner", messages)
    resp_meta = get_usage_tracker().calls[-1] if get_usage_tracker().calls else {}
    _ = resp_meta  # usage already recorded in client

    if not data:
        return None

    try:
        return _parse_plan(data, user_message)
    except Exception as exc:
        logger.warning("Failed to parse LLM plan: %s", exc)
        return None


def _parse_plan(data: dict, fallback_task: str) -> TaskPlan:
    subtasks: list[SubTask] = []
    valid_agents = _valid_agent_ids()
    for i, st in enumerate(data.get("subtasks", [])):
        agent_raw = st.get("assigned_agent", "general-agent")
        if agent_raw not in valid_agents:
            agent_raw = "general-agent"
        subtasks.append(
            SubTask(
                id=st.get("id") or f"task-{uuid.uuid4().hex[:8]}",
                description=st.get("description", fallback_task),
                assigned_agent=AgentId(agent_raw),
            )
        )

    topology_raw = data.get("topology_mode", "planned")
    if topology_raw not in _VALID_TOPOLOGY:
        topology_raw = "planned"

    return TaskPlan(
        main_task=data.get("main_task", fallback_task),
        subtasks=subtasks,
        complexity_score=float(data.get("complexity_score", 0.3)),
        topology_mode=TopologyMode(topology_raw),
        is_greeting=bool(data.get("is_greeting", False)),
    )
