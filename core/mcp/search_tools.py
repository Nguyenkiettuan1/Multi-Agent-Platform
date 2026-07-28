"""Shared search tools — used by MCP server and research-worker."""

from __future__ import annotations

from core.search.combined_search import CombinedSearchResult, combined_search
from core.search.hybrid import HybridSearchResult, format_hits_for_llm, hybrid_search


async def search_documents(
    query: str,
    *,
    top_k: int = 5,
    domain: str | None = None,
    include_web: bool = True,
) -> CombinedSearchResult:
    return await combined_search(query, top_k=top_k, domain=domain, include_web=include_web)


async def search_documents_knowledge_only(
    query: str,
    *,
    top_k: int = 5,
    domain: str | None = None,
) -> HybridSearchResult:
    return await hybrid_search(query, top_k=top_k, domain=domain)


async def search_documents_text(
    query: str,
    *,
    top_k: int = 5,
    domain: str | None = None,
    include_web: bool = True,
) -> str:
    result = await search_documents(query, top_k=top_k, domain=domain, include_web=include_web)
    return result.context_for_llm
