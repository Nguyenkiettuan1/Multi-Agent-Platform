"""Hybrid search — parallel retrievers + RRF fusion."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from core.search.azure_search import azure_search, azure_search_enabled
from core.search.fusion import RankedHitList, reciprocal_rank_fusion
from core.search.pgvector_store import SearchHit, keyword_search, vector_search

logger = logging.getLogger(__name__)


@dataclass
class HybridSearchResult:
    query: str
    hits: list[SearchHit]
    backends_used: list[str]


async def hybrid_search(
    query: str,
    *,
    top_k: int = 5,
    domain: str | None = None,
) -> HybridSearchResult:
    """Run retrievers in parallel, merge with RRF."""
    fetch_k = max(top_k * 2, 10)
    ranked_lists: list[RankedHitList] = []
    backends: list[str] = []

    async def _azure() -> RankedHitList | None:
        try:
            if not azure_search_enabled():
                return None
            hits = await azure_search(query, top_k=fetch_k)
            return RankedHitList("azure_search", hits) if hits else None
        except Exception as exc:
            logger.warning("hybrid azure retriever failed: %s", exc)
            return None

    async def _vector() -> RankedHitList | None:
        try:
            hits = await vector_search(query, top_k=fetch_k, domain=domain)
            return RankedHitList(hits[0].backend if hits else "pgvector", hits) if hits else None
        except Exception as exc:
            logger.warning("hybrid vector retriever failed: %s", exc)
            return None

    async def _keyword() -> RankedHitList | None:
        try:
            hits = await asyncio.to_thread(keyword_search, query, top_k=fetch_k, domain=domain)
            return RankedHitList("pg_fts", hits) if hits else None
        except Exception as exc:
            logger.warning("hybrid keyword retriever failed: %s", exc)
            return None

    results = await asyncio.gather(_azure(), _vector(), _keyword())
    for rl in results:
        if rl is not None:
            ranked_lists.append(rl)
            if rl.backend not in backends:
                backends.append(rl.backend)

    if ranked_lists:
        hits = reciprocal_rank_fusion(ranked_lists, top_k=top_k)
        if hits:
            backends.append("rrf")
            return HybridSearchResult(query=query, hits=hits, backends_used=backends)

    logger.info("hybrid_search: no hits for query=%r", query[:80])
    return HybridSearchResult(query=query, hits=[], backends_used=["none"])


def format_hits_for_llm(result: HybridSearchResult) -> str:
    if not result.hits:
        return "No relevant documents found."
    parts = []
    for i, h in enumerate(result.hits, 1):
        parts.append(
            f"[{i}] {h.title} (source={h.source}, score={h.score:.2f})\n{h.content[:1500]}"
        )
    return "\n\n".join(parts)
