"""Natural language → SQL heuristic for db-worker (Phase 1).

Phase 2: LLM generates SQL with schema context from list_tables/describe_table.
"""

from __future__ import annotations

import re
import unicodedata

from core.mcp.sql_tools import SqlToolError


def _normalize(msg: str) -> str:
    # NFKD does not decompose "đ", so map it explicitly (same as triage._normalize).
    lower = msg.lower().replace("đ", "d")
    nfkd = unicodedata.normalize("NFKD", lower)
    stripped = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", stripped).strip()


_SUPPORTED_HINT = (
    "Hiện hỗ trợ: đếm hợp đồng (ví dụ \"Có bao nhiêu hợp đồng?\"), "
    "đếm hợp đồng active, liệt kê toàn bộ hợp đồng (ví dụ \"Liệt kê hợp đồng\"), "
    "liệt kê hợp đồng ABC, đếm số khách hàng."
)
_UNSUPPORTED_MESSAGE = f"Câu hỏi này chưa được hỗ trợ bởi database agent. {_SUPPORTED_HINT}"
_MIXED_COUNT_MESSAGE = (
    "Câu hỏi kết hợp khách hàng và hợp đồng chưa được hỗ trợ bởi database agent. "
    f"{_SUPPORTED_HINT}"
)
_FILTERED_COUNT_MESSAGE = (
    "Đếm hợp đồng theo bộ lọc ABC chưa được hỗ trợ bởi database agent. "
    f"{_SUPPORTED_HINT}"
)


def build_sql(question: str) -> str:
    """Build a safe read-only SELECT from natural language question.

    Raises SqlToolError for questions matching no known pattern: returning a
    default listing would show the user unrelated data as if it were the answer.
    """
    msg = _normalize(question)

    if _is_count_query(msg):
        is_customer = _has_word(msg, "khach hang|customers?")
        mentions_contract = _has_word(msg, "hop dong|contracts?")
        # The count branches cannot express a relation between the two nouns
        # or an ABC filter; any answer would silently be the wrong number.
        if is_customer and mentions_contract:
            raise SqlToolError(_MIXED_COUNT_MESSAGE)
        if _has_word(msg, "abc"):
            raise SqlToolError(_FILTERED_COUNT_MESSAGE)
        # Customer-only counts must win over the contract count, otherwise
        # "how many customers" is answered with the contract count.
        if is_customer:
            return "SELECT COUNT(DISTINCT client_id) AS total FROM contracts"
        # Only a contract count is implemented; counting anything else
        # ("nhan vien", "invoices", no object) must not yield a contract total.
        if not mentions_contract:
            raise SqlToolError(_UNSUPPORTED_MESSAGE)
        if _has_word(msg, "active"):
            return "SELECT COUNT(*) AS total FROM contracts WHERE status = 'active'"
        return "SELECT COUNT(*) AS total FROM contracts"

    if _is_plain_listing(msg):
        return "SELECT code, title, status, value_vnd FROM contracts LIMIT 10"

    if _has_word(msg, "abc"):
        return (
            "SELECT code, title, status, value_vnd FROM contracts "
            "WHERE title ILIKE '%ABC%' LIMIT 10"
        )

    if _has_word(msg, "khach hang") or _has_word(msg, "customers?"):
        return "SELECT COUNT(DISTINCT client_id) AS total FROM contracts"

    raise SqlToolError(_UNSUPPORTED_MESSAGE)


def _has_word(msg: str, pattern: str) -> bool:
    # Word boundaries so "abc" does not match "abcxyz" or "active" match "inactive".
    return bool(re.search(rf"\b(?:{pattern})\b", msg))


def _is_count_query(msg: str) -> bool:
    return _has_word(msg, "bao nhieu|dem|count|co bao nhieu|how many")


def _is_plain_listing(msg: str) -> bool:
    # Anchored on purpose: any qualifier (customer, year, status...) must fail
    # rather than silently return unfiltered rows.
    return bool(
        re.match(
            r"^(?:(liet ke|danh sach)( cac| tat ca| toan bo)? hop dong( trong he thong)?"
            r"|list( all)? contracts)[?.!\s]*$",
            msg,
        )
    )
