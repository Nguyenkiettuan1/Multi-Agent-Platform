"""Legal domain worker — RAG + web search with citations."""

from __future__ import annotations

import logging

from core.mcp.search_tools import search_documents
from core.search.citations import CITATION_INSTRUCTION
from core.skills.loader import load_skill_instructions
from workflows.llm_service import complete_worker_task
from workflows.state import AgentId, SubTask, WorkerResult

logger = logging.getLogger(__name__)


async def run_legal_worker(task: SubTask, *, chat_history: list[dict] | None = None) -> WorkerResult:
    skill = load_skill_instructions("legal-research")
    tools_called = ["search_documents"]

    try:
        result = await search_documents(task.description, top_k=5, domain="legal", include_web=True)
        tools_called.extend(result.backends_used)

        context = result.context_for_llm
        summary = await complete_worker_task(
            AgentId.LEGAL_WORKER,
            task.description,
            skill_name="legal-research",
            extra_context=(
                f"{CITATION_INSTRUCTION}\n\n"
                f"Legal documents ({', '.join(result.backends_used)}):\n{context}"
            ),
            chat_history=chat_history,
        )
        if not summary:
            summary = context or f"[Legal] {task.description[:200]}"

        sources = [c.doc_id or c.url or c.ref_id for c in result.citations]
        return WorkerResult(
            task_id=task.id,
            agent=AgentId.LEGAL_WORKER,
            summary=summary,
            success=True,
            sources=sources,
            citations=[c.to_dict() for c in result.citations],
            tools_called=tools_called,
        )
    except Exception as exc:
        logger.exception("legal-worker failed")
        return WorkerResult(
            task_id=task.id,
            agent=AgentId.LEGAL_WORKER,
            summary=f"Legal error: {exc}",
            success=False,
            tools_called=tools_called,
        )
