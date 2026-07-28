"""Reciprocal Rank Fusion — merge ranked lists from multiple retrievers."""

from __future__ import annotations

from dataclasses import dataclass

from core.search.pgvector_store import SearchHit

DEFAULT_RRF_K = 60


@dataclass(frozen=True)
class RankedHitList:
    """One retriever's ranked results."""

    backend: str
    hits: list[SearchHit]


def reciprocal_rank_fusion(
    ranked_lists: list[RankedHitList],
    *,
    top_k: int = 5,
    k: int = DEFAULT_RRF_K,
) -> list[SearchHit]:
    """Merge multiple ranked lists using RRF (Cormack et al.).

    score(d) = Σ 1 / (k + rank_i(d)) across lists where document appears.
    """
    if not ranked_lists:
        return []

    flat = [h for rl in ranked_lists for h in rl.hits]
    if not flat:
        return []

    # Single list — preserve order, no fusion overhead
    if len(ranked_lists) == 1 and ranked_lists[0].hits:
        return ranked_lists[0].hits[:top_k]

    scores: dict[str, float] = {}
    best_hit: dict[str, SearchHit] = {}

    for rl in ranked_lists:
        for rank, hit in enumerate(rl.hits, start=1):
            doc_id = hit.doc_id
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
            existing = best_hit.get(doc_id)
            if existing is None or hit.score > existing.score:
                best_hit[doc_id] = hit

    fused: list[SearchHit] = []
    for doc_id in sorted(scores, key=scores.get, reverse=True)[:top_k]:
        source = best_hit[doc_id]
        fused.append(
            SearchHit(
                doc_id=source.doc_id,
                title=source.title,
                content=source.content,
                source=source.source,
                domain=source.domain,
                score=round(scores[doc_id], 6),
                backend=f"rrf:{source.backend}",
            )
        )
    return fused
