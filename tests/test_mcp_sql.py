"""Tests for MCP SQL tools and query builder."""

from __future__ import annotations

import pytest

from core.mcp.sql_query_builder import build_sql
from core.mcp.sql_tools import SqlToolError, validate_read_only


def test_build_sql_count():
    sql = build_sql("Co bao nhieu hop dong active?")
    assert "COUNT" in sql.upper()
    assert "active" in sql.lower()


def test_build_sql_list():
    sql = build_sql("Liet ke hop dong ABC Corp")
    assert "ABC" in sql
    assert "SELECT" in sql.upper()


def test_validate_read_only_blocks_delete():
    with pytest.raises(SqlToolError):
        validate_read_only("DELETE FROM contracts")


def test_validate_read_only_allows_select():
    validate_read_only("SELECT COUNT(*) FROM contracts")


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1; DELETE FROM contracts",
        "SELECT 1; SELECT 2",
        "WITH d AS (DELETE FROM contracts RETURNING *) SELECT * FROM d",
        "WITH u AS (UPDATE contracts SET status = 'x' RETURNING id) SELECT * FROM u",
        "WITH i AS (INSERT INTO contracts(code) VALUES ('x') RETURNING id) SELECT * FROM i",
        "COPY contracts TO '/tmp/x'",
        "CALL do_something()",
        "SET ROLE postgres",
        "DO $$ BEGIN PERFORM 1; END $$",
        "SELECT * INTO new_table FROM contracts",
        "SELECT * FROM contracts FOR UPDATE",
        "/* SELECT */ DELETE FROM contracts",
        "-- SELECT\nDELETE FROM contracts",
        "",
        "   ;  ",
        "-- only a comment",
        # '$' continues an identifier, so these are NOT dollar-quotes / E-strings
        "SELECT 1 AS a$$x$; DELETE FROM t; SELECT 1 AS b$x$",
        "SELECT a$e'\\' ; DELETE FROM t; SELECT '",
        "SELECT * FROM contracts FOR SHARE",
        "SELECT * FROM contracts FOR KEY SHARE",
        "SELECT * FROM contracts FOR NO KEY UPDATE",
        # unterminated constructs
        "SELECT 'abc",
        'SELECT "abc',
        "SELECT 1 /* never closed",
        "SELECT 1 /* a /* nested */ still open",
        "SELECT $t$ never closed",
        # non-ASCII dollar tag / identifier chars are lexed like ASCII ones by PostgreSQL
        "SELECT $é$'$é$ AS a) s; COMMIT; SELECT * FROM (SELECT 1 --'",
        # parentheses must not be able to escape the LIMIT wrapper
        "SELECT 1) a, (SELECT 2",
        "SELECT 1) s; COMMIT; DELETE FROM t; SELECT * FROM (SELECT 1 AS b$x$",
        "SELECT (1",
        "SELECT 1)",
        # resource / protocol guards
        "SELECT '" + "x" * 20_000 + "'",
        "SELECT 1\x00; DELETE FROM t",
        # U+00A0 is an identifier char for PostgreSQL, so `a<NBSP>$x$` is one name
        "SELECT 1 AS a\xa0$x$; DELETE FROM t; SELECT 1 AS b\xa0$x$",
        "SELECT $é$'$é$; DELETE FROM t; SELECT $é$'$é$",
        "SELECT 1) x UNION ALL SELECT * FROM contracts UNION ALL SELECT * FROM (SELECT 2",
        # E-string: \' does not end the literal, but a real quote afterwards does
        "SELECT E'it\\'s' ; DELETE FROM t",
    ],
)
def test_validate_read_only_rejects(sql):
    with pytest.raises(SqlToolError):
        validate_read_only(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM contracts WHERE title = 'update'",
        "SELECT * FROM contracts WHERE title = 'it''s a DELETE; DROP'",
        "SELECT 'a;b' AS x",
        "SELECT $$ delete; $$ AS x",
        'SELECT "update" FROM t',
        "  select 1 ;  ",
        "-- note\nSELECT 1 /* DELETE */",
        "WITH c AS (SELECT * FROM contracts) SELECT COUNT(*) FROM c",
        "SELECT 1 -- ; DELETE FROM x",
        "SELECT 1 AS a$$x$, 2 AS b$x$",
        "SELECT E'it\\'s; DELETE' AS x",
        "SELECT /* a /* nested */ DELETE; */ 1",
        "SELECT $tag$ it's; DELETE $$ $tag$ AS x",
        "SELECT * FROM contracts WHERE id = $1",
        "SELECT $é$a;b$é$ AS s",
        "SELECT 1 AS a\xa0b, 'x' AS c",
        "SELECT $é$ ' ; DELETE $é$, 'z' AS t",
        "SELECT é$1 AS tên_cột FROM bảng",
        "SELECT ((1 + 2) * (3)) AS n, 'a)(b' AS s",
        "SELECT COALESCE((SELECT MAX(id) FROM contracts), 0)",
        "SELECT * FROM contracts ORDER BY code LIMIT 5",
    ],
)
def test_validate_read_only_allows(sql):
    validate_read_only(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT COUNT(*) AS total FROM contracts WHERE status = 'active'",
        "SELECT COUNT(*) AS total FROM contracts",
        "SELECT code, title, status, value_vnd FROM contracts WHERE title ILIKE '%ABC%' LIMIT 10",
        "SELECT COUNT(DISTINCT client_id) AS total FROM contracts",
        "SELECT code, title, status, value_vnd FROM contracts LIMIT 10",
    ],
)
def test_build_sql_outputs_pass_and_are_wrapped_verbatim(sql):
    from core.mcp.sql_tools import prepare_query

    validate_read_only(sql)
    prepared, params = prepare_query(sql)
    # '%' is doubled for the driver; otherwise the statement is wrapped verbatim
    assert prepared == f"SELECT * FROM ({sql.replace('%', '%%')}\n) AS _q LIMIT %s"
    from config import get_settings

    assert params == (get_settings().mcp_max_rows,)


def test_line_comment_ends_at_cr_or_lf_like_postgres():
    from core.mcp.sql_tools import prepare_query

    with pytest.raises(SqlToolError):
        validate_read_only("SELECT 1 --x\r; DELETE FROM t")
    with pytest.raises(SqlToolError):
        prepare_query("SELECT 1 --x\r; DELETE FROM t")
    prepared, _ = prepare_query("SELECT 1 --x\r, 2")
    assert ", 2" in prepared


def test_prepare_query_keeps_with_and_order_by():
    from core.mcp.sql_tools import prepare_query

    prepared, _ = prepare_query("WITH c AS (SELECT 1 AS n) SELECT n FROM c ORDER BY n;")
    assert prepared.startswith("SELECT * FROM (WITH c AS (SELECT 1 AS n) SELECT n FROM c ORDER BY n\n)")


def test_prepare_query_rejects_identifier_dollar_trick():
    from core.mcp.sql_tools import prepare_query

    with pytest.raises(SqlToolError):
        prepare_query("SELECT 1 AS a$$x$; DELETE FROM t; SELECT 1 AS b$x$")


def test_prepare_query_limit_not_faked_by_comment_or_literal():
    from config import get_settings
    from core.mcp.sql_tools import prepare_query

    n = get_settings().mcp_max_rows
    for sql in [
        "SELECT 1 -- LIMIT 5",
        "SELECT 'limit' AS x",
        "SELECT 1 /* LIMIT 1 */",
        "SELECT limit_col FROM t",
    ]:
        prepared, params = prepare_query(sql)
        assert prepared.endswith(") AS _q LIMIT %s"), prepared
        assert params == (n,)
        assert "--" not in prepared and "/*" not in prepared


def test_prepare_query_caps_user_limit():
    from config import get_settings
    from core.mcp.sql_tools import prepare_query

    n = get_settings().mcp_max_rows
    prepared, params = prepare_query("SELECT 1 LIMIT 100000;")
    assert prepared.endswith(") AS _q LIMIT %s")
    assert params == (n,)


def test_timeout_statement_is_statement_timeout_in_ms():
    from core.mcp.sql_tools import timeout_statement

    assert timeout_statement(30) == "SET LOCAL statement_timeout = 30000"
    assert timeout_statement(0) == "SET LOCAL statement_timeout = 0"


def test_execute_query_sets_readonly_and_timeout_before_query(monkeypatch):
    from core.mcp import sql_tools

    class S:
        mcp_max_rows = 3
        mcp_query_timeout_seconds = 5

    executed: list[str] = []

    class FakeResult:
        def fetchmany(self, n):
            return []

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def execute(self, stmt):
            executed.append(str(stmt))
            return FakeResult()

        def exec_driver_sql(self, stmt, params):
            executed.append((stmt, params))
            return FakeResult()

    class FakeEngine:
        def connect(self):
            return FakeConn()

    monkeypatch.setattr(sql_tools, "get_settings", lambda: S())
    monkeypatch.setattr(sql_tools, "_get_engine", lambda: FakeEngine())
    sql_tools.execute_query("SELECT 1 -- LIMIT 99")
    assert executed == [
        "SET TRANSACTION READ ONLY",
        "SET LOCAL standard_conforming_strings = on",
        "SET LOCAL statement_timeout = 5000",
        # the cap travels as a bound parameter => extended protocol => no stacked statements
        ("SELECT * FROM (SELECT 1\n) AS _q LIMIT %s", (3,)),
    ]


def test_execute_query_rejects_write_in_cte_before_db():
    from core.mcp.sql_tools import execute_query

    with pytest.raises(SqlToolError):
        execute_query("WITH d AS (DELETE FROM contracts RETURNING 1) SELECT * FROM d")
