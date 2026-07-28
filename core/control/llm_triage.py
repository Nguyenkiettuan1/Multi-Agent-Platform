"""LLM-based triage — routing có ngữ cảnh hội thoại."""

from __future__ import annotations

import logging

from core.control.triage import build_triage_result
from core.llm.client import get_llm_client
from core.registry.agents import format_registry_for_planner, load_registry
from workflows.prompts import TRIAGE_SYSTEM
from workflows.state import IntentType, TriageResult

logger = logging.getLogger(__name__)

_VALID_INTENTS = {i.value for i in IntentType if i != IntentType.BLOCKED}


async def triage_with_llm(
    user_message: str,
    *,
    chat_history: list[dict] | None = None,
) -> TriageResult | None:
    client = get_llm_client()
    if not client.enabled:
        return None

    registry = format_registry_for_planner(load_registry())
    history_block = _format_history(chat_history)

    messages = [
        {"role": "system", "content": TRIAGE_SYSTEM},
        {
            "role": "user",
            "content": (
                f"## Agent fleet\n{registry}\n\n"
                f"{history_block}"
                f"## Current user message\n{user_message}\n\n"
                "Phân loại intent JSON."
            ),
        },
    ]

    data = await client.chat_json("triage", messages)
    if not data:
        return None

    try:
        intent_raw = str(data.get("intent", "general")).lower().strip()
        if intent_raw not in _VALID_INTENTS:
            intent_raw = "general"
        intent = IntentType(intent_raw)
        complexity = float(data.get("complexity", 0.2))
        complexity = max(0.0, min(1.0, complexity))
        requires_planning = bool(data.get("requires_planning", intent == IntentType.MULTI))
        return build_triage_result(
            intent,
            complexity=complexity,
            requires_planning=requires_planning,
        )
    except Exception as exc:
        logger.warning("Failed to parse LLM triage: %s", exc)
        return None


def _format_history(chat_history: list[dict] | None) -> str:
    if not chat_history:
        return ""
    lines: list[str] = ["## Recent conversation"]
    for msg in chat_history[-8:]:
        role = msg.get("role", "user")
        content = str(msg.get("content", ""))[:1500]
        if content:
            lines.append(f"- {role}: {content}")
    lines.append("")
    return "\n".join(lines) + "\n"
