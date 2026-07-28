"""Tests for RRF fusion."""

from __future__ import annotations

from core.search.fusion import RankedHitList, reciprocal_rank_fusion
from core.search.pgvector_store import SearchHit


def _hit(doc_id: str, score: float, backend: str = "pgvector") -> SearchHit:
    return SearchHit(
        doc_id=doc_id,
        title=doc_id,
        content=f"content-{doc_id}",
        source="test",
        domain="general",
        score=score,
        backend=backend,
    )


def test_rrf_single_list_passthrough():
    hits = [_hit("a", 0.9), _hit("b", 0.8)]
    fused = reciprocal_rank_fusion([RankedHitList("pgvector", hits)], top_k=2)
    assert [h.doc_id for h in fused] == ["a", "b"]


def test_rrf_merges_shared_documents():
    list_a = [_hit("a", 0.9), _hit("b", 0.7)]
    list_b = [_hit("b", 0.95), _hit("c", 0.6)]
    fused = reciprocal_rank_fusion(
        [RankedHitList("pgvector", list_a), RankedHitList("pg_fts", list_b)],
        top_k=3,
    )
    assert fused[0].doc_id == "b"
    assert fused[0].backend.startswith("rrf:")
    assert {h.doc_id for h in fused} == {"a", "b", "c"}
