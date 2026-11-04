"""LLM-based planner — T2 reasoning model, structured JSON output."""

from __future__ import annotations

import logging
import uuid

from core.llm.client import get_llm_client
from core.llm.context import get_usage_tracker
from core.registry.agents import format_registry_for_planner, load_registry
from workflows.prompts import PLANNER_SYSTEM
from workflows.state import AgentId, SubTask, TaskPlan, TopologyMode

logger = logging.getLogger(__name__)

_VALID_AGENTS = {a.value for a in AgentId if a != AgentId.DEFAULT}
_VALID_TOPOLOGY = {m.value for m in TopologyMode}


async def plan_with_llm(user_message: str) -> TaskPlan | None:
    client = get_llm_client()
    if not client.enabled:
        return None

    registry = load_registry()
    registry_text = format_registry_for_planner(registry)

    messages = [
        {"role": "system", "content": PLANNER_SYSTEM},
        {
            "role": "user",
            "content": (
                f"## Agent fleet\n{registry_text}\n\n"
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
    for i, st in enumerate(data.get("subtasks", [])):
        agent_raw = st.get("assigned_agent", "general-agent")
        if agent_raw not in _VALID_AGENTS:
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
