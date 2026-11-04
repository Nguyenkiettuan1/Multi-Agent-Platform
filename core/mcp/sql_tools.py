"""Shared SQL tools — used by MCP server and db-worker (single source of truth)."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from config import get_settings
from core.database.engines import get_app_read_engine

FORBIDDEN_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE|EXEC|EXECUTE)\b",
    re.IGNORECASE,
)


class SqlToolError(Exception):
    """Raised when SQL tool validation or execution fails."""


@lru_cache
def _get_engine() -> Engine:
    return get_app_read_engine()


def validate_read_only(sql: str) -> None:
    if FORBIDDEN_KEYWORDS.search(sql):
        raise SqlToolError("Only SELECT queries are allowed. Write operations are forbidden.")


def list_tables() -> list[str]:
    inspector = inspect(_get_engine())
    return inspector.get_table_names()


def describe_table(table_name: str) -> list[dict[str, Any]]:
    inspector = inspect(_get_engine())
    columns = inspector.get_columns(table_name)
    return [
        {"name": col["name"], "type": str(col["type"]), "nullable": col.get("nullable", True)}
        for col in columns
    ]


def execute_query(sql: str) -> list[dict[str, Any]]:
    settings = get_settings()
    query = sql.strip().rstrip(";")
    validate_read_only(query)

    if "LIMIT" not in query.upper():
        query = f"{query} LIMIT {settings.mcp_max_rows}"

    with _get_engine().connect() as conn:
        conn = conn.execution_options(timeout=settings.mcp_query_timeout_seconds)
        result = conn.execute(text(query))
        return [dict(row._mapping) for row in result.fetchmany(settings.mcp_max_rows)]


def execute_query_json(sql: str) -> str:
    rows = execute_query(sql)
    return json.dumps(rows, ensure_ascii=False, default=str)
