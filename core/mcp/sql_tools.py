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

# Defense in depth on top of the allowlist: checked on SQL with literals/comments
# masked, so a keyword inside a string never trips it. Covers data-modifying CTEs,
# SELECT ... INTO (creates a table) and FOR [NO KEY] UPDATE / FOR [KEY] SHARE
# (take row locks).
FORBIDDEN_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE|EXEC|EXECUTE|"
    r"COPY|CALL|INTO|FOR\s+(?:NO\s+KEY\s+|KEY\s+)?SHARE)\b",
    re.IGNORECASE,
)
_FIRST_WORD = re.compile(r"[A-Za-z_]+")
# PostgreSQL lexer: identifier/tag start = ASCII letter, '_' or any char >= 0x80; a
# dollar-quote tag is delimited by '$' and may not itself contain '$'.
_DOLLAR_TAG = re.compile(r"\$(?:(?:[A-Za-z_]|[^\x00-\x7f])(?:[A-Za-z0-9_]|[^\x00-\x7f])*)?\$")
_LINE_END = re.compile(r"[\r\n]")
_ALLOWED_START = {"SELECT", "WITH"}
# Bounds the scanner's CPU cost; far above any query the agents are expected to send.
MAX_SQL_CHARS = 20_000


class SqlToolError(Exception):
    """Raised when SQL tool validation or execution fails."""


@lru_cache
def _get_engine() -> Engine:
    return get_app_read_engine()


def _is_ident_start(c: str) -> bool:
    # Every char >= 0x80 (even NBSP) is an identifier char to PostgreSQL, whatever
    # Python's str.isalpha() says.
    return c.isalpha() or c == "_" or ord(c) >= 0x80


def _is_ident_cont(c: str) -> bool:
    # '$' continues an identifier in PostgreSQL (a$$x$ is a legal name).
    return _is_ident_start(c) or c.isdigit() or c == "$"


def _quoted_end(sql: str, start: int, quote: str, backslash: bool) -> int:
    """Index just past the literal whose opening quote is at `start`."""
    j, n = start + 1, len(sql)
    while True:
        if j >= n:
            raise SqlToolError("Unterminated quoted string or identifier in SQL.")
        if backslash and sql[j] == "\\":
            j += 2
        elif sql[j] == quote:
            if j + 1 < n and sql[j + 1] == quote:
                j += 2
            else:
                return j + 1
        else:
            j += 1


def _scan(sql: str) -> tuple[str, str]:
    """Return (clean, masked): comments removed; masked also blanks every literal.

    Validation must look only at real SQL tokens, so quoted text is replaced by an
    empty literal in `masked`. Mirrors the PostgreSQL lexer: identifiers are consumed
    as whole tokens, so a string prefix (E, B, X, N, U&) or a $tag$ is only recognised
    at a token start; handles '' escapes, E'..' backslashes, "idents", $tag$..$tag$
    (closed only by the same tag) and nested /* */ comments. Assumes
    standard_conforming_strings = on (execute_query sets it for the transaction).
    """
    clean: list[str] = []
    masked: list[str] = []
    i, n = 0, len(sql)
    while i < n:
        c = sql[i]
        if sql.startswith("--", i):
            # PostgreSQL ends a -- comment at the first CR *or* LF.
            m = _LINE_END.search(sql, i)
            i = n if m is None else m.start()
            clean.append(" ")
            masked.append(" ")
        elif sql.startswith("/*", i):
            depth, i = 1, i + 2
            while depth and i < n:
                if sql.startswith("/*", i):
                    depth, i = depth + 1, i + 2
                elif sql.startswith("*/", i):
                    depth, i = depth - 1, i + 2
                else:
                    i += 1
            if depth:
                raise SqlToolError("Unterminated /* comment in SQL.")
            clean.append(" ")
            masked.append(" ")
        elif c in "'\"":
            end = _quoted_end(sql, i, c, backslash=False)
            clean.append(sql[i:end])
            masked.append(c + c)
            i = end
        elif _is_ident_start(c) or c.isdigit():
            j = i + 1
            while j < n and _is_ident_cont(sql[j]):
                j += 1
            word = sql[i:j]
            prefix = word.lower() if not c.isdigit() else ""
            quote_at = None
            if prefix == "u" and sql.startswith("&'", j):
                quote_at = j + 1
            elif prefix in {"e", "b", "x", "n"} and sql.startswith("'", j):
                quote_at = j
            if quote_at is None:
                clean.append(word)
                masked.append(word)
                i = j
            else:
                end = _quoted_end(sql, quote_at, "'", backslash=prefix == "e")
                clean.append(sql[i:end])
                masked.append("''")
                i = end
        elif c == "$" and (m := _DOLLAR_TAG.match(sql, i)):
            end = sql.find(m.group(0), m.end())
            if end == -1:
                raise SqlToolError("Unterminated dollar-quoted string in SQL.")
            end += len(m.group(0))
            clean.append(sql[i:end])
            masked.append("''")
            i = end
        else:
            clean.append(c)
            masked.append(c)
            i += 1
    return "".join(clean), "".join(masked)


def _check_parentheses(masked: str) -> None:
    # The row cap wraps the query as a subquery, so unbalanced parentheses could
    # close the wrapper early.
    depth = 0
    for c in masked:
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth < 0:
                break
    if depth != 0:
        raise SqlToolError("Unbalanced parentheses in SQL.")


def _check(sql: str) -> str:
    """Validate and return the single statement without comments or trailing ';'."""
    if len(sql) > MAX_SQL_CHARS:
        raise SqlToolError(f"SQL is too long ({len(sql)} chars, max {MAX_SQL_CHARS}).")
    if "\x00" in sql:
        raise SqlToolError("SQL must not contain NUL characters.")
    clean, masked = _scan(sql)
    _check_parentheses(masked)
    # Trailing semicolons are harmless; one anywhere else means a second statement.
    stripped = masked.rstrip(" \t\r\n;")
    if ";" in stripped:
        raise SqlToolError("Only a single SQL statement is allowed.")
    match = _FIRST_WORD.match(stripped.lstrip())
    if not match or match.group(0).upper() not in _ALLOWED_START:
        raise SqlToolError("Only SELECT queries are allowed (statement must start with SELECT or WITH).")
    if FORBIDDEN_KEYWORDS.search(stripped):
        raise SqlToolError("Only SELECT queries are allowed. Write operations are forbidden.")
    # The stripped tail is only whitespace and ';' in both variants, so trimming
    # `clean` the same way yields the statement itself.
    return clean.rstrip(" \t\r\n;")


def validate_read_only(sql: str) -> None:
    _check(sql)


def prepare_query(sql: str) -> tuple[str, tuple[int]]:
    """Validate, strip comments and cap rows in the database via a wrapping subquery.

    Returns (driver_sql, params) for `exec_driver_sql`. Wrapping (rather than looking
    for the word LIMIT) cannot be faked by comments, identifiers or literals, and also
    caps a larger LIMIT written by the caller.

    The cap is a bound parameter on purpose: with parameters psycopg uses the extended
    protocol, which the server refuses to run for more than one statement. That makes
    stacked statements impossible even if the scanner above misjudges a token.
    Every '%' in the caller's SQL is doubled because the driver treats '%' as a
    placeholder marker once parameters are present.
    """
    query = _check(sql).replace("%", "%%")
    return f"SELECT * FROM ({query}\n) AS _q LIMIT %s", (int(get_settings().mcp_max_rows),)


def timeout_statement(seconds: int) -> str:
    # SQLAlchemy has no `timeout` execution option; the server enforces it instead.
    return f"SET LOCAL statement_timeout = {int(seconds) * 1000}"


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
    query, params = prepare_query(sql)

    with _get_engine().connect() as conn:
        # READ ONLY must be the first statement of the transaction; SET LOCAL
        # settings vanish at its end so pooled connections are not affected.
        # standard_conforming_strings is pinned because the scanner assumes it.
        conn.execute(text("SET TRANSACTION READ ONLY"))
        conn.execute(text("SET LOCAL standard_conforming_strings = on"))
        conn.execute(text(timeout_statement(settings.mcp_query_timeout_seconds)))
        result = conn.exec_driver_sql(query, params)
        return [dict(row._mapping) for row in result.fetchmany(settings.mcp_max_rows)]


def execute_query_json(sql: str) -> str:
    rows = execute_query(sql)
    return json.dumps(rows, ensure_ascii=False, default=str)
