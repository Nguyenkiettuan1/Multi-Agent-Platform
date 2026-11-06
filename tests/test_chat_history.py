"""GET /api/v1/chat/history: latest-first keyset pagination over chat_messages, owner-only.

Turns are written through the chat store into a session owned by the test user; deleting the
session cascades to its messages. Store-level pagination edge cases live in test_chat_store.py.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from core.chat import store
from core.database.engines import get_platform_engine

URL = "/api/v1/chat/history"


@pytest.fixture
def client(user_client):
    """Chat routes need a signed-in user since MA-AU-T7."""
    return user_client


@pytest.fixture
def session_id(client):
    sid = store.create_session(client.auth_user.id, "pytest-au history")
    try:
        yield sid
    finally:
        with get_platform_engine().begin() as conn:
            conn.execute(text("DELETE FROM platform.chat_sessions WHERE id = :sid"), {"sid": sid})


def _seed(sid: str, count: int) -> None:
    for n in range(1, count + 1):
        trace = f"pytest-au-{sid[:8]}-{n:03d}"
        store.append_message(
            session_id=sid, role="user", content=f"Câu hỏi {n:03d} về tiếng Việt có dấu", trace_id=trace
        )
        store.append_message(
            session_id=sid, role="assistant", content=f"Trả lời {n:03d}: đã xử lý xong", trace_id=trace
        )


def _labels(turns: list[dict]) -> list[int]:
    return [int(t["user_message"].split()[2]) for t in turns]


def test_api_rejects_malformed_before(client, session_id):
    assert client.get(URL, params={"session_id": session_id, "before": "abc"}).status_code == 422


def test_api_rejects_limit_below_one(client, session_id):
    assert client.get(URL, params={"session_id": session_id, "limit": 0}).status_code == 422


def test_api_clamps_limit_to_100(client, session_id):
    _seed(session_id, 105)

    body = client.get(URL, params={"session_id": session_id, "limit": 500}).json()

    assert len(body["turns"]) == 100
    assert body["count"] == 100
    assert body["has_more"] is True


def test_api_page_shape_and_cursor_walk(client, session_id):
    _seed(session_id, 25)

    first = client.get(URL, params={"session_id": session_id, "limit": 10})
    assert first.status_code == 200
    body = first.json()
    assert set(body) == {"session_id", "turns", "count", "has_more", "next_before"}
    assert body["session_id"] == session_id
    assert body["count"] == 10 and body["has_more"] is True
    assert _labels(body["turns"]) == list(range(16, 26))
    assert set(body["turns"][0]) >= {
        "trace_id", "session_id", "user_message", "response", "rating", "comment", "eval_score",
        "created_at", "status",
    }
    assert body["turns"][-1]["response"] == "Trả lời 025: đã xử lý xong"

    second = client.get(
        URL, params={"session_id": session_id, "limit": 10, "before": body["next_before"]}
    ).json()
    assert _labels(second["turns"]) == list(range(6, 16))
    assert second["has_more"] is True

    third = client.get(
        URL, params={"session_id": session_id, "limit": 10, "before": second["next_before"]}
    ).json()
    assert _labels(third["turns"]) == list(range(1, 6))
    assert third["has_more"] is False and third["next_before"] is None


def test_api_exact_fit_page_has_no_more(client, session_id):
    _seed(session_id, 25)

    body = client.get(URL, params={"session_id": session_id, "limit": 25}).json()

    assert body["count"] == 25
    assert body["has_more"] is False and body["next_before"] is None


def test_api_empty_owned_session_has_no_turns(client, session_id):
    body = client.get(URL, params={"session_id": session_id}).json()
    assert body == {
        "session_id": session_id, "turns": [], "count": 0, "has_more": False, "next_before": None,
    }


def test_api_unknown_session_is_404(client):
    r = client.get(URL, params={"session_id": "pytest-au-no-such-session"})
    assert r.status_code == 404 and r.json() == {"detail": "Session not found"}


@pytest.mark.parametrize("cursor", ["0", "-5", "99999999999999999999", "9223372036854775808"])
def test_api_rejects_out_of_range_before(client, session_id, cursor):
    assert client.get(URL, params={"session_id": session_id, "before": cursor}).status_code == 422


def test_api_history_requires_authentication(anon_client, session_id):
    assert anon_client.get(URL, params={"session_id": session_id}).status_code == 401
