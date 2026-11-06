"""Chat history: latest-N for the LLM and keyset pagination, against the real dev Postgres.

Rows are inserted straight through the platform engine (not save_chat_trace) so created_at is
controlled and strictly increasing.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from core.database.engines import get_platform_engine
from core.intelligence.feedback_store import list_session_traces, load_session_history

BASE_TIME = datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc)


def _insert(conn, sid: str, label: str, created_at: datetime) -> None:
    conn.execute(
        text("""
            INSERT INTO platform.feedback (trace_id, session_id, user_message, response, created_at)
            VALUES (:trace_id, :sid, :user_message, :response, :created_at)
        """),
        {
            "trace_id": f"{sid}-{label}-{uuid.uuid4().hex[:6]}",
            "sid": sid,
            "user_message": f"Câu hỏi {label} về tiếng Việt có dấu",
            "response": f"Trả lời {label}: đã xử lý xong",
            "created_at": created_at,
        },
    )


def _cleanup(sid: str) -> None:
    with get_platform_engine().connect() as conn:
        conn.execute(text("DELETE FROM platform.feedback WHERE session_id = :sid"), {"sid": sid})
        conn.commit()


@pytest.fixture
def session_id():
    sid = f"pytest-au-{uuid.uuid4().hex[:8]}"
    try:
        yield sid
    finally:
        _cleanup(sid)


@pytest.fixture
def session_25(session_id):
    with get_platform_engine().connect() as conn:
        for n in range(1, 26):
            _insert(conn, session_id, f"{n:02d}", BASE_TIME + timedelta(minutes=n))
        conn.commit()
    return session_id


def _labels(turns: list[dict]) -> list[int]:
    return [int(t["user_message"].split()[2]) for t in turns]


def test_load_session_history_returns_newest_turns_oldest_first(session_25):
    messages = load_session_history(session_25, limit=20)

    assert len(messages) == 40
    assert [m["role"] for m in messages[:2]] == ["user", "assistant"]
    assert messages[0]["content"] == "Câu hỏi 06 về tiếng Việt có dấu"
    assert messages[1]["content"] == "Trả lời 06: đã xử lý xong"
    assert messages[-2]["content"] == "Câu hỏi 25 về tiếng Việt có dấu"
    assert messages[-1]["content"] == "Trả lời 25: đã xử lý xong"


def test_same_created_at_is_ordered_by_id(session_id):
    with get_platform_engine().connect() as conn:
        _insert(conn, session_id, "01", BASE_TIME)
        _insert(conn, session_id, "02", BASE_TIME)
        _insert(conn, session_id, "03", BASE_TIME)
        conn.commit()

    page = list_session_traces(session_id, limit=10)
    assert _labels(page["turns"]) == [1, 2, 3]

    newest_two = load_session_history(session_id, limit=2)
    assert [m["content"] for m in newest_two if m["role"] == "user"] == [
        "Câu hỏi 02 về tiếng Việt có dấu",
        "Câu hỏi 03 về tiếng Việt có dấu",
    ]


def test_pagination_walks_back_through_the_session(session_25):
    page1 = list_session_traces(session_25, limit=10)
    assert _labels(page1["turns"]) == list(range(16, 26))
    assert page1["has_more"] is True
    assert isinstance(page1["next_before"], str)
    assert isinstance(page1["turns"][0]["created_at"], str)

    page2 = list_session_traces(session_25, limit=10, before_id=int(page1["next_before"]))
    assert _labels(page2["turns"]) == list(range(6, 16))
    assert page2["has_more"] is True

    page3 = list_session_traces(session_25, limit=10, before_id=int(page2["next_before"]))
    assert _labels(page3["turns"]) == list(range(1, 6))
    assert page3["has_more"] is False
    assert page3["next_before"] is None


def test_exact_fit_page_has_no_more(session_25):
    page = list_session_traces(session_25, limit=25)
    assert len(page["turns"]) == 25
    assert page["has_more"] is False
    assert page["next_before"] is None


def test_unknown_session_is_empty(session_id):
    assert list_session_traces(session_id) == {"turns": [], "has_more": False, "next_before": None}


@pytest.fixture
def client(user_client):
    """Chat routes need a signed-in user since MA-AU-T7."""
    return user_client


URL = "/api/v1/chat/history"


def test_api_rejects_malformed_before(client, session_id):
    assert client.get(URL, params={"session_id": session_id, "before": "abc"}).status_code == 422


def test_api_rejects_limit_below_one(client, session_id):
    assert client.get(URL, params={"session_id": session_id, "limit": 0}).status_code == 422


def test_api_clamps_limit_to_100(client, session_id):
    with get_platform_engine().connect() as conn:
        for n in range(1, 106):
            _insert(conn, session_id, f"{n:03d}", BASE_TIME + timedelta(minutes=n))
        conn.commit()

    body = client.get(URL, params={"session_id": session_id, "limit": 500}).json()
    assert len(body["turns"]) == 100
    assert body["count"] == 100
    assert body["has_more"] is True


def test_api_page_shape_and_cursor(client, session_25):
    first = client.get(URL, params={"session_id": session_25, "limit": 10})
    assert first.status_code == 200
    body = first.json()
    assert set(body) == {"session_id", "turns", "count", "has_more", "next_before"}
    assert body["session_id"] == session_25
    assert body["count"] == 10
    assert _labels(body["turns"]) == list(range(16, 26))
    assert set(body["turns"][0]) >= {
        "trace_id", "session_id", "user_message", "response", "rating", "comment", "eval_score", "created_at",
    }

    second = client.get(
        URL, params={"session_id": session_25, "limit": 10, "before": body["next_before"]}
    ).json()
    assert _labels(second["turns"]) == list(range(6, 16))


def test_api_unknown_session_returns_empty_turns(client, session_id):
    body = client.get(URL, params={"session_id": session_id}).json()
    assert body == {
        "session_id": session_id, "turns": [], "count": 0, "has_more": False, "next_before": None,
    }


@pytest.mark.parametrize("cursor", ["0", "-5", "99999999999999999999", "9223372036854775808"])
def test_api_rejects_out_of_range_before(client, session_id, cursor):
    assert client.get(URL, params={"session_id": session_id, "before": cursor}).status_code == 422


def _walk_pages(sid: str, limit: int) -> list[list[int]]:
    pages, before = [], None
    while True:
        page = list_session_traces(sid, limit=limit, before_id=before)
        pages.append(_labels(page["turns"]))
        if not page["has_more"]:
            return pages
        before = int(page["next_before"])


def test_pagination_keys_on_id_when_created_at_disagrees(session_id):
    # Insert order (id) is T1, T3, T2 but created_at order is T1 < T2 < T3: a created_at sort
    # with an id cursor would skip T2.
    with get_platform_engine().connect() as conn:
        _insert(conn, session_id, "01", BASE_TIME + timedelta(minutes=1))
        _insert(conn, session_id, "03", BASE_TIME + timedelta(minutes=3))
        _insert(conn, session_id, "02", BASE_TIME + timedelta(minutes=2))
        conn.commit()

    assert _walk_pages(session_id, 1) == [[2], [3], [1]]
    assert _labels(list_session_traces(session_id, limit=10)["turns"]) == [1, 3, 2]
    users = [m["content"] for m in load_session_history(session_id, limit=2) if m["role"] == "user"]
    assert users == ["Câu hỏi 03 về tiếng Việt có dấu", "Câu hỏi 02 về tiếng Việt có dấu"]


def test_null_created_at_is_not_lost_or_floated_to_top(session_id):
    with get_platform_engine().connect() as conn:
        _insert(conn, session_id, "01", BASE_TIME)
        _insert(conn, session_id, "02", None)
        _insert(conn, session_id, "03", BASE_TIME + timedelta(minutes=1))
        conn.commit()

    assert _walk_pages(session_id, 1) == [[3], [2], [1]]
    assert _labels(list_session_traces(session_id, limit=10)["turns"]) == [1, 2, 3]


def test_api_history_requires_authentication(anon_client, session_id):
    assert anon_client.get(URL, params={"session_id": session_id}).status_code == 401
