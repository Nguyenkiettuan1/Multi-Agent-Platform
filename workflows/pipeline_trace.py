"""Build pipeline trace steps for UI / SSE."""

from __future__ import annotations

import uuid

from workflows.state import AgentId, PipelineStep, WorkerResult


def _sid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def running_step(*, phase: str, title: str, agent: str | None = None, detail: str = "") -> PipelineStep:
    return PipelineStep(
        id=_sid(phase),
        phase=phase,
        agent=agent,
        status="running",
        title=title,
        detail=detail,
    )


def done_step(
    *,
    phase: str,
    title: str,
    agent: str | None = None,
    detail: str = "",
    tools: list[str] | None = None,
) -> PipelineStep:
    return PipelineStep(
        id=_sid(phase),
        phase=phase,
        agent=agent,
        status="done",
        title=title,
        detail=detail,
        tools=tools or [],
    )


def skipped_step(*, phase: str, title: str, detail: str = "") -> PipelineStep:
    return PipelineStep(
        id=_sid(phase),
        phase=phase,
        status="skipped",
        title=title,
        detail=detail,
    )


def triage_steps(triage) -> list[PipelineStep]:
    if triage.blocked:
        return [
            done_step(
                phase="triage",
                agent="triage",
                title="Security check",
                detail=f"Blocked: {triage.block_reason}",
            )
        ]
    return [
        done_step(
            phase="triage",
            agent="triage",
            title="Classify intent",
            detail=(
                f"Intent: {triage.intent.value} · "
                f"Complexity: {triage.complexity:.0%} · "
                f"Fast path: {'yes' if triage.fast_path else 'no'}"
            ),
        )
    ]


def plan_steps(plan) -> list[PipelineStep]:
    if plan.is_greeting:
        return [skipped_step(phase="plan", title="Planning", detail="Greeting — planner skipped")]

    agents = [t.assigned_agent.value for t in plan.subtasks]
    return [
        done_step(
            phase="plan",
            agent="meta-planner",
            title="Plan agents",
            detail=(
                f"Topology: {plan.topology_mode.value} · "
                f"Agents: {', '.join(agents) or '—'}"
            ),
        )
    ]


def worker_running_steps(tasks) -> list[PipelineStep]:
    return [
        running_step(
            phase="worker",
            agent=task.assigned_agent.value,
            title=f"Running {format_agent_label(task.assigned_agent)}",
            detail=task.description[:200],
        )
        for task in tasks
    ]


def worker_done_steps(results: list[WorkerResult]) -> list[PipelineStep]:
    steps: list[PipelineStep] = []
    for r in results:
        cite_count = len(r.citations)
        tool_text = ", ".join(r.tools_called) if r.tools_called else "—"
        status = "Success" if r.success else "Error"
        steps.append(
            done_step(
                phase="worker",
                agent=r.agent.value,
                title=format_agent_label(r.agent),
                detail=f"{status} · Tools: {tool_text} · Sources: {cite_count}",
                tools=list(r.tools_called),
            )
        )
    return steps


def review_steps(status: str, notes: str) -> list[PipelineStep]:
    if status == "skipped":
        return [skipped_step(phase="review", title="Reviewer", detail=notes or "Review skipped")]
    return [
        done_step(
            phase="review",
            agent="reviewer",
            title="Reviewer check",
            detail=f"Result: {status}" + (f" — {notes}" if notes else ""),
        )
    ]


def synthesize_steps(skipped: bool = False) -> list[PipelineStep]:
    if skipped:
        return [skipped_step(phase="synthesize", title="Synthesizer", detail="Fast path — using worker output")]
    return [
        done_step(
            phase="synthesize",
            agent="synthesizer",
            title="Synthesize response",
            detail="Merge agent results into final response",
        )
    ]


def eval_steps(eval_result) -> list[PipelineStep]:
    if not eval_result:
        return []
    return [
        done_step(
            phase="eval",
            agent="evaluator",
            title="Quality evaluation",
            detail=f"Score: {eval_result.score:.0%} · {'Passed' if eval_result.passed else 'Failed'}",
        )
    ]


def format_agent_label(agent: AgentId | str) -> str:
    raw = agent.value if isinstance(agent, AgentId) else agent
    return raw.replace("-", " ").replace("_", " ").title()


def predict_next_phase(current: str, state: dict) -> tuple[str, str] | None:
    """Return (phase, title) for the next running indicator."""
    triage = state.get("triage")

    if current == "triage":
        if triage and getattr(triage, "blocked", False):
            return ("eval", "Evaluate & finalize")
        return ("plan", "Plan agents")

    if current == "plan":
        return ("worker", "Run agents")

    if current == "execute_workers":
        if triage and triage.skip_synthesize and state.get("final_response"):
            return ("eval", "Evaluate & finalize")
        if triage and triage.skip_review:
            return ("synthesize", "Synthesize response")
        mode = state.get("topology_mode", "planned")
        if mode in ("reviewed", "council"):
            return ("review", "Reviewer check")
        return ("synthesize", "Synthesize response")

    if current == "review":
        return ("synthesize", "Synthesize response")

    if current == "synthesize":
        return ("eval", "Evaluate & finalize")

    return None


def steps_from_node(node_name: str, output: dict, state: dict) -> list[PipelineStep]:
    if node_name == "triage":
        triage = output.get("triage")
        return triage_steps(triage) if triage else []

    if node_name == "plan":
        plan = output.get("plan")
        return plan_steps(plan) if plan else []

    if node_name == "execute_workers":
        results = output.get("worker_results", [])
        if not results:
            return []
        return worker_done_steps(results)

    if node_name == "review":
        return review_steps(
            output.get("review_status", "skipped"),
            output.get("review_notes", ""),
        )

    if node_name == "synthesize":
        if output.get("final_response"):
            return synthesize_steps(skipped=False)
        return [skipped_step(phase="synthesize", title="Synthesizer", detail="Response already available")]

    if node_name == "eval":
        return eval_steps(output.get("eval_result"))

    return []
