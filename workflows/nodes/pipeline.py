"""LangGraph nodes — triage → plan → execute → [review] → [synthesize] → eval.

Fast path: DB-only / greeting / general đơn giản → bỏ review + synthesize.
"""

from __future__ import annotations

from core.control.evaluator import evaluate_response_async
from core.control.guardrails import redact_output
from core.control.triage import analyze_triage_async
from core.search.citations import append_citations_to_response
from workflows.llm_service import review_with_llm, synthesize_with_llm
from workflows.planner import plan_tasks_async
from workflows.pipeline_trace import (
    eval_steps,
    plan_steps,
    review_steps,
    synthesize_steps,
    triage_steps,
    worker_done_steps,
    worker_running_steps,
)
from workflows.state import AgentId, EvalResult, GraphState, PipelineStep, TopologyMode, WorkerResult
from workflows.workers.handlers import run_worker


async def triage_node(state: GraphState) -> dict:
    """Bước 1: Phân tích intent + security scan."""
    triage = await analyze_triage_async(
        state["user_message"],
        chat_history=state.get("chat_history"),
    )

    if triage.blocked:
        return {
            "triage": triage,
            "review_status": "skipped",
            "review_notes": "",
            "final_response": triage.block_reason,
            "worker_results": [],
            "redacted_types": [],
            "citations": [],
            "pipeline_steps": triage_steps(triage),
        }

    return {
        "triage": triage,
        "review_status": "pending",
        "review_notes": "",
        "final_response": "",
        "worker_results": [],
        "redacted_types": [],
        "citations": [],
        "pipeline_steps": triage_steps(triage),
    }


def route_after_triage(state: GraphState) -> str:
    triage = state.get("triage")
    if triage and triage.blocked:
        return "eval"
    return "plan"


async def plan_node(state: GraphState) -> dict:
    """Bước 2: Tạo TaskPlan — LLM chỉ khi multi/complex."""
    triage = state.get("triage")
    plan = await plan_tasks_async(state["user_message"], triage=triage)
    return {
        "plan": plan,
        "topology_mode": plan.topology_mode.value,
        "pipeline_steps": plan_steps(plan),
    }


async def execute_workers_node(state: GraphState) -> dict:
    """Bước 3: Chạy workers — fast path set final_response ngay."""
    plan = state.get("plan")
    triage = state.get("triage")

    if not plan:
        return {"worker_results": []}

    if plan.is_greeting:
        response = "Xin chào! Tôi là trợ lý AI đa năng. Bạn cần hỗ trợ gì?"
        greeting_result = WorkerResult(
            task_id="greeting",
            agent=AgentId.DEFAULT,
            summary=response,
            success=True,
        )
        return {
            "worker_results": [greeting_result],
            "final_response": response,
            "pipeline_steps": worker_done_steps([greeting_result]),
        }

    running: list[PipelineStep] = worker_running_steps(plan.subtasks)
    results_list: list[WorkerResult] = []
    done: list[PipelineStep] = []

    for task in plan.subtasks:
        result = await run_worker(task, chat_history=state.get("chat_history"))
        results_list.append(result)
        done.extend(worker_done_steps([result]))

    updates: dict = {
        "worker_results": results_list,
        "pipeline_steps": running + done,
    }

    # Fast path: trả thẳng kết quả worker, không qua synthesizer
    if triage and triage.skip_synthesize and len(results_list) == 1:
        raw = results_list[0].summary
        redacted, types = redact_output(raw)
        updates["final_response"] = redacted
        updates["redacted_types"] = types

    return updates


def route_after_execute(state: GraphState) -> str:
    triage = state.get("triage")

    if triage and triage.skip_synthesize and state.get("final_response"):
        return "eval"

    mode = state.get("topology_mode", "planned")
    if triage and triage.skip_review:
        return "synthesize"
    if mode in ("reviewed", "council"):
        return "review"
    return "synthesize"


async def review_node(state: GraphState) -> dict:
    plan = state.get("plan")
    results = state.get("worker_results", [])

    if plan and plan.topology_mode == TopologyMode.DIRECT:
        return {
            "review_status": "skipped",
            "review_notes": "Direct mode",
            "pipeline_steps": review_steps("skipped", "Direct mode"),
        }

    status, notes = await review_with_llm(
        state["user_message"],
        results,
        chat_history=state.get("chat_history"),
    )
    return {
        "review_status": status,
        "review_notes": notes,
        "pipeline_steps": review_steps(status, notes),
    }


async def synthesize_node(state: GraphState) -> dict:
    if state.get("final_response"):
        triage = state.get("triage")
        if triage and triage.skip_synthesize:
            return {"pipeline_steps": synthesize_steps(skipped=True)}
        return {}

    plan = state.get("plan")
    results = state.get("worker_results", [])

    if not results:
        return {"final_response": "Không có kết quả từ workers."}

    llm_response = await synthesize_with_llm(
        state["user_message"],
        results,
        review_status=state.get("review_status", "pass"),
        chat_history=state.get("chat_history"),
    )

    raw = llm_response or _template_response(plan, results, state)
    redacted, types = redact_output(raw)
    return {
        "final_response": redacted,
        "redacted_types": types,
        "pipeline_steps": synthesize_steps(skipped=False),
    }


async def eval_node(state: GraphState) -> dict:
    """Bước cuối: append citations + đánh giá chất lượng response."""
    response = state.get("final_response", "")
    worker_results = state.get("worker_results", [])
    citations: list[dict] = []

    if response and worker_results:
        response, citations = append_citations_to_response(response, worker_results)

    if not response and state.get("triage") and state["triage"].blocked:
        return {
            "eval_result": EvalResult(passed=False, score=0.0, checks=[]),
            "citations": [],
            "pipeline_steps": eval_steps(None),
        }

    if not response:
        return {
            "eval_result": EvalResult(passed=False, score=0.0, checks=[]),
            "citations": [],
            "pipeline_steps": eval_steps(None),
        }

    eval_result = await evaluate_response_async(
        user_message=state["user_message"],
        response=response,
        triage=state.get("triage"),
        worker_results=worker_results,
    )
    return {
        "eval_result": eval_result,
        "final_response": response,
        "citations": citations,
        "pipeline_steps": eval_steps(eval_result),
    }


def _template_response(plan, results, state) -> str:
    parts = [f"**Yêu cầu:** {plan.main_task if plan else state['user_message']}\n"]
    for r in results:
        parts.append(f"\n### [{r.agent.value}]\n{r.summary}")
    return "\n".join(parts)
