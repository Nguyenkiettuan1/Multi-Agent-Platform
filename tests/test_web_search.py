"""Tests for web search and citations."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from core.search.citations import (
    SourceCitation,
    append_citations_to_response,
    citations_from_web_results,
    format_references_block,
)
from core.search.combined_search import combined_search
from core.search.pgvector_store import SearchHit
from workflows.state import AgentId, WorkerResult


def test_format_references_block_with_url():
    citations = [
        SourceCitation(
            ref_id="W1", title="Example", excerpt="text",
            source_type="web", backend="web_search", url="https://example.com",
        ),
    ]
    block = format_references_block(citations)
    assert "## Nguồn tham khảo" in block
    assert "https://example.com" in block
    assert "[W1]" in block


def test_append_citations_to_response():
    worker = WorkerResult(
        task_id="t1",
        agent=AgentId.RESEARCH_WORKER,
        summary="Theo [W1] hợp đồng...",
        citations=[c.to_dict() for c in citations_from_web_results([
            {"title": "Law", "url": "https://law.example", "content": "..."},
        ])],
    )
    final, cites = append_citations_to_response("Trả lời ngắn.", [worker])
    assert "## Nguồn tham khảo" not in final
    assert final == "Trả lời ngắn."
    assert len(cites) == 1


def test_strip_references_block():
    from core.search.citations import strip_references_block

    text = "Câu trả lời.\n\n## Nguồn tham khảo\n- **[W1]** Example"
    assert strip_references_block(text) == "Câu trả lời."


@pytest.mark.asyncio
async def test_combined_search_falls_back_to_web_when_kb_fails():
    web_hits = [{"title": "Web", "url": "https://x.com", "content": "web data", "score": 0.8}]

    with (
        patch("core.search.combined_search.hybrid_search", new_callable=AsyncMock) as mock_kb,
        patch("core.search.combined_search.web_search_enabled", return_value=True),
        patch("core.search.combined_search.web_search", new_callable=AsyncMock) as mock_web,
    ):
        mock_kb.side_effect = RuntimeError("pgvector broken")
        mock_web.return_value = web_hits

        result = await combined_search("tin tuc AI moi nhat")

    assert len(result.citations) == 1
    assert result.citations[0].ref_id == "W1"
    assert "web_search" in result.backends_used


@pytest.mark.asyncio
async def test_vector_search_falls_back_on_pgvector_error():
    mock_vec = [0.1] * 8
    fts_hits = [
        SearchHit(
            doc_id="fts-1", title="FTS", content="fallback body",
            source="seed", domain="general", score=0.5, backend="pg_fts",
        )
    ]

    with (
        patch("core.search.pgvector_store.embed_query", new_callable=AsyncMock) as mock_eq,
        patch("core.search.pgvector_store._read_engine") as mock_engine,
        patch("core.search.pgvector_store.keyword_search", return_value=fts_hits) as mock_kw,
    ):
        mock_eq.return_value = mock_vec
        conn = mock_engine.return_value.connect.return_value.__enter__.return_value
        conn.execute.side_effect = Exception('type "vector" does not exist')

        from core.search.pgvector_store import vector_search

        hits = await vector_search("hop dong", top_k=3)

    mock_kw.assert_called_once()
    assert hits == fts_hits


@pytest.mark.asyncio
async def test_combined_search_merges_kb_and_web():
    mock_hits = [
        SearchHit(
            doc_id="doc-1", title="Internal", content="data",
            source="seed", domain="general", score=0.9, backend="pgvector",
        )
    ]
    web_hits = [{"title": "Web", "url": "https://x.com", "content": "web data", "score": 0.8}]

    with (
        patch("core.search.combined_search.hybrid_search", new_callable=AsyncMock) as mock_kb,
        patch("core.search.combined_search.web_search_enabled", return_value=True),
        patch("core.search.combined_search.web_search", new_callable=AsyncMock) as mock_web,
    ):
        mock_kb.return_value = type("R", (), {"hits": mock_hits, "backends_used": ["pgvector"]})()
        mock_web.return_value = web_hits

        result = await combined_search("test query")

    assert len(result.citations) == 2
    assert result.citations[0].ref_id == "D1"
    assert result.citations[1].ref_id == "W1"
    assert "web_search" in result.backends_used
