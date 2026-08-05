"""Chạy workflow end-to-end."""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any

from core.intelligence.feedback_store import load_session_history, save_chat_trace
from core.llm.context import get_usage_tracker, reset_usage_tracker
from core.observability.audit import write_audit
from core.observability.logging import set_trace_id
from core.observability.tracing import trace_span
from workflows.graph import build_graph
from workflows.pipeline_trace import predict_next_phase, running_step, steps_from_node
from workflows.state import GraphState, PipelineStep

logger = logging.getLogger(__name__)

_default_graph = None


def get_graph():
    global _default_graph
    if _default_graph is None:
        from langgraph.checkpoint.memory import MemorySaver

        _default_graph = build_graph(MemorySaver())
    return _default_graph


def set_graph(graph) -> None:
    global _default_graph
    _default_graph = graph


def _build_initial_state(
    *,
    user_message: str,
    session_id: str,
    user_id: str,
    trace_id: str,
    chat_history: list[dict],
    attachments: list[dict] | None = None,
) -> GraphState:
    return {
        "user_message": user_message,
        "session_id": session_id,
        "user_id": user_id,
        "trace_id": trace_id,
        "chat_history": chat_history,
        "attachments": attachments or [],
        "triage": None,
        "plan": None,
        "topology_mode": "planned",
        "worker_results": [],
        "review_status": "pending",
        "review_notes": "",
        "eval_result": None,
        "final_response": "",
        "redacted_types": [],
        "citations": [],
        "pipeline_steps": [],
    }


def _merge_update(accumulated: dict[str, Any], update: dict[str, Any]) -> None:
    for key, value in update.items():
        if key == "pipeline_steps" and value:
            accumulated.setdefault("pipeline_steps", [])
            accumulated["pipeline_steps"].extend(value)
        else:
            accumulated[key] = value


def _pipeline_payload(steps: list) -> list[dict]:
    out: list[dict] = []
    for s in steps:
        if isinstance(s, PipelineStep):
            out.append(s.to_dict())
        elif isinstance(s, dict):
            out.append(s)
    return out


def _result_to_response(result: dict[str, Any], *, trace_id: str, session_id: str) -> dict[str, Any]:
    triage = result.get("triage")
    eval_result = result.get("eval_result")
    return {
        "trace_id": trace_id,
        "session_id": session_id,
        "triage": triage.model_dump() if triage else None,
        "topology_mode": result.get("topology_mode"),
        "plan": result.get("plan").model_dump() if result.get("plan") else None,
        "worker_results": [r.model_dump() for r in result.get("worker_results", [])],
        "review_status": result.get("review_status"),
        "eval": eval_result.model_dump() if eval_result else None,
        "response": result.get("final_response", ""),
        "redacted_types": result.get("redacted_types", []),
        "citations": result.get("citations", []),
        "pipeline": _pipeline_payload(result.get("pipeline_steps", [])),
        "model_usage": get_usage_tracker().to_list(),
    }


async def run_agent_workflow(
    user_message: str,
    *,
    user_id: str = "anonymous",
    session_id: str | None = None,
    graph=None,
    attachments: list[dict] | None = None,
) -> dict[str, Any]:
    reset_usage_tracker()
    trace_id = uuid.uuid4().hex
    session_id = session_id or uuid.uuid4().hex
    set_trace_id(trace_id)

    chat_history = load_session_history(session_id, limit=20) if session_id else []
    initial = _build_initial_state(
        user_message=user_message,
        session_id=session_id,
        user_id=user_id,
        trace_id=trace_id,
        chat_history=chat_history,
        attachments=attachments,
    )

    compiled = graph or get_graph()
    config = {"configurable": {"thread_id": session_id}}

    logger.info("workflow start session=%s user=%s", session_id, user_id)
    write_audit(
        trace_id=trace_id,
        session_id=session_id,
        user_id=user_id,
        action="chat_start",
        payload={"message_preview": user_message[:200]},
    )

    try:
        with trace_span("agent_workflow", session_id=session_id, user_id=user_id):
            result = await compiled.ainvoke(initial, config)
    except Exception as exc:
        write_audit(
            trace_id=trace_id,
            session_id=session_id,
            user_id=user_id,
            action="chat_error",
            payload={"error": str(exc)},
        )
        raise

    triage = result.get("triage")
    eval_result = result.get("eval_result")

    write_audit(
        trace_id=trace_id,
        session_id=session_id,
        user_id=user_id,
        action="chat_complete",
        payload={
            "intent": triage.intent.value if triage else None,
            "topology_mode": result.get("topology_mode"),
            "worker_count": len(result.get("worker_results", [])),
        },
    )

    final_response = result.get("final_response", "")
    eval_score = eval_result.score if eval_result else None
    save_chat_trace(
        trace_id=trace_id,
        session_id=session_id,
        user_message=user_message,
        response=final_response,
        eval_score=eval_score,
    )

    return _result_to_response(result, trace_id=trace_id, session_id=session_id)


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def stream_agent_workflow(
    user_message: str,
    *,
    user_id: str = "anonymous",
    session_id: str | None = None,
    graph=None,
    attachments: list[dict] | None = None,
) -> AsyncIterator[str]:
    """SSE stream — step events live, complete event with full ChatResponse."""
    reset_usage_tracker()
    trace_id = uuid.uuid4().hex
    session_id = session_id or uuid.uuid4().hex
    set_trace_id(trace_id)

    chat_history = load_session_history(session_id, limit=20) if session_id else []
    initial = _build_initial_state(
        user_message=user_message,
        session_id=session_id,
        user_id=user_id,
        trace_id=trace_id,
        chat_history=chat_history,
        attachments=attachments,
    )

    compiled = graph or get_graph()
    config = {"configurable": {"thread_id": session_id}}
    accumulated: dict[str, Any] = dict(initial)

    write_audit(
        trace_id=trace_id,
        session_id=session_id,
        user_id=user_id,
        action="chat_start",
        payload={"message_preview": user_message[:200]},
    )

    yield _sse("step", running_step(
        phase="triage",
        agent="triage",
        title="Phân loại intent",
        detail="Đang phân tích yêu cầu…",
    ).to_dict())

    try:
        with trace_span("agent_workflow", session_id=session_id, user_id=user_id):
            async for update in compiled.astream(initial, config, stream_mode="updates"):
                for node_name, node_output in update.items():
                    _merge_update(accumulated, node_output)
                    for step in steps_from_node(node_name, node_output, accumulated):
                        yield _sse("step", step.to_dict())
                    nxt = predict_next_phase(node_name, accumulated)
                    if nxt:
                        phase, title = nxt
                        yield _sse("step", running_step(
                            phase=phase,
                            title=title,
                            detail="Đang xử lý…",
                        ).to_dict())

            snapshot = await compiled.aget_state(config)
            if snapshot and snapshot.values:
                accumulated = dict(snapshot.values)

    except Exception as exc:
        write_audit(
            trace_id=trace_id,
            session_id=session_id,
            user_id=user_id,
            action="chat_error",
            payload={"error": str(exc)},
        )
        yield _sse("error", {"message": str(exc)})
        return

    triage = accumulated.get("triage")
    eval_result = accumulated.get("eval_result")

    write_audit(
        trace_id=trace_id,
        session_id=session_id,
        user_id=user_id,
        action="chat_complete",
        payload={
            "intent": triage.intent.value if triage else None,
            "topology_mode": accumulated.get("topology_mode"),
            "worker_count": len(accumulated.get("worker_results", [])),
        },
    )

    save_chat_trace(
        trace_id=trace_id,
        session_id=session_id,
        user_message=user_message,
        response=accumulated.get("final_response", ""),
        eval_score=eval_result.score if eval_result else None,
    )

    yield _sse("complete", _result_to_response(accumulated, trace_id=trace_id, session_id=session_id))
