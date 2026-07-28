"""Audit log — ghi vào platform.audit_log."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from sqlalchemy import text

from config import get_settings
from core.database.engines import get_platform_engine, platform_db_configured

logger = logging.getLogger(__name__)


def _parse_uuid(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return str(uuid.UUID(value))
    except ValueError:
        return None


def write_audit(
    *,
    trace_id: str,
    action: str,
    agent_name: str = "gateway",
    session_id: str | None = None,
    user_id: str | None = None,
    payload: dict[str, Any] | None = None,
    sql_executed: str | None = None,
) -> None:
    if not platform_db_configured():
        return

    try:
        with get_platform_engine().connect() as conn:
            session_uuid = _parse_uuid(session_id)
            conn.execute(
                text("""
                    INSERT INTO platform.audit_log
                        (trace_id, session_id, user_id, agent_name, action, payload, sql_executed)
                    VALUES
                        (:trace_id, :session_id, :user_id, :agent_name, :action,
                         CAST(:payload AS jsonb), :sql_executed)
                """),
                {
                    "trace_id": trace_id,
                    "session_id": session_uuid,
                    "user_id": user_id,
                    "agent_name": agent_name,
                    "action": action,
                    "payload": json.dumps({**(payload or {}), **({"session_ref": session_id} if session_id and not session_uuid else {})}),
                    "sql_executed": sql_executed,
                },
            )
            conn.commit()
    except Exception as exc:
        logger.warning("Audit write failed: %s", exc)


def list_audit(
    *,
    limit: int = 50,
    trace_id: str | None = None,
) -> list[dict[str, Any]]:
    if not platform_db_configured():
        return []

    where = "WHERE trace_id = :trace_id" if trace_id else ""
    sql = f"""
        SELECT id, trace_id, session_id, user_id, agent_name, action,
               payload, sql_executed, created_at
        FROM platform.audit_log
        {where}
        ORDER BY created_at DESC
        LIMIT :limit
    """
    params: dict[str, Any] = {"limit": limit}
    if trace_id:
        params["trace_id"] = trace_id

    with get_platform_engine().connect() as conn:
        rows = conn.execute(text(sql), params).mappings().all()
    return [dict(r) for r in rows]
