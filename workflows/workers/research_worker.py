"""Research worker — hybrid RAG + optional web search with citations."""

from __future__ import annotations

import logging

from core.mcp.search_tools import search_documents
from core.search.citations import CITATION_INSTRUCTION, strip_references_block
from core.skills.loader import load_skill_instructions
from workflows.llm_service import complete_worker_task
from workflows.state import AgentId, SubTask, WorkerResult

logger = logging.getLogger(__name__)


def _enrich_query_with_history(description: str, chat_history: list[dict] | None) -> str:
    """Short follow-ups inherit prior user question as search anchor."""
    if not chat_history:
        return description

    text = description.strip()
    if len(text) > 150:
        return description

    prior_users = [m["content"] for m in chat_history if m.get("role") == "user" and m.get("content")]
    if not prior_users:
        return description

    anchor = prior_users[-1].strip()
    if anchor == text:
        return description

    return f"{anchor} — {text}"


def _structured_fallback(citations) -> str:
    """Short bullet summary when LLM is unavailable — never dump raw search blocks."""
    bullets: list[str] = []
    for c in citations:
        excerpt = (c.excerpt or "").strip().replace("\n", " ")
        if len(excerpt) > 280:
            excerpt = excerpt[:277] + "…"
        if excerpt:
            bullets.append(f"- {excerpt} [{c.ref_id}]")
    if not bullets:
        return "No detailed content found in the sources."
    return "Summary from retrieved sources:\n" + "\n".join(bullets)


async def _synthesize_answer(
    task: SubTask,
    context: str,
    *,
    chat_history: list[dict] | None,
) -> str | None:
    """Retry synthesis with general agent if research model returns empty."""
    prompt = (
        f"{CITATION_INSTRUCTION}\n\n"
        f"Retrieved documents:\n{context}"
    )
    for agent in (AgentId.RESEARCH_WORKER, AgentId.GENERAL):
        summary = await complete_worker_task(
            agent,
            task.description,
            skill_name="document-research" if agent == AgentId.RESEARCH_WORKER else None,
            extra_context=prompt,
            chat_history=chat_history,
        )
        if summary and summary.strip():
            return strip_references_block(summary.strip())
    return None


async def run_research_worker(task: SubTask, *, chat_history: list[dict] | None = None) -> WorkerResult:
    skill = load_skill_instructions("document-research")
    tools_called = ["search_documents"]

    try:
        query = _enrich_query_with_history(task.description, chat_history)
        result = await search_documents(query, top_k=5, include_web=True)
        tools_called.extend(result.backends_used)

        context = result.context_for_llm
        if not result.citations and "none" in result.backends_used:
            context = (
                f"{context}\n\n"
                "(No internal documents or Azure Search results. "
                "If TAVILY_API_KEY is configured, web search was attempted. "
                "Answer based on retrieved sources or general knowledge, and state limitations clearly.)"
            )

        summary = await _synthesize_answer(
            task,
            context,
            chat_history=chat_history,
        )

        if not summary:
            if result.citations:
                summary = _structured_fallback(result.citations)
            else:
                summary = (
                    "No internal or web documents found for this question. "
                    "Try rephrasing or check TAVILY_API_KEY / knowledge base."
                )
        else:
            summary = strip_references_block(summary)

        sources = [c.doc_id or c.url or c.ref_id for c in result.citations]
        return WorkerResult(
            task_id=task.id,
            agent=AgentId.RESEARCH_WORKER,
            summary=summary,
            success=True,
            sources=sources,
            citations=[c.to_dict() for c in result.citations],
            tools_called=tools_called,
        )
    except Exception as exc:
        logger.exception("research-worker failed")
        return WorkerResult(
            task_id=task.id,
            agent=AgentId.RESEARCH_WORKER,
            summary=(
                "Search could not be completed. "
                "Check DB/pgvector connection (run `python scripts/db_migrate.py`) "
                "and TAVILY_API_KEY for web search."
            ),
            success=False,
            tools_called=tools_called,
        )
