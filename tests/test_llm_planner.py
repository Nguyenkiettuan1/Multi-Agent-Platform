"""LLM planner: chat history reaches the model; only enabled agents are assignable."""

from __future__ import annotations

import asyncio

from workflows import llm_planner
from workflows.state import AgentId


class _FakeClient:
    enabled = True

    def __init__(self, response: dict | None = None):
        self.response = response or {"subtasks": [], "topology_mode": "planned"}
        self.calls: list[tuple[str, list[dict]]] = []

    async def chat_json(self, role: str, messages: list[dict]):
        self.calls.append((role, messages))
        return self.response


def _run_plan(client: _FakeClient, monkeypatch, message: str, **kwargs):
    monkeypatch.setattr(llm_planner, "get_llm_client", lambda: client)
    return asyncio.run(llm_planner.plan_with_llm(message, **kwargs))


def _all_text(messages: list[dict]) -> str:
    return "\n".join(m["content"] for m in messages)


def test_chat_history_is_sent_to_planner_llm(monkeypatch):
    client = _FakeClient()
    history = [
        {"role": "user", "content": "Tell me about Vinamilk"},
        {"role": "assistant", "content": "Vinamilk is a dairy company."},
    ]
    _run_plan(client, monkeypatch, "còn công ty đó thì sao", chat_history=history)

    text = _all_text(client.calls[0][1])
    assert "Tell me about Vinamilk" in text
    assert "Vinamilk is a dairy company." in text
    assert "còn công ty đó thì sao" in text


def test_history_is_trimmed_to_recent_turns_and_truncated(monkeypatch):
    client = _FakeClient()
    history = [{"role": "user", "content": f"old-turn-{i}"} for i in range(30)]
    history.append({"role": "assistant", "content": "x" * 5000})
    _run_plan(client, monkeypatch, "next", chat_history=history)

    text = _all_text(client.calls[0][1])
    assert "old-turn-0" not in text
    assert "old-turn-29" in text
    assert "x" * 1500 in text
    assert "x" * 1501 not in text


def test_no_history_section_without_history(monkeypatch):
    client = _FakeClient()
    _run_plan(client, monkeypatch, "hello there")

    assert "Recent conversation" not in _all_text(client.calls[0][1])


def test_valid_agents_exclude_disabled_and_default():
    valid = llm_planner._valid_agent_ids()

    assert "code-worker" not in valid
    assert "default-agent" not in valid
    assert {"general-agent", "db-worker", "research-worker", "legal-agent", "action-worker"} <= valid


def test_prompt_lists_only_enabled_agents(monkeypatch):
    client = _FakeClient()
    _run_plan(client, monkeypatch, "hello there")

    system = client.calls[0][1][0]["content"]
    assert "code-worker" not in system
    assert "assigned_agent must be one of:" in system
    assert "db-worker" in system


def test_disabled_agent_proposed_by_llm_falls_back_to_general():
    plan = llm_planner._parse_plan(
        {
            "subtasks": [
                {"id": "a", "description": "write code", "assigned_agent": "code-worker"},
                {"id": "b", "description": "count", "assigned_agent": "db-worker"},
                {"id": "c", "description": "?", "assigned_agent": "no-such-agent"},
            ]
        },
        "fallback",
    )

    assert [s.assigned_agent for s in plan.subtasks] == [
        AgentId.GENERAL,
        AgentId.DB_WORKER,
        AgentId.GENERAL,
    ]


def test_planner_passes_chat_history_to_plan_with_llm(monkeypatch):
    from workflows import planner
    from workflows.state import IntentType, TriageResult

    captured: dict = {}

    async def fake_plan_with_llm(message, chat_history=None):
        captured["history"] = chat_history
        return None

    async def fake_from_triage(*args, **kwargs):
        return "fallback-plan"

    monkeypatch.setattr(llm_planner, "plan_with_llm", fake_plan_with_llm)
    monkeypatch.setattr(planner, "plan_from_triage", fake_from_triage)

    triage = TriageResult(intent=IntentType.MULTI, requires_planning=True)
    history = [{"role": "user", "content": "earlier"}]
    result = asyncio.run(planner.plan_tasks_async("follow up", triage, chat_history=history))

    assert result == "fallback-plan"
    assert captured["history"] == history
