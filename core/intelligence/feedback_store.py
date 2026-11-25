"""Persist feedback — chat traces + user ratings + export for training."""

from __future__ import annotations

import json
import logging
from typing import Any, Literal

from sqlalchemy import text

from config import get_settings
from core.database.engines import get_platform_engine, platform_db_configured
from core.intelligence.feedback import FeedbackRecord, get_by_trace_id, list_feedback, upsert_feedback

logger = logging.getLogger(__name__)

ExportFormat = Literal["jsonl", "openai", "pairs"]


def save_chat_trace(
    *,
    trace_id: str,
    session_id: str,
    user_message: str,
    response: str,
    eval_score: float | None = None,
) -> None:
    """Auto-save Q&A after each chat — foundation for eval + fine-tune."""
    record = FeedbackRecord(
        trace_id=trace_id,
        session_id=session_id,
        user_message=user_message,
        response=response,
        eval_score=eval_score,
    )
    upsert_feedback(record)
    _persist_upsert(record)


def apply_user_rating(
    *, trace_id: str, rating: int, comment: str = "", auto_promote: bool = False
) -> bool:
    """User rates a previous chat — updates existing trace row.

    auto_promote is opt-in: promotion copies the Q&A into the RAG store shared by every user, so
    only a caller who trusts the rater (admin / service key) may turn it on.
    """
    existing = get_by_trace_id(trace_id)
    if existing:
        existing.rating = rating
        existing.comment = comment
        _persist_rating(trace_id, rating, comment)
    else:
        settings = get_settings()
        if not settings.platform_database_url or not _persist_rating(trace_id, rating, comment):
            return False

    if auto_promote:
        _try_auto_promote(trace_id, rating)
    return True


def _try_auto_promote(trace_id: str, rating: int) -> None:
    """Schedule background RAG promotion when rating meets threshold."""
    settings = get_settings()
    if settings.feedback_auto_promote_min_rating <= 0 or rating < settings.feedback_auto_promote_min_rating:
        return

    from core.search.embeddings import embeddings_enabled

    if not embeddings_enabled():
        return
    if not (settings.migrate_database_url or settings.database_url):
        return

    import asyncio

    from core.intelligence.knowledge_promotion import maybe_auto_promote

    async def _run() -> None:
        try:
            await maybe_auto_promote(trace_id=trace_id, rating=rating)
        except Exception as exc:
            logger.warning("Auto-promote failed for %s: %s", trace_id, exc)

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_run())
    except RuntimeError:
        logger.debug("Skip auto-promote — no running event loop (trace_id=%s)", trace_id)


def list_feedback_records(
    *,
    limit: int = 50,
    trace_id: str | None = None,
    min_rating: int | None = None,
) -> list[dict[str, Any]]:
    settings = get_settings()
    if settings.platform_database_url:
        return _list_from_db(
            limit=limit, trace_id=trace_id, min_rating=min_rating,
        )
    items = list_feedback(trace_id=trace_id, limit=limit)
    if min_rating is not None:
        items = [i for i in items if i.rating is not None and i.rating >= min_rating]
    return [_record_to_dict(r) for r in items]


def export_training_dataset(
    *,
    min_rating: int = 4,
    min_eval_score: float = 0.0,
    fmt: ExportFormat = "jsonl",
    limit: int = 1000,
) -> str:
    """Export filtered Q&A pairs for SFT / eval."""
    rows = list_feedback_records(limit=limit, min_rating=None)
    filtered = [
        r for r in rows
        if (r.get("rating") is None or r.get("rating", 0) >= min_rating)
        and (r.get("eval_score") is None or r.get("eval_score", 0) >= min_eval_score)
        and r.get("user_message") and r.get("response")
    ]

    lines: list[str] = []
    for r in filtered:
        if fmt == "pairs":
            lines.append(json.dumps({
                "trace_id": r["trace_id"],
                "input": r["user_message"],
                "output": r["response"],
                "rating": r.get("rating"),
                "eval_score": r.get("eval_score"),
            }, ensure_ascii=False))
        elif fmt == "openai":
            lines.append(json.dumps({
                "messages": [
                    {"role": "user", "content": r["user_message"]},
                    {"role": "assistant", "content": r["response"]},
                ],
            }, ensure_ascii=False))
        else:
            lines.append(json.dumps({
                "trace_id": r["trace_id"],
                "session_id": r.get("session_id"),
                "user_message": r["user_message"],
                "response": r["response"],
                "rating": r.get("rating"),
                "eval_score": r.get("eval_score"),
                "comment": r.get("comment"),
            }, ensure_ascii=False))

    return "\n".join(lines)


def _record_to_dict(record: FeedbackRecord) -> dict[str, Any]:
    return {
        "trace_id": record.trace_id,
        "session_id": record.session_id,
        "user_message": record.user_message,
        "response": record.response,
        "rating": record.rating,
        "comment": record.comment,
        "eval_score": record.eval_score,
        "created_at": record.created_at,
    }


def _persist_upsert(record: FeedbackRecord) -> None:
    settings = get_settings()
    if not platform_db_configured():
        return
    try:
        with get_platform_engine().connect() as conn:
            conn.execute(
                text("""
                    INSERT INTO platform.feedback
                        (trace_id, session_id, user_message, response, rating, comment, eval_score)
                    VALUES
                        (:trace_id, :session_id, :user_message, :response, :rating, :comment, :eval_score)
                    ON CONFLICT (trace_id) DO UPDATE SET
                        session_id = EXCLUDED.session_id,
                        user_message = EXCLUDED.user_message,
                        response = EXCLUDED.response,
                        eval_score = EXCLUDED.eval_score
                """),
                {
                    "trace_id": record.trace_id,
                    "session_id": record.session_id,
                    "user_message": record.user_message,
                    "response": record.response,
                    "rating": record.rating,
                    "comment": record.comment,
                    "eval_score": record.eval_score,
                },
            )
            conn.commit()
    except Exception as exc:
        logger.warning("Chat trace persist failed (in-memory only): %s", exc)


def _persist_rating(trace_id: str, rating: int, comment: str) -> bool:
    settings = get_settings()
    if not platform_db_configured():
        return True
    try:
        with get_platform_engine().connect() as conn:
            result = conn.execute(
                text("""
                    UPDATE platform.feedback
                    SET rating = :rating, comment = :comment
                    WHERE trace_id = :trace_id
                """),
                {"trace_id": trace_id, "rating": rating, "comment": comment},
            )
            conn.commit()
            return result.rowcount > 0
    except Exception as exc:
        logger.warning("Rating persist failed: %s", exc)
        return False


def _list_from_db(
    *,
    limit: int,
    trace_id: str | None,
    min_rating: int | None,
) -> list[dict[str, Any]]:
    settings = get_settings()
    if not platform_db_configured():
        return []
    engine = get_platform_engine()
    clauses = []
    params: dict[str, Any] = {"limit": min(limit, 2000)}
    if trace_id:
        clauses.append("trace_id = :trace_id")
        params["trace_id"] = trace_id
    if min_rating is not None:
        clauses.append("rating >= :min_rating")
        params["min_rating"] = min_rating
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    sql = f"""
        SELECT trace_id, session_id, user_message, response, rating, comment, eval_score, created_at
        FROM platform.feedback
        {where}
        ORDER BY created_at DESC
        LIMIT :limit
    """
    with engine.connect() as conn:
        rows = conn.execute(text(sql), params).mappings().all()
    items = [dict(r) for r in rows]
    for r in items:
        if r.get("created_at"):
            r["created_at"] = r["created_at"].isoformat()
    return items
