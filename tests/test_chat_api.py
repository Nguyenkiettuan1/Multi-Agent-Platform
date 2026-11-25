"""Chat routes end to end: ownership, persistence of every turn (failed ones included), LLM context.

The graph is a fake (no LLM). Users, sessions and the feedback/audit rows the runner writes are real
rows in the dev platform DB and are removed in the fixture teardown.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import uuid

import pytest
from conftest import _logged_in_client
from sqlalchemy import text

from core.chat import store
from core.database.engines import get_platform_engine
from core.security.users import LEGACY_USER_ID, SERVICE_USER_ID
from workflows import runner

CHAT = "/api/v1/chat"
STREAM = "/api/v1/chat/stream"
HISTORY = "/api/v1/chat/history"
SESSIONS = "/api/v1/chat/sessions"
FEEDBACK = "/api/v1/feedback"

# Marks sessions created through the service (API key) user, who is shared and never deleted.
PREFIX = "pytest-au-"
SECRET = "boom-internal-detail-do-not-leak"


class FakeGraph:
    """Stands in for the compiled LangGraph: records every initial state it receives."""

    def __init__(self, answer: str = "Đây là câu trả lời có dấu", fail: bool = False):
        self.answer = answer
        self.fail = fail
        self.calls: list[dict] = []
        self.on_run = None  # called inside the run, e.g. to look at the DB while the graph executes

    async def ainvoke(self, initial, config):
        self.calls.append(initial)
        if self.on_run:
            self.on_run()
        if self.fail:
            raise RuntimeError(SECRET)
        return {"final_response": self.answer}

    async def astream(self, initial, config, stream_mode="updates"):
        self.calls.append(initial)
        if self.on_run:
            self.on_run()
        if self.fail:
            raise RuntimeError(SECRET)
        yield {"synthesize": {"final_response": self.answer}}

    async def aget_state(self, config):
        return None


@pytest.fixture
def graph(monkeypatch):
    fake = FakeGraph()
    monkeypatch.setattr(runner, "_default_graph", fake)
    return fake


@pytest.fixture
def failing_graph(monkeypatch):
    fake = FakeGraph(fail=True)
    monkeypatch.setattr(runner, "_default_graph", fake)
    return fake


@pytest.fixture(autouse=True)
def cleanup_chat_rows(auth_env):
    """Runs before the users are purged (chat_sessions.owner_id has no cascade)."""
    try:
        yield
    finally:
        with get_platform_engine().begin() as conn:
            owned = """
                SELECT s.id FROM platform.chat_sessions s
                WHERE s.owner_id IN (SELECT id FROM platform.users WHERE email LIKE :mail)
                   OR (s.owner_id IN (:service, :legacy) AND s.title LIKE :prefix)
            """
            params = {
                "mail": f"{PREFIX}%@example.test",
                "service": SERVICE_USER_ID,
                "legacy": LEGACY_USER_ID,
                "prefix": f"{PREFIX}%",
            }
            # Also by message prefix, so a run that died early (or a mutant) leaves nothing behind.
            traces = """
                SELECT trace_id FROM platform.chat_messages WHERE role = 'user' AND content LIKE :prefix
                UNION SELECT trace_id FROM platform.feedback WHERE user_message LIKE :prefix
            """
            conn.execute(text(f"DELETE FROM platform.audit_log WHERE trace_id IN ({traces})"), params)
            conn.execute(text("DELETE FROM platform.feedback WHERE user_message LIKE :prefix"), params)
            conn.execute(text(f"DELETE FROM platform.feedback WHERE session_id IN ({owned})"), params)
            conn.execute(text(f"DELETE FROM platform.audit_log WHERE replace(session_id::text, '-', '') IN ({owned})"), params)
            conn.execute(text(f"DELETE FROM platform.chat_sessions WHERE id IN ({owned})"), params)


def _msg(label: str) -> str:
    return f"{PREFIX}{label} xin chào, tiếng Việt có dấu"


def _sse_events(body: str) -> list[tuple[str, dict]]:
    events = []
    for block in body.strip().split("\n\n"):
        lines = block.split("\n")
        name = lines[0].removeprefix("event: ")
        events.append((name, json.loads(lines[1].removeprefix("data: "))))
    return events


def _count_messages(session_id: str) -> int:
    with get_platform_engine().connect() as conn:
        return conn.execute(
            text("SELECT count(*) FROM platform.chat_messages WHERE session_id = :s"), {"s": session_id}
        ).scalar()


def _seed_turns(session_id: str, count: int) -> None:
    for n in range(1, count + 1):
        trace = f"{PREFIX}{session_id[:8]}-{n:02d}"
        store.append_message(session_id=session_id, role="user", content=f"Câu hỏi {n:02d}", trace_id=trace)
        store.append_message(session_id=session_id, role="assistant", content=f"Trả lời {n:02d}", trace_id=trace)


def test_chat_without_session_creates_session_owned_by_caller(user_client, graph):
    message = _msg("new")
    body = user_client.post(CHAT, json={"message": message}).json()

    sid = body["session_id"]
    assert body["response"] == graph.answer
    owned = store.get_owned_session(sid, user_client.auth_user.id)
    assert owned is not None and owned["title"] == message
    items = user_client.get(SESSIONS).json()["items"]
    assert [i["session_id"] for i in items] == [sid]


def test_follow_up_receives_only_latest_turns_without_current_question(user_client, graph):
    sid = store.create_session(user_client.auth_user.id, _msg("ctx"))
    _seed_turns(sid, 25)

    r = user_client.post(CHAT, json={"message": _msg("now"), "session_id": sid})

    assert r.status_code == 200
    history = graph.calls[0]["chat_history"]
    assert len(history) == 40
    assert history[0] == {"role": "user", "content": "Câu hỏi 06"}
    assert history[-1] == {"role": "assistant", "content": "Trả lời 25"}
    assert all(_msg("now") != m["content"] for m in history)


def test_two_consecutive_chats_chain_context(user_client, graph):
    first = user_client.post(CHAT, json={"message": _msg("one")}).json()
    user_client.post(CHAT, json={"message": _msg("two"), "session_id": first["session_id"]})

    assert graph.calls[0]["chat_history"] == []
    assert graph.calls[1]["chat_history"] == [
        {"role": "user", "content": _msg("one")},
        {"role": "assistant", "content": graph.answer},
    ]


def test_completed_turn_is_in_history(user_client, graph):
    sid = user_client.post(CHAT, json={"message": _msg("ok")}).json()["session_id"]

    body = user_client.get(HISTORY, params={"session_id": sid}).json()

    assert [(t["user_message"], t["response"], t["status"]) for t in body["turns"]] == [
        (_msg("ok"), graph.answer, "completed")
    ]


def test_other_user_cannot_chat_in_a_foreign_session(user_client, make_user, graph):
    sid = store.create_session(user_client.auth_user.id, _msg("a"))
    intruder = _logged_in_client(make_user("user"))

    r = intruder.post(CHAT, json={"message": _msg("intrude"), "session_id": sid})

    assert r.status_code == 404 and r.json() == {"detail": "Session not found"}
    assert _count_messages(sid) == 0
    assert graph.calls == []


def test_foreign_session_on_stream_is_http_404_not_sse(user_client, make_user, graph):
    sid = store.create_session(user_client.auth_user.id, _msg("a"))
    intruder = _logged_in_client(make_user("user"))

    r = intruder.post(STREAM, json={"message": _msg("intrude"), "session_id": sid})

    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/json")
    assert r.json() == {"detail": "Session not found"}
    assert _count_messages(sid) == 0


def test_unknown_session_is_404(user_client, graph):
    r = user_client.post(CHAT, json={"message": _msg("x"), "session_id": uuid.uuid4().hex})
    assert r.status_code == 404 and r.json() == {"detail": "Session not found"}


def test_other_user_cannot_read_history_or_see_session(user_client, make_user, graph):
    sid = user_client.post(CHAT, json={"message": _msg("secret")}).json()["session_id"]
    other = _logged_in_client(make_user("user"))

    r = other.get(HISTORY, params={"session_id": sid})

    assert r.status_code == 404 and r.json() == {"detail": "Session not found"}
    assert other.get(SESSIONS).json() == {"items": [], "count": 0, "has_more": False, "next_before": None}


def test_legacy_session_is_404_for_regular_user(user_client, graph):
    sid = store.create_session(LEGACY_USER_ID, _msg("legacy"))

    assert user_client.get(HISTORY, params={"session_id": sid}).status_code == 404
    assert user_client.post(CHAT, json={"message": _msg("x"), "session_id": sid}).status_code == 404


def test_other_user_cannot_rate_a_foreign_trace(user_client, make_user, graph):
    body = user_client.post(CHAT, json={"message": _msg("rate")}).json()
    other = _logged_in_client(make_user("user"))

    foreign = other.post(FEEDBACK, json={"trace_id": body["trace_id"], "rating": 2})
    missing = other.post(FEEDBACK, json={"trace_id": "no-such-trace", "rating": 2})

    assert foreign.status_code == 404 and missing.status_code == 404
    assert foreign.json()["detail"] == f"trace_id not found: {body['trace_id']}"
    assert foreign.json()["detail"].replace(body["trace_id"], "X") == missing.json()["detail"].replace("no-such-trace", "X")

    own = user_client.post(FEEDBACK, json={"trace_id": body["trace_id"], "rating": 2})
    assert own.status_code == 200


def test_failed_chat_is_persisted_and_error_is_generic(user_client, failing_graph):
    r = user_client.post(CHAT, json={"message": _msg("fail")})

    assert r.status_code == 500
    assert SECRET not in r.text
    sid = r.json()["session_id"]
    assert r.json()["detail"]
    turns = user_client.get(HISTORY, params={"session_id": sid}).json()["turns"]
    assert [(t["user_message"], t["response"], t["status"]) for t in turns] == [(_msg("fail"), "", "failed")]


def test_failed_chat_in_existing_session_carries_the_same_session_id_as_sse(user_client, failing_graph):
    sid = store.create_session(user_client.auth_user.id, _msg("exists"))

    r = user_client.post(CHAT, json={"message": _msg("fail"), "session_id": sid})
    streamed = user_client.post(STREAM, json={"message": _msg("fail2"), "session_id": sid})

    assert r.status_code == 500 and SECRET not in r.text
    assert r.json()["session_id"] == sid
    errors = [d for name, d in _sse_events(streamed.text) if name == "error"]
    assert errors[0]["session_id"] == sid


def test_failed_turn_is_excluded_from_next_llm_context(user_client, graph):
    sid = user_client.post(CHAT, json={"message": _msg("good")}).json()["session_id"]
    graph.fail = True
    assert user_client.post(CHAT, json={"message": _msg("bad"), "session_id": sid}).status_code == 500
    graph.fail = False

    user_client.post(CHAT, json={"message": _msg("next"), "session_id": sid})

    assert [m["content"] for m in graph.calls[-1]["chat_history"]] == [_msg("good"), graph.answer]


def test_stream_success_emits_complete_and_persists(user_client, graph):
    r = user_client.post(STREAM, json={"message": _msg("s")})

    events = _sse_events(r.text)
    complete = [d for name, d in events if name == "complete"][0]
    turns = user_client.get(HISTORY, params={"session_id": complete["session_id"]}).json()["turns"]
    assert [(t["response"], t["status"]) for t in turns] == [(graph.answer, "completed")]


def test_stream_error_carries_session_id_is_generic_and_persists_failed_turn(user_client, failing_graph):
    r = user_client.post(STREAM, json={"message": _msg("sfail")})

    assert r.status_code == 200
    assert SECRET not in r.text
    errors = [d for name, d in _sse_events(r.text) if name == "error"]
    assert len(errors) == 1 and errors[0]["message"]
    sid = errors[0]["session_id"]
    assert store.get_owned_session(sid, user_client.auth_user.id) is not None
    turns = user_client.get(HISTORY, params={"session_id": sid}).json()["turns"]
    assert [(t["user_message"], t["status"]) for t in turns] == [(_msg("sfail"), "failed")]


def test_retry_after_failure_reuses_the_created_session(user_client, graph):
    graph.fail = True
    sid = user_client.post(CHAT, json={"message": _msg("retry")}).json()["session_id"]
    graph.fail = False

    ok = user_client.post(CHAT, json={"message": _msg("retry"), "session_id": sid}).json()

    assert ok["session_id"] == sid
    assert len(user_client.get(SESSIONS).json()["items"]) == 1
    statuses = [t["status"] for t in user_client.get(HISTORY, params={"session_id": sid}).json()["turns"]]
    assert statuses == ["failed", "completed"]


def test_user_id_in_body_is_ignored(user_client, graph):
    body = user_client.post(CHAT, json={"message": _msg("h"), "user_id": "hacker"}).json()

    assert graph.calls[0]["user_id"] == user_client.auth_user.id
    assert store.get_owned_session(body["session_id"], user_client.auth_user.id) is not None


def test_api_key_chat_belongs_to_service_user(api_key_client, graph):
    body = api_key_client.post(CHAT, json={"message": _msg("svc")}).json()

    assert store.get_owned_session(body["session_id"], SERVICE_USER_ID) is not None
    assert graph.calls[0]["user_id"] == SERVICE_USER_ID


def test_sessions_pagination_and_validation(user_client, graph):
    created = [user_client.post(CHAT, json={"message": _msg(f"p{n}")}).json()["session_id"] for n in range(3)]

    first = user_client.get(SESSIONS, params={"limit": 2}).json()
    assert [i["session_id"] for i in first["items"]] == created[::-1][:2]
    assert first["count"] == 2 and first["has_more"] is True and first["next_before"]

    second = user_client.get(SESSIONS, params={"limit": 2, "before": first["next_before"]}).json()
    assert [i["session_id"] for i in second["items"]] == created[::-1][2:]
    assert second["has_more"] is False and second["next_before"] is None

    assert user_client.get(SESSIONS, params={"limit": 0}).status_code == 422
    assert user_client.get(SESSIONS, params={"before": "not-a-cursor"}).status_code == 422


def test_persistence_failure_does_not_break_the_answer(user_client, graph, monkeypatch, caplog):
    sid = store.create_session(user_client.auth_user.id, _msg("db"))

    def broken(**_kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(runner, "append_message", broken)
    with caplog.at_level(logging.WARNING, logger="workflows.runner"):
        r = user_client.post(CHAT, json={"message": _msg("q"), "session_id": sid})

    assert r.status_code == 200 and r.json()["response"] == graph.answer
    assert any(sid in rec.getMessage() for rec in caplog.records if rec.levelno == logging.WARNING)


def test_detached_run_writes_no_chat_messages(graph):
    result = asyncio.run(runner.run_agent_workflow(_msg("detached"), graph=graph))
    trace = result["trace_id"]
    try:
        with get_platform_engine().connect() as conn:
            rows = conn.execute(
                text("SELECT count(*) FROM platform.chat_messages WHERE trace_id = :t"), {"t": trace}
            ).scalar()
        assert rows == 0
        assert graph.calls[0]["chat_history"] == []
    finally:
        with get_platform_engine().begin() as conn:
            conn.execute(text("DELETE FROM platform.feedback WHERE trace_id = :t"), {"t": trace})
            conn.execute(text("DELETE FROM platform.audit_log WHERE trace_id = :t"), {"t": trace})


# --- T9 review gaps ---------------------------------------------------------------------------


async def _collect(agen) -> list[str]:
    return [chunk async for chunk in agen]


def test_detached_run_never_touches_chat_storage(graph, monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("a detached run must not use chat storage")

    monkeypatch.setattr(runner, "append_message", forbidden)
    monkeypatch.setattr(runner, "load_recent_messages", forbidden)

    result = asyncio.run(runner.run_agent_workflow(_msg("detached-spy"), graph=graph))
    events = asyncio.run(_collect(runner.stream_agent_workflow(_msg("detached-spy2"), graph=graph)))

    assert result["response"] == graph.answer
    assert any(e.startswith("event: complete") for e in events)


def test_context_load_failure_gives_empty_history_and_still_answers(user_client, graph, monkeypatch):
    sid = user_client.post(CHAT, json={"message": _msg("first")}).json()["session_id"]

    def broken(*_args, **_kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(runner, "load_recent_messages", broken)
    r = user_client.post(CHAT, json={"message": _msg("second"), "session_id": sid})

    assert r.status_code == 200 and r.json()["response"] == graph.answer
    assert graph.calls[-1]["chat_history"] == []


def test_sessions_limit_500_is_clamped_to_100(user_client, monkeypatch):
    seen = {}

    def spy(owner_id, *, limit, before):
        seen["limit"] = limit
        return [], None

    monkeypatch.setattr(store, "list_sessions", spy)
    r = user_client.get(SESSIONS, params={"limit": 500})

    assert r.status_code == 200 and seen["limit"] == 100


@pytest.mark.parametrize("path", [CHAT, STREAM])
def test_user_message_is_stored_before_the_graph_runs(user_client, graph, path):
    sid = store.create_session(user_client.auth_user.id, _msg("early"))
    seen = {}
    graph.on_run = lambda: seen.update(turns=store.list_turns(sid, limit=10, before=None)[0])

    user_client.post(path, json={"message": _msg("early-q"), "session_id": sid})

    assert [(t["user_message"], t["status"]) for t in seen["turns"]] == [(_msg("early-q"), "incomplete")]


# --- T13 security -----------------------------------------------------------------------------

_BAD_IDS = ["x" * 101, "a b", "a/b", "id\x00", "../etc", "é", "a;drop"]


@pytest.mark.parametrize("bad", _BAD_IDS + [""])
def test_chat_rejects_malformed_session_id(user_client, graph, bad):
    for path in (CHAT, STREAM):
        assert user_client.post(path, json={"message": _msg("v"), "session_id": bad}).status_code == 422


@pytest.mark.parametrize("bad", _BAD_IDS)
def test_history_rejects_malformed_session_id(user_client, bad):
    assert user_client.get(HISTORY, params={"session_id": bad}).status_code == 422


@pytest.mark.parametrize("good", ["s", "s1", uuid.uuid4().hex, "pytest-au-abc_DEF-1", "a" * 100])
def test_id_pattern_accepts_every_shape_the_app_generates(user_client, graph, good):
    # Well-formed but unknown: a 404 (not a 422) proves the format itself is accepted.
    assert user_client.post(CHAT, json={"message": _msg("v"), "session_id": good}).status_code == 404
    assert user_client.get(HISTORY, params={"session_id": good}).status_code == 404


def test_nul_in_message_or_comment_is_422(user_client, graph):
    assert user_client.post(CHAT, json={"message": "a\x00b"}).status_code == 422
    assert user_client.post(STREAM, json={"message": "a\x00b"}).status_code == 422
    body = user_client.post(CHAT, json={"message": _msg("rate")}).json()
    for bad in ({"comment": "x\x00"}, {"comment": "x" * 2001}, {"trace_id": "t\x00"}, {"trace_id": "t" * 101}):
        payload = {"trace_id": body["trace_id"], "rating": 3, **bad}
        assert user_client.post(FEEDBACK, json=payload).status_code == 422
    ok = user_client.post(FEEDBACK, json={"trace_id": body["trace_id"], "rating": 3, "comment": "x" * 2000})
    assert ok.status_code == 200


def test_sessions_cursor_with_nul_is_422(user_client):
    cursor = base64.urlsafe_b64encode(b"2026-11-06T00:00:00+00:00|ab\x00cd").decode().rstrip("=")

    assert user_client.get(SESSIONS, params={"before": cursor}).status_code == 422
    assert user_client.get(SESSIONS, params={"before": "A" * 301}).status_code == 422


@pytest.mark.parametrize("path", [CHAT, STREAM])
def test_malformed_base64_attachment_is_422_and_creates_no_session(user_client, graph, path):
    bad = {"filename": "a.png", "mime_type": "image/png", "data": "@@not base64@@"}

    r = user_client.post(path, json={"message": _msg("att"), "attachments": [bad]})

    assert r.status_code == 422
    assert user_client.get(SESSIONS).json()["items"] == []
    assert graph.calls == []


def test_valid_attachment_with_data_url_prefix_is_accepted(user_client, graph):
    data = "data:image/png;base64," + base64.b64encode(b"\x89PNG-bytes").decode()

    r = user_client.post(CHAT, json={"message": _msg("att"), "attachments": [{"data": data}]})

    assert r.status_code == 200


def test_nul_in_attachment_filename_is_422(user_client, graph):
    att = {"filename": "a\x00.png", "data": base64.b64encode(b"x").decode()}
    assert user_client.post(CHAT, json={"message": _msg("att"), "attachments": [att]}).status_code == 422


def test_unmaterializable_attachment_on_new_chat_fails_generic_without_orphan_session(user_client, graph, monkeypatch):
    def broken(_items):
        raise OSError("disk full: /secret/path")

    monkeypatch.setattr("gateway.main.materialize_attachments", broken)
    att = {"data": base64.b64encode(b"x").decode()}

    r = user_client.post(CHAT, json={"message": _msg("att"), "attachments": [att]})

    assert r.status_code == 500 and "secret" not in r.text and "session_id" not in r.json()
    assert user_client.get(SESSIONS).json()["items"] == []


def test_chat_error_audit_keeps_type_and_a_truncated_message(user_client, monkeypatch):
    class Leaky(FakeGraph):
        async def ainvoke(self, initial, config):
            raise RuntimeError("SELECT " + "x" * 500)

    monkeypatch.setattr(runner, "_default_graph", Leaky())
    sid = user_client.post(CHAT, json={"message": _msg("audit")}).json()["session_id"]

    with get_platform_engine().connect() as conn:
        error = conn.execute(
            text("SELECT payload->>'error' FROM platform.audit_log "
                 "WHERE action = 'chat_error' AND replace(session_id::text, '-', '') = :s"),
            {"s": sid},
        ).scalar()
    assert error.startswith("RuntimeError: SELECT ")
    assert len(error) == len("RuntimeError: ") + 200


# --- pipeline steps are per turn ----------------------------------------------------------------


def _stepping_graph():
    """Real GraphState reducer (operator.add on pipeline_steps) + MemorySaver, one node per turn."""
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.graph import END, START, StateGraph

    from workflows.state import GraphState, PipelineStep

    def node(state):
        label = state["user_message"][len(PREFIX)]
        steps = [PipelineStep(id=f"{label}-{n}", phase="worker", title="t") for n in (1, 2)]
        return {"pipeline_steps": steps, "final_response": f"answer {label}"}

    builder = StateGraph(GraphState)
    builder.add_node("work", node)
    builder.add_edge(START, "work")
    builder.add_edge("work", END)
    return builder.compile(checkpointer=MemorySaver())


def test_pipeline_in_response_is_only_the_current_turn(user_client, monkeypatch):
    monkeypatch.setattr(runner, "_default_graph", _stepping_graph())
    first = user_client.post(CHAT, json={"message": _msg("a")}).json()
    second = user_client.post(CHAT, json={"message": _msg("b"), "session_id": first["session_id"]}).json()
    third = user_client.post(CHAT, json={"message": _msg("c"), "session_id": first["session_id"]}).json()

    assert [s["id"] for s in first["pipeline"]] == ["a-1", "a-2"]
    assert [s["id"] for s in second["pipeline"]] == ["b-1", "b-2"]
    assert [s["id"] for s in third["pipeline"]] == ["c-1", "c-2"]


def test_sse_complete_pipeline_is_only_the_current_turn(user_client, monkeypatch):
    monkeypatch.setattr(runner, "_default_graph", _stepping_graph())
    first = user_client.post(CHAT, json={"message": _msg("a")}).json()

    r = user_client.post(STREAM, json={"message": _msg("b"), "session_id": first["session_id"]})

    complete = [d for name, d in _sse_events(r.text) if name == "complete"][0]
    assert [s["id"] for s in complete["pipeline"]] == ["b-1", "b-2"]


# --- feedback auto-promote is admin-only ---------------------------------------------------------


def _spy_promotion(monkeypatch) -> list[str]:
    from core.intelligence import feedback_store

    promoted: list[str] = []
    monkeypatch.setattr(feedback_store, "_try_auto_promote", lambda trace_id, rating: promoted.append(trace_id))
    return promoted


def test_user_rating_never_auto_promotes_but_admin_rating_does(user_client, admin_client, graph, monkeypatch):
    promoted = _spy_promotion(monkeypatch)
    mine = user_client.post(CHAT, json={"message": _msg("rate-u")}).json()["trace_id"]
    admins = admin_client.post(CHAT, json={"message": _msg("rate-a")}).json()["trace_id"]

    assert user_client.post(FEEDBACK, json={"trace_id": mine, "rating": 5}).status_code == 200
    assert promoted == []

    assert admin_client.post(FEEDBACK, json={"trace_id": admins, "rating": 5}).status_code == 200
    assert promoted == [admins]


def test_api_key_service_rating_auto_promotes(api_key_client, graph, monkeypatch):
    promoted = _spy_promotion(monkeypatch)
    trace = api_key_client.post(CHAT, json={"message": _msg("rate-svc")}).json()["trace_id"]

    assert api_key_client.post(FEEDBACK, json={"trace_id": trace, "rating": 5}).status_code == 200
    assert promoted == [trace]
