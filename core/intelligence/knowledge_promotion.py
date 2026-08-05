"""Promote high-quality Q&A from feedback into RAG knowledge base."""

from __future__ import annotations

import logging
import re

from sqlalchemy import text

from config import get_settings
from core.database.engines import get_platform_engine, platform_db_configured
from core.search.embeddings import embed_text
from core.search.pgvector_store import upsert_document

logger = logging.getLogger(__name__)

_PROMOTED_PREFIX = "feedback-"


def _promoted_doc_id(trace_id: str) -> str:
    safe = re.sub(r"[^a-z0-9]", "", trace_id.lower())[:24]
    return f"{_PROMOTED_PREFIX}{safe}"


async def promote_feedback_to_knowledge(
    *,
    trace_id: str,
    user_message: str,
    response: str,
    domain: str = "general",
) -> dict:
    """Index approved Q&A pair as a knowledge document for future RAG retrieval."""
    doc_id = _promoted_doc_id(trace_id)
    title = user_message[:200].strip() or f"Q&A {trace_id[:8]}"
    content = f"Question: {user_message.strip()}\n\nAnswer: {response.strip()}"

    embedding = await embed_text(f"{title}\n{content}")
    upsert_document(
        doc_id=doc_id,
        title=title,
        content=content,
        domain=domain,
        source="feedback_promoted",
        embedding=embedding,
        metadata={
            "trace_id": trace_id,
            "promoted_from": "platform.feedback",
            "type": "qa_pair",
        },
    )
    _mark_promoted(trace_id, doc_id)
    logger.info("Promoted feedback %s → knowledge doc %s", trace_id, doc_id)
    return {
        "trace_id": trace_id,
        "doc_id": doc_id,
        "has_embedding": embedding is not None,
        "promoted": True,
    }


def is_already_promoted(trace_id: str) -> bool:
    if not platform_db_configured():
        return False
    with get_platform_engine().connect() as conn:
        row = conn.execute(
            text("SELECT promoted_to_rag FROM platform.feedback WHERE trace_id = :tid"),
            {"tid": trace_id},
        ).scalar()
    return bool(row)


def _mark_promoted(trace_id: str, doc_id: str) -> None:
    if not platform_db_configured():
        return
    with get_platform_engine().connect() as conn:
        conn.execute(
            text("""
                UPDATE platform.feedback
                SET promoted_to_rag = TRUE, promoted_doc_id = :doc_id
                WHERE trace_id = :trace_id
            """),
            {"trace_id": trace_id, "doc_id": doc_id},
        )
        conn.commit()


async def maybe_auto_promote(*, trace_id: str, rating: int) -> dict | None:
    """Auto-promote when rating meets threshold."""
    settings = get_settings()
    min_rating = settings.feedback_auto_promote_min_rating
    if min_rating <= 0 or rating < min_rating:
        return None
    if is_already_promoted(trace_id):
        return None

    record = load_feedback_for_promotion(trace_id)
    if not record:
        return None

    return await promote_feedback_to_knowledge(
        trace_id=trace_id,
        user_message=record["user_message"],
        response=record["response"],
    )


def load_feedback_for_promotion(trace_id: str) -> dict | None:
    """Load Q&A for promotion; returns None if missing or already promoted."""
    if not platform_db_configured():
        from core.intelligence.feedback import get_by_trace_id

        rec = get_by_trace_id(trace_id)
        if not rec or not rec.user_message or not rec.response:
            return None
        return {"user_message": rec.user_message, "response": rec.response}

    with get_platform_engine().connect() as conn:
        row = conn.execute(
            text("""
                SELECT user_message, response, promoted_to_rag
                FROM platform.feedback WHERE trace_id = :tid
            """),
            {"tid": trace_id},
        ).mappings().first()
    if not row or not row["user_message"] or not row["response"]:
        return None
    if row["promoted_to_rag"]:
        return None
    return dict(row)
