"""Tests for the heuristic NL -> SQL builder (word boundaries + explicit failure)."""

from __future__ import annotations

import pytest

from core.mcp.sql_query_builder import build_sql
from core.mcp.sql_tools import SqlToolError

COUNT_ALL = "SELECT COUNT(*) AS total FROM contracts"
COUNT_ACTIVE = "SELECT COUNT(*) AS total FROM contracts WHERE status = 'active'"
ABC_LIST = (
    "SELECT code, title, status, value_vnd FROM contracts "
    "WHERE title ILIKE '%ABC%' LIMIT 10"
)
LIST_ALL = "SELECT code, title, status, value_vnd FROM contracts LIMIT 10"
CUSTOMERS = "SELECT COUNT(DISTINCT client_id) AS total FROM contracts"


@pytest.mark.parametrize(
    "question, expected",
    [
        ("Co bao nhieu hop dong?", COUNT_ALL),
        ("Có bao nhiêu hợp đồng active?", COUNT_ACTIVE),
        ("Count active contracts", COUNT_ACTIVE),
        ("Liet ke hop dong ABC Corp", ABC_LIST),
        ("Liệt kê hợp đồng ABC", ABC_LIST),
        ("Số khách hàng", CUSTOMERS),
    ],
)
def test_supported_patterns_unchanged(question, expected):
    assert build_sql(question) == expected


@pytest.mark.parametrize(
    "question",
    [
        "Co bao nhieu khach hang?",
        "Có bao nhiêu khách hàng?",
        "How many customers?",
        "How many customers",
        "Count customers",
        "Đếm khách hàng",
    ],
)
def test_count_customers_returns_customer_count(question):
    assert build_sql(question) == CUSTOMERS


@pytest.mark.parametrize(
    "question",
    [
        "Có bao nhiêu hợp đồng của khách hàng ABC?",
        "How many contracts per customer?",
        "How many customers have contracts?",
        "Đếm khách hàng có hợp đồng",
        "How many customers have active contracts?",
    ],
)
def test_count_mixing_customers_and_contracts_rejected(question):
    with pytest.raises(SqlToolError) as exc:
        build_sql(question)
    assert "khách hàng và hợp đồng" in str(exc.value)
    assert "Hiện hỗ trợ" in str(exc.value)


@pytest.mark.parametrize(
    "question",
    ["Có bao nhiêu hợp đồng ABC?", "Count ABC contracts", "Đếm hợp đồng abc"],
)
def test_count_with_abc_filter_rejected(question):
    # The count branch cannot apply the ABC filter; the total would be wrong.
    with pytest.raises(SqlToolError):
        build_sql(question)


@pytest.mark.parametrize(
    "question",
    [
        "How many employees?",
        "Đếm nhân viên",
        "How many clients?",
        "đếm số lượng đơn hàng",
        "How many invoices are active?",
        "How many?",
        "dem khach",
    ],
)
def test_count_of_unknown_object_rejected(question):
    with pytest.raises(SqlToolError) as exc:
        build_sql(question)
    assert "chưa được hỗ trợ" in str(exc.value)
    assert "Hiện hỗ trợ" in str(exc.value)


@pytest.mark.parametrize(
    "question, expected",
    [
        # Phrasings taken from eval/cases/basic.yaml.
        ("Co bao nhieu hop dong dang active?", COUNT_ACTIVE),
        ("Co bao nhieu khach hang trong he thong?", CUSTOMERS),
        ("Co bao nhieu hop dong active?", COUNT_ACTIVE),
        ("Co bao nhieu hop dong trong he thong?", COUNT_ALL),
        ("Count active contracts", COUNT_ACTIVE),
    ],
)
def test_eval_case_phrasings(question, expected):
    assert build_sql(question) == expected


def test_non_count_abc_still_lists():
    assert build_sql("Hợp đồng ABC") == ABC_LIST


@pytest.mark.parametrize(
    "question", ["list contracts", "List all contracts", "list all contracts."]
)
def test_english_plain_listing(question):
    assert build_sql(question) == LIST_ALL


def test_whitespace_runs_are_collapsed():
    assert build_sql("Liệt   kê  hợp   đồng") == LIST_ALL
    assert build_sql("Co  bao   nhieu hop dong") == COUNT_ALL


@pytest.mark.parametrize(
    "question, expected",
    [
        ("Đếm hợp đồng", COUNT_ALL),
        ("đếm hợp đồng", COUNT_ALL),
        ("Đếm hợp đồng active", COUNT_ACTIVE),
        ("Dem hop dong", COUNT_ALL),
        ("How many contracts?", COUNT_ALL),
        ("How many active contracts?", COUNT_ACTIVE),
    ],
)
def test_count_with_d_stroke_and_english(question, expected):
    assert build_sql(question) == expected


@pytest.mark.parametrize(
    "question",
    [
        "Liệt kê hợp đồng",
        "Danh sách hợp đồng",
        "Liet ke cac hop dong",
        "Danh sách tất cả hợp đồng?",
        "Liệt kê toàn bộ hợp đồng trong hệ thống.",
    ],
)
def test_plain_contract_listing_supported(question):
    assert build_sql(question) == LIST_ALL


@pytest.mark.parametrize(
    "question",
    [
        "Danh sách hợp đồng của khách A",
        "Liệt kê hợp đồng ký năm 2024",
        "Liet ke hop dong da het han",
        "Hãy liệt kê hợp đồng",
    ],
)
def test_qualified_listing_still_rejected(question):
    with pytest.raises(SqlToolError):
        build_sql(question)


@pytest.mark.parametrize("question", ["Liet ke abcxyz", "xabc contracts", "Danh sach abc123"])
def test_abc_requires_word_boundary(question):
    with pytest.raises(SqlToolError):
        build_sql(question)


def test_customer_requires_word_boundary():
    # "customers" is a plural of a known word, but "customerx" is not.
    with pytest.raises(SqlToolError):
        build_sql("Show customerx details")


def test_inactive_is_not_active_count():
    # "inactive" must not be read as the word "active".
    assert build_sql("Count inactive contracts") == COUNT_ALL


@pytest.mark.parametrize(
    "question",
    ["Thoi tiet hom nay the nao", "Hợp đồng là gì?", "", "   "],
)
def test_unknown_question_fails_explicitly(question):
    with pytest.raises(SqlToolError) as exc:
        build_sql(question)
    msg = str(exc.value)
    assert "chua duoc ho tro" in msg or "chưa được hỗ trợ" in msg
    # Tells the user what is supported.
    assert "ABC" in msg
    assert "active" in msg
