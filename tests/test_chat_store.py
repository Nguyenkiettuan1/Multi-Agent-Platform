"""Chat store against the real dev Postgres (platform schema).

Every user/session/feedback row is created here and removed in the fixture teardown; ids carry the
`pytest-au-` prefix so a crashed run is easy to spot. Legacy sessions are never touched.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from core.chat import store
from core.database.engines import get_platform_engine

BASE_TIME = datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc)


@pytest.fixture
def owner_id():
    """Throwaway non-login user ('system' provider needs no password hash)."""
    uid = uuid.uuid4()
    engine = get_platform_engine()
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO platform.users (id, email, auth_provider, is_active)
                VALUES (:id, :email, 'system', FALSE)
            """),
            {"id": uid, "email": f"pytest-au-{uid.hex[:8]}@test.invalid"},
        )
    try:
        yield str(uid)
    finally:
        with engine.begin() as conn:
            conn.execute(
                text("""
                    DELETE FROM platform.feedback WHERE trace_id IN (
                        SELECT m.trace_id FROM platform.chat_messages m
                        JOIN platform.chat_sessions s ON s.id = m.session_id
                        WHERE s.owner_id = :id)
                """),
                {"id": uid},
            )
            conn.execute(text("DELETE FROM platform.chat_sessions WHERE owner_id = :id"), {"id": uid})
            conn.execute(text("DELETE FROM platform.users WHERE id = :id"), {"id": uid})


@pytest.fixture
def other_owner_id():
    uid = uuid.uuid4()
    engine = get_platform_engine()
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO platform.users (id, email, auth_provider, is_active)
                VALUES (:id, :email, 'system', FALSE)
            """),
            {"id": uid, "email": f"pytest-au-{uid.hex[:8]}@test.invalid"},
        )
    try:
        yield str(uid)
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM platform.chat_sessions WHERE owner_id = :id"), {"id": uid})
            conn.execute(text("DELETE FROM platform.users WHERE id = :id"), {"id": uid})


def _tid(label: str) -> str:
    """Unique trace id: the (trace_id, role) index is global, so fixed ids could collide silently."""
    return f"pytest-au-{label}-{uuid.uuid4().hex[:8]}"


def _turn(sid: str, n: int, *, status: str = "completed") -> str:
    """Write one user+assistant turn; returns its trace id."""
    trace = f"pytest-au-{sid[:8]}-{n:02d}"
    store.append_message(session_id=sid, role="user", content=f"Câu hỏi {n:02d} có dấu", trace_id=trace)
    if status == "completed":
        store.append_message(session_id=sid, role="assistant", content=f"Trả lời {n:02d}: xong", trace_id=trace)
    else:
        store.append_message(
            session_id=sid, role="assistant", content="", status="failed", trace_id=trace, error="Boom"
        )
    return trace


def _set_updated_at(sid: str, when: datetime) -> None:
    with get_platform_engine().begin() as conn:
        conn.execute(
            text("UPDATE platform.chat_sessions SET updated_at = :w WHERE id = :id"), {"w": when, "id": sid}
        )


# --- sessions -----------------------------------------------------------------------------------


def test_create_session_returns_hex_id_and_truncates_title(owner_id):
    title = "Đ" * 250
    sid = store.create_session(owner_id, title)

    assert len(sid) == 32 and uuid.UUID(sid).hex == sid
    session = store.get_owned_session(sid, owner_id)
    assert session["title"] == "Đ" * 200
    assert session["session_id"] == sid


def test_create_session_unknown_owner_raises_integrity_error():
    with pytest.raises(IntegrityError):
        store.create_session(str(uuid.uuid4()), "x")


def test_get_owned_session_hides_other_users_and_unknown_ids(owner_id, other_owner_id):
    sid = store.create_session(owner_id, "Phiên của tôi")

    assert store.get_owned_session(sid, other_owner_id) is None
    assert store.get_owned_session("pytest-au-does-not-exist", owner_id) is None


def test_list_sessions_pages_without_gaps_and_scopes_to_owner(owner_id, other_owner_id):
    sids = [store.create_session(owner_id, f"Phiên {i}") for i in range(5)]
    store.create_session(other_owner_id, "của người khác")
    for i, sid in enumerate(sids):
        _set_updated_at(sid, BASE_TIME + timedelta(minutes=len(sids) - i))

    page1, cur1 = store.list_sessions(owner_id, limit=2, before=None)
    page2, cur2 = store.list_sessions(owner_id, limit=2, before=cur1)
    page3, cur3 = store.list_sessions(owner_id, limit=2, before=cur2)

    assert [s["session_id"] for s in page1] == [sids[0], sids[1]]
    assert [s["session_id"] for s in page2] == [sids[2], sids[3]]
    assert [s["session_id"] for s in page3] == [sids[4]]
    assert cur1 is not None and cur2 is not None and cur3 is None
    assert set(page1[0]) == {"session_id", "title", "updated_at"}


def test_list_sessions_orders_by_updated_at_not_created_at(owner_id):
    s0 = store.create_session(owner_id, "first created")
    s1 = store.create_session(owner_id, "second created")
    store.append_message(session_id=s0, role="user", content="bump", trace_id=_tid("order"))

    items, _ = store.list_sessions(owner_id, limit=10, before=None)

    assert [s["session_id"] for s in items] == [s0, s1]


def test_list_sessions_exact_page_boundary_has_no_next(owner_id):
    for i in range(2):
        store.create_session(owner_id, f"s{i}")

    items, nxt = store.list_sessions(owner_id, limit=2, before=None)

    assert len(items) == 2 and nxt is None


def test_list_sessions_tie_on_updated_at_breaks_on_id(owner_id):
    sids = [store.create_session(owner_id, f"tie {i}") for i in range(3)]
    for sid in sids:
        _set_updated_at(sid, BASE_TIME)

    seen: list[str] = []
    cursor = None
    while True:
        items, cursor = store.list_sessions(owner_id, limit=1, before=cursor)
        seen += [s["session_id"] for s in items]
        if cursor is None:
            break

    assert seen == sorted(sids, reverse=True)


@pytest.mark.parametrize("bad", ["", "not-base64!!", "bm9waXBl", "YXxi", "MjAyNi0wMS0wMVQwMDowMDowMHx4"])
def test_list_sessions_malformed_cursor_raises_value_error(owner_id, bad):
    with pytest.raises(ValueError):
        store.list_sessions(owner_id, limit=5, before=bad)


def test_list_sessions_rejects_non_positive_limit(owner_id):
    with pytest.raises(ValueError):
        store.list_sessions(owner_id, limit=0, before=None)


# --- messages -----------------------------------------------------------------------------------


def test_append_message_is_idempotent_per_trace_and_role(owner_id):
    sid = store.create_session(owner_id, "idem")
    trace = _tid("idem")
    for _ in range(2):
        store.append_message(session_id=sid, role="user", content="Xin chào", trace_id=trace)

    turns, _, _ = store.list_turns(sid, limit=10, before=None)
    assert len(turns) == 1

    with get_platform_engine().connect() as conn:
        n = conn.execute(
            text("SELECT count(*) FROM platform.chat_messages WHERE session_id = :s"), {"s": sid}
        ).scalar_one()
    assert n == 1


def test_append_message_bumps_session_updated_at(owner_id):
    sid = store.create_session(owner_id, "bump")
    _set_updated_at(sid, BASE_TIME)

    store.append_message(session_id=sid, role="user", content="hi", trace_id=_tid("bump"))

    assert store.get_owned_session(sid, owner_id)["updated_at"] > BASE_TIME.isoformat()


def test_append_message_retry_does_not_bump_updated_at(owner_id):
    sid = store.create_session(owner_id, "retry")
    trace = _tid("retry")
    store.append_message(session_id=sid, role="user", content="hi", trace_id=trace)
    _set_updated_at(sid, BASE_TIME)

    store.append_message(session_id=sid, role="user", content="hi", trace_id=trace)

    updated = store.get_owned_session(sid, owner_id)["updated_at"]
    assert datetime.fromisoformat(updated) == BASE_TIME


def test_append_message_truncates_error_to_200(owner_id):
    sid = store.create_session(owner_id, "err")
    store.append_message(
        session_id=sid, role="assistant", content="", status="failed", trace_id=_tid("err"), error="E" * 500
    )

    with get_platform_engine().connect() as conn:
        err = conn.execute(
            text("SELECT error FROM platform.chat_messages WHERE session_id = :s"), {"s": sid}
        ).scalar_one()
    assert err == "E" * 200


def test_append_message_unknown_session_raises_integrity_error():
    with pytest.raises(IntegrityError):
        store.append_message(session_id="pytest-au-nope", role="user", content="x", trace_id=_tid("nope"))


# --- load_recent_messages -----------------------------------------------------------------------


def test_load_recent_messages_returns_last_20_turns_oldest_first(owner_id):
    sid = store.create_session(owner_id, "ctx")
    for n in range(1, 26):
        _turn(sid, n)

    msgs = store.load_recent_messages(sid)

    assert len(msgs) == 40
    assert msgs[0] == {"role": "user", "content": "Câu hỏi 06 có dấu"}
    assert msgs[1] == {"role": "assistant", "content": "Trả lời 06: xong"}
    assert msgs[-1] == {"role": "assistant", "content": "Trả lời 25: xong"}
    assert [m["role"] for m in msgs] == ["user", "assistant"] * 20


def test_load_recent_messages_skips_failed_and_incomplete_turns(owner_id):
    sid = store.create_session(owner_id, "skip")
    _turn(sid, 1)
    _turn(sid, 2, status="failed")
    store.append_message(session_id=sid, role="user", content="Câu hỏi 03 có dấu", trace_id=_tid("skip"))
    _turn(sid, 4)

    msgs = store.load_recent_messages(sid)

    assert [m["content"] for m in msgs] == [
        "Câu hỏi 01 có dấu",
        "Trả lời 01: xong",
        "Câu hỏi 04 có dấu",
        "Trả lời 04: xong",
    ]


def test_load_recent_messages_rejects_non_positive_limit(owner_id):
    sid = store.create_session(owner_id, "lim")

    with pytest.raises(ValueError):
        store.load_recent_messages(sid, limit_turns=0)


def test_load_recent_messages_empty_session(owner_id):
    sid = store.create_session(owner_id, "empty")

    assert store.load_recent_messages(sid) == []


# --- list_turns ---------------------------------------------------------------------------------


def test_list_turns_pages_newest_first_but_returns_oldest_first(owner_id):
    sid = store.create_session(owner_id, "pages")
    for n in range(1, 26):
        _turn(sid, n)

    t1, more1, nb1 = store.list_turns(sid, limit=10, before=None)
    t2, more2, nb2 = store.list_turns(sid, limit=10, before=int(nb1))
    t3, more3, nb3 = store.list_turns(sid, limit=10, before=int(nb2))

    def nums(turns):
        return [int(t["user_message"].split()[2]) for t in turns]

    assert nums(t1) == list(range(16, 26)) and more1 is True
    assert nums(t2) == list(range(6, 16)) and more2 is True
    assert nums(t3) == list(range(1, 6)) and more3 is False and nb3 is None


def test_list_turns_exact_page_boundary_has_no_more(owner_id):
    sid = store.create_session(owner_id, "boundary")
    for n in range(1, 4):
        _turn(sid, n)

    turns, more, nxt = store.list_turns(sid, limit=3, before=None)

    assert len(turns) == 3 and more is False and nxt is None


def test_list_turns_shape_status_and_vietnamese(owner_id):
    sid = store.create_session(owner_id, "shape")
    ok = _turn(sid, 1)
    bad = _turn(sid, 2, status="failed")
    store.append_message(session_id=sid, role="user", content="Câu hỏi 03 có dấu", trace_id=_tid("shape"))

    turns, _, _ = store.list_turns(sid, limit=10, before=None)

    assert [t["status"] for t in turns] == ["completed", "failed", "incomplete"]
    assert turns[0]["trace_id"] == ok and turns[1]["trace_id"] == bad
    assert turns[0]["user_message"] == "Câu hỏi 01 có dấu"
    assert turns[0]["response"] == "Trả lời 01: xong"
    assert turns[1]["response"] == "" and turns[2]["response"] == ""
    assert turns[0]["session_id"] == sid
    assert turns[0]["rating"] is None and turns[0]["comment"] is None and turns[0]["eval_score"] is None
    assert isinstance(turns[0]["created_at"], str)


def test_list_turns_user_message_without_trace_id_is_incomplete(owner_id):
    sid = store.create_session(owner_id, "notrace")
    store.append_message(session_id=sid, role="user", content="không có trace")
    store.append_message(session_id=sid, role="user", content="cũng không có trace")

    turns, _, _ = store.list_turns(sid, limit=10, before=None)

    assert [t["user_message"] for t in turns] == ["không có trace", "cũng không có trace"]
    assert all(t["status"] == "incomplete" and t["trace_id"] is None for t in turns)


def test_list_turns_joins_feedback_by_trace_id(owner_id):
    sid = store.create_session(owner_id, "fb")
    rated = _turn(sid, 1)
    _turn(sid, 2)
    with get_platform_engine().begin() as conn:
        conn.execute(
            text("""
                INSERT INTO platform.feedback (trace_id, session_id, rating, comment, eval_score)
                VALUES (:t, :s, 5, 'Tốt lắm', 0.75)
            """),
            {"t": rated, "s": sid},
        )

    turns, _, _ = store.list_turns(sid, limit=10, before=None)

    assert len(turns) == 2
    assert (turns[0]["rating"], turns[0]["comment"], turns[0]["eval_score"]) == (5, "Tốt lắm", 0.75)
    assert turns[1]["rating"] is None


def test_list_turns_empty_session(owner_id):
    sid = store.create_session(owner_id, "none")

    assert store.list_turns(sid, limit=5, before=None) == ([], False, None)


# --- trace_owner --------------------------------------------------------------------------------


def test_trace_owner_returns_owner_or_none(owner_id):
    sid = store.create_session(owner_id, "own")
    trace = _turn(sid, 1)

    assert store.trace_owner(trace) == owner_id
    assert store.trace_owner("pytest-au-unknown-trace") is None
