"""Response evaluator — đánh giá chất lượng câu trả lời.

Ref: OpenAI evals, Langfuse scoring, Anthropic eval patterns.

Phase 1: rule-based checks (không cần LLM).
Phase 2+: LLM-as-judge, human feedback loop → self-improvement.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from core.control.guardrails import redact_output, scan_input
from workflows.state import AgentId, EvalResult, IntentType, TriageResult, WorkerResult

ROOT = Path(__file__).resolve().parents[2]
GUARDRAILS_PATH = ROOT / "config" / "guardrails.yaml"


@lru_cache
def _eval_config() -> dict:
    if not GUARDRAILS_PATH.exists():
        return {}
    return yaml.safe_load(GUARDRAILS_PATH.read_text(encoding="utf-8")).get("eval", {})


def evaluate_response(
    *,
    user_message: str,
    response: str,
    triage: TriageResult | None,
    worker_results: list[WorkerResult],
) -> EvalResult:
    checks: list[dict] = []
    score_parts: list[float] = []

    # 1. Worker success
    if worker_results:
        failed = [r for r in worker_results if not r.success]
        passed = len(failed) == 0
        checks.append({
            "name": "worker_success",
            "passed": passed,
            "detail": f"{len(failed)} worker(s) failed" if failed else "all ok",
        })
        score_parts.append(1.0 if passed else 0.0)
    else:
        checks.append({"name": "worker_success", "passed": True, "detail": "no workers"})
        score_parts.append(1.0)

    # 2. Non-empty response
    non_empty = bool(response and response.strip())
    checks.append({
        "name": "non_empty_response",
        "passed": non_empty,
        "detail": "empty" if not non_empty else "ok",
    })
    score_parts.append(1.0 if non_empty else 0.0)

    # 3. Intent match
    intent_ok = _check_intent_match(triage, worker_results)
    checks.append({
        "name": "intent_match",
        "passed": intent_ok,
        "detail": triage.intent.value if triage else "unknown",
    })
    score_parts.append(1.0 if intent_ok else 0.5)

    # 4. No blocked content in output
    output_scan = scan_input(response)
    no_leak = not output_scan.blocked
    checks.append({
        "name": "no_blocked_content",
        "passed": no_leak,
        "detail": "clean" if no_leak else output_scan.block_reason,
    })
    score_parts.append(1.0 if no_leak else 0.0)

    # 5. Citations when research/legal used RAG
    cite_ok = _check_citations_present(triage, worker_results, response)
    checks.append({
        "name": "citations_present",
        "passed": cite_ok,
        "detail": "ok" if cite_ok else "missing [Dx]/[Wx] or Nguồn tham khảo",
    })
    score_parts.append(1.0 if cite_ok else 0.3)

    score = sum(score_parts) / len(score_parts) if score_parts else 0.0
    min_score = _eval_config().get("min_score", 0.6)

    return EvalResult(
        passed=score >= min_score,
        score=round(score, 2),
        checks=checks,
    )


async def evaluate_response_async(
    *,
    user_message: str,
    response: str,
    triage: TriageResult | None,
    worker_results: list[WorkerResult],
) -> EvalResult:
    """Rule-based eval + optional LLM-as-judge."""
    from config import get_settings

    result = evaluate_response(
        user_message=user_message,
        response=response,
        triage=triage,
        worker_results=worker_results,
    )

    if not get_settings().eval_llm_judge_enabled:
        return result

    from core.control.llm_judge import enrich_eval_with_llm_judge

    return await enrich_eval_with_llm_judge(
        result,
        user_message=user_message,
        response=response,
        worker_results=worker_results,
    )


def _check_citations_present(
    triage: TriageResult | None,
    worker_results: list[WorkerResult],
    response: str,
) -> bool:
    search_agents = {AgentId.RESEARCH_WORKER, AgentId.LEGAL_WORKER}
    used_search = any(r.agent in search_agents for r in worker_results)
    has_sources = any(r.citations for r in worker_results)
    if not used_search or not has_sources:
        return True
    if "## Nguồn tham khảo" in response:
        return True
    return "[D" in response or "[W" in response


def _check_intent_match(
    triage: TriageResult | None,
    worker_results: list[WorkerResult],
) -> bool:
    if not triage or not worker_results:
        return True

    agents = {r.agent.value for r in worker_results}

    intent_agent_map = {
        IntentType.DB_ONLY: {"db-worker"},
        IntentType.LEGAL: {"legal-agent"},
        IntentType.RESEARCH: {"research-worker"},
        IntentType.GENERAL: {"general-agent"},
        IntentType.ACTION: {"action-worker"},
        IntentType.GREETING: {"default-agent"},
    }

    expected = intent_agent_map.get(triage.intent)
    if expected is None:
        return True  # MULTI — any combination ok
    return bool(agents & expected)
