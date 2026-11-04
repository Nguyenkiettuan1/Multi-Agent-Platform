"""Natural language → SQL heuristic for db-worker (Phase 1).

Phase 2: LLM generates SQL with schema context from list_tables/describe_table.
"""

from __future__ import annotations

import re
import unicodedata


def _normalize(msg: str) -> str:
    lower = msg.lower().strip()
    nfkd = unicodedata.normalize("NFKD", lower)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def build_sql(question: str) -> str:
    """Build a safe read-only SELECT from natural language question."""
    msg = _normalize(question)

    if _is_count_query(msg):
        if "active" in msg:
            return "SELECT COUNT(*) AS total FROM contracts WHERE status = 'active'"
        return "SELECT COUNT(*) AS total FROM contracts"

    if "abc" in msg or "abc corp" in msg:
        return (
            "SELECT code, title, status, value_vnd FROM contracts "
            "WHERE title ILIKE '%ABC%' LIMIT 10"
        )

    if "khach hang" in msg or "customer" in msg:
        return "SELECT COUNT(DISTINCT client_id) AS total FROM contracts"

    return "SELECT code, title, status, value_vnd FROM contracts LIMIT 10"


def _is_count_query(msg: str) -> bool:
    return bool(re.search(r"\b(bao nhieu|dem|count|co bao nhieu)\b", msg))
