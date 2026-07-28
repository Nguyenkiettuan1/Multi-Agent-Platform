"""Combined knowledge + web search with citations."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from core.search.citations import (
    CITATION_INSTRUCTION,
    SourceCitation,
    citations_from_knowledge_hits,
    citations_from_web_results,
    format_context_for_llm,
)
from core.search.hybrid import HybridSearchResult, hybrid_search
from core.search.rerank import rerank_citations
from core.search.web_search import web_search, web_search_enabled

logger = logging.getLogger(__name__)


@dataclass
class CombinedSearchResult:
    query: str
    citations: list[SourceCitation] = field(default_factory=list)
    backends_used: list[str] = field(default_factory=list)

    @property
    def context_for_llm(self) -> str:
        return format_context_for_llm(self.citations)

    @property
    def citation_instruction(self) -> str:
        return CITATION_INSTRUCTION


async def combined_search(
    query: str,
    *,
    top_k: int = 5,
    domain: str | None = None,
    include_web: bool = True,
) -> CombinedSearchResult:
    """Knowledge (pgvector / FTS / Azure) then optional web — never raises on retriever failure."""
    backends: list[str] = []
    citations: list[SourceCitation] = []

    try:
        kb = await hybrid_search(query, top_k=top_k, domain=domain)
    except Exception as exc:
        logger.warning("hybrid_search failed (%s) — continuing with web-only if enabled", exc)
        kb = HybridSearchResult(query=query, hits=[], backends_used=["none"])

    if kb.backends_used and kb.backends_used != ["none"]:
        backends.extend(kb.backends_used)
    if kb.hits:
        citations.extend(citations_from_knowledge_hits(kb.hits))

    if include_web and web_search_enabled():
        try:
            web_hits = await web_search(query, top_k=top_k)
            if web_hits:
                backends.append("web_search")
                citations.extend(citations_from_web_results(web_hits))
        except Exception as exc:
            logger.warning("web_search failed (%s)", exc)

    if citations:
        from config import get_settings

        if get_settings().search_rerank_enabled:
            try:
                backends.append("rerank")
                citations = await rerank_citations(query, citations, top_k=top_k)
            except Exception as exc:
                logger.warning("rerank failed (%s) — using unranked citations", exc)

    return CombinedSearchResult(
        query=query,
        citations=citations,
        backends_used=backends or ["none"],
    )
