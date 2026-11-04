"""Worker handlers — one handler per agent."""

from __future__ import annotations

from core.llm.client import get_llm_client
from core.skills.loader import load_skill_instructions
from workflows.llm_service import complete_worker_task
from workflows.state import AgentId, SubTask, WorkerResult
from workflows.workers.action_worker import run_action_worker
from workflows.workers.db_worker import run_db_worker
from workflows.workers.legal_worker import run_legal_worker
from workflows.workers.research_worker import run_research_worker


async def run_worker(
    task: SubTask,
    *,
    chat_history: list[dict] | None = None,
    attachments: list[dict] | None = None,
) -> WorkerResult:
    handlers = {
        AgentId.DB_WORKER: run_db_worker,
        AgentId.GENERAL: _run_general_agent,
        AgentId.RESEARCH_WORKER: run_research_worker,
        AgentId.LEGAL_WORKER: run_legal_worker,
        AgentId.ACTION_WORKER: run_action_worker,
    }
    handler = handlers.get(task.assigned_agent, _run_default_worker)
    if handler in (run_db_worker, run_research_worker, run_legal_worker, _run_general_agent, run_action_worker):
        if handler is run_action_worker:
            return await handler(task, chat_history=chat_history, attachments=attachments)
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
    success = bool(summary and summary.strip())
    if not success:
        # complete_worker_task returns "" both when the LLM is off and when the call failed;
        # the client flag tells them apart so we never blame config for a runtime failure.
        if get_llm_client().enabled:
            summary = "The model call failed or returned nothing. Please try again."
        else:
            summary = (
                f"[General Agent] {task.description[:300]}\n"
                "(Configure LLM in .env: OPENROUTER_API_KEY, OPENAI_API_KEY, or AZURE_OPENAI_API_KEY + AZURE_OPENAI_ENDPOINT)"
            )
    return WorkerResult(
        task_id=task.id,
        agent=AgentId.GENERAL,
        summary=summary,
        success=success,
        sources=["general-assistant"] if skill and success else [],
    )


async def _run_default_worker(task: SubTask) -> WorkerResult:
    # No handler registered (e.g. code-worker is disabled): fail loudly instead of faking success.
    return WorkerResult(
        task_id=task.id,
        agent=task.assigned_agent,
        summary=f"No worker handler available for agent '{task.assigned_agent.value}'; task was not executed.",
        success=False,
    )
