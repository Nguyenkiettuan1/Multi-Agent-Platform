"""Workers must not report success when the model call failed or no handler exists."""

from types import SimpleNamespace

import pytest

from workflows.state import AgentId, SubTask
from workflows.workers import handlers


def _task(agent: AgentId, description: str = "Giải thích hợp đồng") -> SubTask:
    return SubTask(id="t1", description=description, assigned_agent=agent)


def _patch_llm(monkeypatch, *, enabled: bool, reply: str):
    async def fake_complete(*args, **kwargs):
        return reply

    monkeypatch.setattr(handlers, "complete_worker_task", fake_complete)
    monkeypatch.setattr(handlers, "get_llm_client", lambda: SimpleNamespace(enabled=enabled))
    # Pin the skill so `sources` does not depend on files on disk.
    monkeypatch.setattr(handlers, "load_skill_instructions", lambda name: "skill text")


@pytest.mark.asyncio
@pytest.mark.parametrize("reply", ["", "   ", "\n\t "])
async def test_general_llm_enabled_but_empty_is_failure_without_config_hint(monkeypatch, reply):
    _patch_llm(monkeypatch, enabled=True, reply=reply)
    result = await handlers.run_worker(_task(AgentId.GENERAL))
    assert result.success is False
    assert result.agent == AgentId.GENERAL
    assert "model call failed" in result.summary
    assert "try again" in result.summary
    assert "Configure LLM" not in result.summary
    assert result.sources == []


@pytest.mark.asyncio
async def test_general_llm_not_configured_is_failure_with_config_hint(monkeypatch):
    _patch_llm(monkeypatch, enabled=False, reply="")
    result = await handlers.run_worker(_task(AgentId.GENERAL))
    assert result.success is False
    assert "Configure LLM in .env" in result.summary
    assert result.sources == []


@pytest.mark.asyncio
async def test_general_success_keeps_model_reply(monkeypatch):
    _patch_llm(monkeypatch, enabled=True, reply="Hợp đồng là thỏa thuận ...")
    result = await handlers.run_worker(_task(AgentId.GENERAL))
    assert result.success is True
    assert result.summary == "Hợp đồng là thỏa thuận ..."
    assert result.sources == ["general-assistant"]


@pytest.mark.asyncio
@pytest.mark.parametrize("agent", [AgentId.CODE_WORKER, AgentId.DEFAULT])
async def test_agent_without_handler_is_failure_naming_agent(agent):
    result = await handlers.run_worker(_task(agent))
    assert result.success is False
    assert result.agent == agent
    assert agent.value in result.summary
    assert result.sources == []
