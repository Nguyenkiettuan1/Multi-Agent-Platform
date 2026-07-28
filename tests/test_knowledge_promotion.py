"""Tests for feedback → RAG promotion."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from core.intelligence.knowledge_promotion import _promoted_doc_id, maybe_auto_promote


@pytest.fixture(autouse=True)
def clear_feedback():
    from core.intelligence import feedback

    feedback._feedback_by_trace.clear()
    yield
    feedback._feedback_by_trace.clear()


def test_promoted_doc_id_stable():
    assert _promoted_doc_id("abc-123").startswith("feedback-")


@pytest.mark.asyncio
async def test_maybe_auto_promote_skips_low_rating():
    with patch("core.intelligence.knowledge_promotion.get_settings") as mock_settings:
        mock_settings.return_value.feedback_auto_promote_min_rating = 5
        result = await maybe_auto_promote(trace_id="t1", rating=3)
    assert result is None


@pytest.mark.asyncio
async def test_maybe_auto_promote_indexes_high_rating():
    from core.intelligence.feedback_store import save_chat_trace

    save_chat_trace(
        trace_id="t-promote",
        session_id="s1",
        user_message="Câu hỏi?",
        response="Trả lời.",
    )

    with (
        patch("core.intelligence.knowledge_promotion.get_settings") as mock_settings,
        patch("core.intelligence.knowledge_promotion.is_already_promoted", return_value=False),
        patch("core.intelligence.knowledge_promotion.embed_text", new_callable=AsyncMock) as mock_embed,
        patch("core.intelligence.knowledge_promotion.upsert_document") as mock_upsert,
        patch("core.intelligence.knowledge_promotion._mark_promoted") as mock_mark,
    ):
        mock_settings.return_value.feedback_auto_promote_min_rating = 5
        mock_settings.return_value.platform_database_url = ""
        mock_embed.return_value = [0.1] * 8
        result = await maybe_auto_promote(trace_id="t-promote", rating=5)

    assert result is not None
    assert result["promoted"] is True
    mock_upsert.assert_called_once()
    mock_mark.assert_called_once()
