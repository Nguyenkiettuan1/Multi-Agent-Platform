"""Tests for hybrid search."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from core.search.combined_search import combined_search
from core.search.hybrid import hybrid_search
from core.search.pgvector_store import SearchHit


@pytest.mark.asyncio
async def test_hybrid_search_uses_pg_fallback():
    mock_hits = [
        SearchHit(
            doc_id="doc-1",
            title="Test",
            content="REST API content",
            source="seed",
            domain="general",
            score=0.9,
            backend="pg_fts",
        )
    ]

    with (
        patch("core.search.hybrid.azure_search_enabled", return_value=False),
        patch("core.search.hybrid.vector_search", new_callable=AsyncMock) as mock_vec,
        patch("core.search.hybrid.keyword_search", return_value=[]),
    ):
        mock_vec.return_value = mock_hits
        result = await hybrid_search("REST API")

    assert len(result.hits) == 1
    assert result.hits[0].doc_id == "doc-1"


@pytest.mark.asyncio
async def test_combined_search_knowledge_only_when_no_web_key():
    mock_hits = [
        SearchHit(
            doc_id="doc-1", title="Test", content="content",
            source="seed", domain="general", score=0.9, backend="pg_fts",
        )
    ]

    with (
        patch("core.search.combined_search.hybrid_search", new_callable=AsyncMock) as mock_kb,
        patch("core.search.combined_search.web_search_enabled", return_value=False),
    ):
        mock_kb.return_value = type("R", (), {"hits": mock_hits, "backends_used": ["pg_fts"]})()
        result = await combined_search("REST API", include_web=True)

    assert len(result.citations) == 1
    assert result.citations[0].ref_id == "D1"
