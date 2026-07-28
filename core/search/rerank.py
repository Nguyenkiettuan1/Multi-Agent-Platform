"""Rerank search citations by semantic similarity to query."""

from __future__ import annotations

import logging
import math

from core.search.citations import SourceCitation
from core.search.embeddings import embed_query, embed_text

logger = logging.getLogger(__name__)


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


async def rerank_citations(
    query: str,
    citations: list[SourceCitation],
    *,
    top_k: int = 5,
) -> list[SourceCitation]:
    """Re-order citations — blend original score + embedding similarity."""
    if len(citations) <= 1:
        return citations

    query_vec = await embed_query(query)
    if query_vec is None:
        return citations[:top_k]

    scored: list[tuple[float, SourceCitation]] = []
    for c in citations:
        text = f"{c.title}\n{c.excerpt}"
        doc_vec = await embed_text(text)
        sim = _cosine(query_vec, doc_vec) if doc_vec else 0.0
        base = c.score or 0.5
        combined = 0.6 * sim + 0.4 * min(base, 1.0)
        scored.append((combined, c))

    scored.sort(key=lambda x: x[0], reverse=True)
    reranked = []
    for rank, (score, c) in enumerate(scored[:top_k], 1):
        c.score = round(score, 4)
        reranked.append(c)

    logger.info("Reranked %d → top %d citations for query", len(citations), len(reranked))
    return reranked
