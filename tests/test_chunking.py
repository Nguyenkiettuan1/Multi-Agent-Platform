"""Tests for chunking and query embedding."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from core.search.chunking import analyze_chunks, chunk_text
from core.search.pgvector_store import SearchHit


def test_chunk_text_splits_long_document():
    text = "Đoạn một. " * 50 + "\n\n" + "Đoạn hai. " * 50
    chunks = chunk_text(text, chunk_size=200, chunk_overlap=40)
    assert len(chunks) >= 2
    assert all(c.char_count <= 300 for c in chunks)  # some tolerance for sentence boundary


def test_analyze_chunks_warns_on_single_huge_chunk():
    chunks = chunk_text("x" * 3000, chunk_size=800, chunk_overlap=0)
    analysis = analyze_chunks(chunks)
    assert analysis.chunk_count >= 1
    if analysis.chunk_count == 1:
        assert any("1 chunk" in w for w in analysis.warnings)


@pytest.mark.asyncio
async def test_vector_search_calls_embed_query():
    mock_vec = [0.1] * 1536
    mock_hits = [
        SearchHit(
            doc_id="c1", title="T", content="body",
            source="seed", domain="general", score=0.9, backend="pgvector",
        )
    ]

    with (
        patch("core.search.pgvector_store.embed_query", new_callable=AsyncMock) as mock_eq,
        patch("core.search.pgvector_store._read_engine") as mock_engine,
    ):
        mock_eq.return_value = mock_vec
        conn = mock_engine.return_value.connect.return_value.__enter__.return_value
        conn.execute.return_value.mappings.return_value.all.return_value = [
            {"doc_id": "c1", "title": "T", "content": "body", "source": "seed", "domain": "general", "score": 0.9}
        ]

        from core.search.pgvector_store import vector_search

        hits = await vector_search("hop dong lao dong", top_k=3)
        mock_eq.assert_called_once_with("hop dong lao dong")
        sql = conn.execute.call_args[0][0].text
        assert "CAST(:vec AS vector)" in sql
        assert ":vec::vector" not in sql
        assert len(hits) == 1
        assert hits[0].backend == "pgvector"
