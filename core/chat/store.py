"""Chat store — sessions and messages owned by a user (platform schema, no in-memory fallback).

Chat history is per-user server state, so a missing platform DB must fail loudly instead of
silently degrading to a process-local store that would leak or lose conversations.

Pagination invariant: every keyset query sorts and filters on the SAME key
((updated_at, id) for sessions, message id for turns). Sorting by one column and filtering by
another silently drops rows when the two orders disagree.
"""

from __future__ import annotations

import base64
import binascii
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import bindparam, text

from core.database.engines import get_platform_engine

TITLE_MAX = 200
ERROR_MAX = 200


def create_session(owner_id: str, title: str) -> str:
    """Create a session and return its id (uuid4 hex, same shape as the LangGraph thread_id).

    An unknown owner raises sqlalchemy IntegrityError (FK) — the owner comes from an
    authenticated principal, so a miss is a programming error, not a business outcome.
    """
    session_id = uuid.uuid4().hex
    with get_platform_engine().begin() as conn:
        conn.execute(
            text("""
                INSERT INTO platform.chat_sessions (id, owner_id, title)
                VALUES (:id, :owner, :title)
            """),
            {"id": session_id, "owner": owner_id, "title": (title or "")[:TITLE_MAX]},
        )
    return session_id


def get_owned_session(session_id: str, owner_id: str) -> dict[str, Any] | None:
    """Session row if it exists AND belongs to owner_id; None otherwise (callers answer 404)."""
    with get_platform_engine().connect() as conn:
        row = conn.execute(
            text("""
                SELECT id, title, created_at, updated_at
                FROM platform.chat_sessions
                WHERE id = :id AND owner_id = :owner
            """),
            {"id": session_id, "owner": owner_id},
        ).mappings().first()
    if row is None:
        return None
    return {
        "session_id": row["id"],
        "title": row["title"],
        "created_at": row["created_at"].isoformat(),
        "updated_at": row["updated_at"].isoformat(),
    }


def _encode_cursor(updated_at: datetime, session_id: str) -> str:
    raw = f"{updated_at.isoformat()}|{session_id}".encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, str]:
    """Raise ValueError on any malformed cursor (route maps it to 422)."""
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
        iso, sep, session_id = raw.partition("|")  # iso timestamps contain no '|'
        if not sep or not session_id:
            raise ValueError("missing separator")
        updated_at = datetime.fromisoformat(iso)
        if updated_at.tzinfo is None:
            raise ValueError("naive timestamp")
    except (ValueError, binascii.Error) as exc:  # UnicodeError is a ValueError subclass
        raise ValueError(f"Invalid cursor: {cursor!r}") from exc
    return updated_at, session_id


def list_sessions(
    owner_id: str, *, limit: int, before: str | None
) -> tuple[list[dict[str, Any]], str | None]:
    """Owner's sessions, newest first. Returns (items, next_before); next_before None = last page."""
    if limit < 1:
        raise ValueError(f"limit must be >= 1, got {limit}")
    params: dict[str, Any] = {"owner": owner_id, "lim": limit + 1}
    cursor_sql = ""
    if before is not None:
        params["u"], params["cid"] = _decode_cursor(before)
        cursor_sql = "AND (updated_at, id) < (:u, :cid)"
    with get_platform_engine().connect() as conn:
        rows = conn.execute(
            text(f"""
                SELECT id, title, updated_at
                FROM platform.chat_sessions
                WHERE owner_id = :owner {cursor_sql}
                ORDER BY updated_at DESC, id DESC
                LIMIT :lim
            """),
            params,
        ).mappings().all()
    page = rows[:limit]
    items = [
        {"session_id": r["id"], "title": r["title"], "updated_at": r["updated_at"].isoformat()}
        for r in page
    ]
    next_before = _encode_cursor(page[-1]["updated_at"], page[-1]["id"]) if len(rows) > limit else None
    return items, next_before


def append_message(
    *,
    session_id: str,
    role: str,
    content: str,
    status: str = "completed",
    trace_id: str | None = None,
    error: str | None = None,
) -> None:
    """Insert one message and bump the session's updated_at, in one transaction.

    A repeated (trace_id, role) is a retry: the insert is a no-op and updated_at is left alone so a
    retry cannot reorder the session list. Unknown session raises IntegrityError (FK).
    """
    with get_platform_engine().begin() as conn:
        inserted = conn.execute(
            text("""
                INSERT INTO platform.chat_messages (session_id, role, content, status, trace_id, error)
                VALUES (:sid, :role, :content, :status, :trace, :error)
                ON CONFLICT (trace_id, role) WHERE trace_id IS NOT NULL DO NOTHING
            """),
            {
                "sid": session_id,
                "role": role,
                "content": content or "",
                "status": status,
                "trace": trace_id,
                "error": error[:ERROR_MAX] if error is not None else None,
            },
        ).rowcount
        if inserted:
            conn.execute(
                text("UPDATE platform.chat_sessions SET updated_at = now() WHERE id = :sid"),
                {"sid": session_id},
            )


def load_recent_messages(session_id: str, *, limit_turns: int = 20) -> list[dict[str, str]]:
    """LLM context: the newest `limit_turns` fully completed turns, oldest first.

    A turn counts only when user AND assistant are both 'completed' with the same trace_id; a failed
    or unanswered turn would leave a user message with no reply and break role alternation.
    """
    if limit_turns < 1:
        raise ValueError(f"limit_turns must be >= 1, got {limit_turns}")
    with get_platform_engine().connect() as conn:
        rows = conn.execute(
            text("""
                SELECT u.content AS question, a.content AS answer
                FROM platform.chat_messages u
                JOIN platform.chat_messages a
                  ON a.trace_id = u.trace_id AND a.role = 'assistant' AND a.status = 'completed'
                WHERE u.session_id = :sid AND a.session_id = :sid
                  AND u.role = 'user' AND u.status = 'completed'
                ORDER BY u.id DESC
                LIMIT :lim
            """),
            {"sid": session_id, "lim": limit_turns},
        ).mappings().all()
    messages: list[dict[str, str]] = []
    for r in reversed(rows):
        messages.append({"role": "user", "content": r["question"]})
        messages.append({"role": "assistant", "content": r["answer"]})
    return messages


def list_turns(
    session_id: str, *, limit: int, before: int | None
) -> tuple[list[dict[str, Any]], bool, str | None]:
    """Newest `limit` turns older than user-message id `before`, returned oldest first.

    Returns (turns, has_more, next_before); next_before is str(id of the oldest returned turn) when
    has_more, else None. A user message without trace_id (not produced by the runner) cannot be
    matched to an answer, so it is shown as an 'incomplete' turn rather than hidden.
    """
    if limit < 1:
        raise ValueError(f"limit must be >= 1, got {limit}")
    params: dict[str, Any] = {"sid": session_id, "lim": limit + 1}
    cursor_sql = ""
    if before is not None:
        params["before"] = before
        cursor_sql = "AND id < :before"
    with get_platform_engine().connect() as conn:
        users = conn.execute(
            text(f"""
                SELECT id FROM platform.chat_messages
                WHERE session_id = :sid AND role = 'user' {cursor_sql}
                ORDER BY id DESC
                LIMIT :lim
            """),
            params,
        ).scalars().all()
        has_more = len(users) > limit
        ids = users[:limit]
        if not ids:
            return [], False, None
        # One query for the whole page: answer by trace_id plus feedback (trace_id is unique there).
        rows = conn.execute(
            text("""
                SELECT u.id, u.trace_id, u.content AS question, u.created_at,
                       a.content AS answer, a.status AS answer_status,
                       fb.rating, fb.comment, fb.eval_score
                FROM platform.chat_messages u
                LEFT JOIN platform.chat_messages a
                  ON a.trace_id = u.trace_id AND a.role = 'assistant' AND a.session_id = u.session_id
                LEFT JOIN platform.feedback fb ON fb.trace_id = u.trace_id
                WHERE u.id IN :ids
                ORDER BY u.id ASC
            """).bindparams(bindparam("ids", expanding=True)),
            {"ids": list(ids)},
        ).mappings().all()
    turns = [
        {
            "trace_id": r["trace_id"],
            "session_id": session_id,
            "user_message": r["question"],
            "response": r["answer"] or "",
            "rating": r["rating"],
            "comment": r["comment"],
            "eval_score": r["eval_score"],
            "created_at": r["created_at"].isoformat(),
            "status": r["answer_status"] or "incomplete",
        }
        for r in rows
    ]
    return turns, has_more, str(ids[-1]) if has_more else None


def trace_owner(trace_id: str) -> str | None:
    """Owner id (str) of the session holding this trace, or None if no chat message has it."""
    with get_platform_engine().connect() as conn:
        owner = conn.execute(
            text("""
                SELECT s.owner_id
                FROM platform.chat_messages m
                JOIN platform.chat_sessions s ON s.id = m.session_id
                WHERE m.trace_id = :trace
                LIMIT 1
            """),
            {"trace": trace_id},
        ).scalar()
    return str(owner) if owner is not None else None
