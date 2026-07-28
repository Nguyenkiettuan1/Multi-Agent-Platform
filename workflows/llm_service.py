"""LLM helpers — review, synthesize, worker completion."""

from __future__ import annotations

from core.llm.client import get_llm_client
from core.skills.loader import load_skill_instructions
from workflows.prompts import (
    GENERAL_SYSTEM,
    LEGAL_SYSTEM,
    RESEARCH_SYSTEM,
    REVIEWER_SYSTEM,
    SYNTHESIZER_SYSTEM,
)
from workflows.state import AgentId, WorkerResult


def _skill_context(skill_name: str | None) -> str:
    if not skill_name:
        return ""
    instructions = load_skill_instructions(skill_name)
    if not instructions:
        return ""
    return f"\n\n## Skill instructions\n{instructions[:4000]}"


def _history_messages(chat_history: list[dict] | None, *, max_turns: int = 8) -> list[dict[str, str]]:
    if not chat_history:
        return []
    trimmed = chat_history[-(max_turns * 2) :]
    return [
        {"role": m["role"], "content": m["content"][:2000]}
        for m in trimmed
        if m.get("role") in ("user", "assistant") and m.get("content")
    ]


async def complete_worker_task(
    agent: AgentId,
    task_description: str,
    *,
    skill_name: str | None = None,
    extra_context: str = "",
    chat_history: list[dict] | None = None,
) -> str:
    """Worker LLM call — model resolved from agents/registry.yaml."""
    client = get_llm_client()
    if not client.enabled:
        return ""

    system_map = {
        AgentId.GENERAL: GENERAL_SYSTEM,
        AgentId.LEGAL_WORKER: LEGAL_SYSTEM,
        AgentId.RESEARCH_WORKER: RESEARCH_SYSTEM,
        AgentId.DB_WORKER: GENERAL_SYSTEM,
    }
    system = system_map.get(agent, GENERAL_SYSTEM) + _skill_context(skill_name)

    messages = [
        {"role": "system", "content": system},
        *_history_messages(chat_history),
        {"role": "user", "content": f"{task_description}\n{extra_context}".strip()},
    ]

    resp = await client.chat(agent.value, messages, agent_id=agent)
    return resp.content


async def review_with_llm(
    user_message: str,
    worker_results: list[WorkerResult],
    *,
    chat_history: list[dict] | None = None,
) -> tuple[str, str]:
    """Pipeline node — model from orchestrator/agent.yaml."""
    client = get_llm_client()
    if not client.enabled:
        failed = [r for r in worker_results if not r.success]
        if failed:
            return "fail", f"{len(failed)} worker(s) failed"
        return "pass", "All workers succeeded (rule-based)"

    summaries = "\n".join(
        f"- [{r.agent.value}] success={r.success}: {r.summary[:500]}" for r in worker_results
    )
    messages = [
        {"role": "system", "content": REVIEWER_SYSTEM},
        *_history_messages(chat_history, max_turns=4),
        {
            "role": "user",
            "content": f"Yêu cầu: {user_message}\n\nKết quả workers:\n{summaries}",
        },
    ]

    data = await client.chat_json("reviewer", messages)
    if data and data.get("status") in ("pass", "fail"):
        return data["status"], data.get("notes", "")

    failed = [r for r in worker_results if not r.success]
    if failed:
        return "fail", f"{len(failed)} worker(s) failed"
    return "pass", "Review passed"


async def synthesize_with_llm(
    user_message: str,
    worker_results: list[WorkerResult],
    *,
    review_status: str = "pass",
    chat_history: list[dict] | None = None,
) -> str:
    """Pipeline node — model from orchestrator/agent.yaml."""
    client = get_llm_client()
    if not client.enabled:
        return ""

    if len(worker_results) == 1:
        return worker_results[0].summary

    summaries = "\n\n".join(f"### {r.agent.value}\n{r.summary}" for r in worker_results)
    messages = [
        {"role": "system", "content": SYNTHESIZER_SYSTEM},
        *_history_messages(chat_history, max_turns=6),
        {
            "role": "user",
            "content": (
                f"Yêu cầu gốc: {user_message}\n"
                f"Review: {review_status}\n\n"
                f"Kết quả từng agent:\n{summaries}\n\n"
                "Viết câu trả lời cuối cho user."
            ),
        },
    ]

    resp = await client.chat("synthesizer", messages)
    return resp.content
