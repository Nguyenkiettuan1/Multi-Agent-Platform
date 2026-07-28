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
