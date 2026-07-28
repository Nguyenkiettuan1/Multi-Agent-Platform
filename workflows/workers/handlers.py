"""Worker handlers — mỗi agent một handler riêng."""

from __future__ import annotations

from core.skills.loader import load_skill_instructions
from workflows.llm_service import complete_worker_task
from workflows.state import AgentId, SubTask, WorkerResult
from workflows.workers.db_worker import run_db_worker
from workflows.workers.legal_worker import run_legal_worker
from workflows.workers.research_worker import run_research_worker


async def run_worker(task: SubTask, *, chat_history: list[dict] | None = None) -> WorkerResult:
    handlers = {
        AgentId.DB_WORKER: run_db_worker,
        AgentId.GENERAL: _run_general_agent,
        AgentId.RESEARCH_WORKER: run_research_worker,
        AgentId.LEGAL_WORKER: run_legal_worker,
        AgentId.ACTION_WORKER: _run_action_worker,
    }
    handler = handlers.get(task.assigned_agent, _run_default_worker)
    if handler in (run_db_worker, run_research_worker, run_legal_worker, _run_general_agent):
        return await handler(task, chat_history=chat_history)
    return await handler(task)


async def _run_general_agent(task: SubTask, *, chat_history: list[dict] | None = None) -> WorkerResult:
    skill = load_skill_instructions("general-assistant")
    summary = await complete_worker_task(
        AgentId.GENERAL,
        task.description,
        skill_name="general-assistant",
        chat_history=chat_history,
    )
    if not summary:
        summary = (
            f"[General Agent] {task.description[:300]}\n"
            "(Cấu hình LLM trong .env: OPENROUTER_API_KEY, OPENAI_API_KEY, hoặc AZURE_OPENAI_API_KEY + AZURE_OPENAI_ENDPOINT)"
        )
    return WorkerResult(
        task_id=task.id,
        agent=AgentId.GENERAL,
        summary=summary,
        success=True,
        sources=["general-assistant"] if skill else [],
    )


async def _run_action_worker(task: SubTask) -> WorkerResult:
    return WorkerResult(
        task_id=task.id,
        agent=AgentId.ACTION_WORKER,
        summary=f"[Action] Cần HITL approval. Task: {task.description[:200]}",
        success=True,
        tools_called=["api-mcp-stub"],
    )


async def _run_default_worker(task: SubTask) -> WorkerResult:
    return WorkerResult(
        task_id=task.id,
        agent=AgentId.DEFAULT,
        summary=f"Fallback: {task.description[:200]}",
        success=True,
    )
