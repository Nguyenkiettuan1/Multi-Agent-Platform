"""LLM-as-judge — faithfulness & citation quality (P1)."""

from __future__ import annotations

import logging

from core.llm.client import get_llm_client
from core.search.citations import SourceCitation, merge_worker_citations
from workflows.state import EvalResult, WorkerResult

logger = logging.getLogger(__name__)

JUDGE_SYSTEM = """Bạn là evaluator cho hệ thống RAG. Đánh giá câu trả lời dựa trên nguồn được cung cấp.
Trả JSON:
{
  "faithfulness": 0.0-1.0,
  "citation_quality": 0.0-1.0,
  "notes": "ngắn gọn"
}
faithfulness: câu trả lời có bám nguồn không, có bịa không
citation_quality: có dùng [Dx]/[Wx] đúng không"""


async def judge_rag_response(
    *,
    user_message: str,
    response: str,
    citations: list[SourceCitation],
) -> dict | None:
    client = get_llm_client()
    if not client.enabled or not citations:
        return None

    sources_text = "\n\n".join(
        f"[{c.ref_id}] {c.title}\n{c.excerpt[:800]}"
        for c in citations[:8]
    )
    messages = [
        {"role": "system", "content": JUDGE_SYSTEM},
        {
            "role": "user",
            "content": (
                f"Câu hỏi: {user_message}\n\n"
                f"Nguồn:\n{sources_text}\n\n"
                f"Câu trả lời:\n{response[:3000]}"
            ),
        },
    ]

    try:
        data = await client.chat_json("evaluator", messages)
        if not data:
            return None
        return {
            "faithfulness": float(data.get("faithfulness", 0.5)),
            "citation_quality": float(data.get("citation_quality", 0.5)),
            "notes": str(data.get("notes", "")),
        }
    except Exception as exc:
        logger.warning("LLM judge failed: %s", exc)
        return None


async def enrich_eval_with_llm_judge(
    eval_result: EvalResult,
    *,
    user_message: str,
    response: str,
    worker_results: list[WorkerResult],
) -> EvalResult:
    citations_raw = merge_worker_citations(worker_results)
    if not citations_raw:
        return eval_result

    judge = await judge_rag_response(
        user_message=user_message,
        response=response,
        citations=citations_raw,
    )
    if not judge:
        return eval_result

    checks = list(eval_result.checks)
    faith = judge["faithfulness"]
    cite = judge["citation_quality"]
    checks.append({
        "name": "llm_faithfulness",
        "passed": faith >= 0.6,
        "detail": f"score={faith:.2f} — {judge.get('notes', '')}",
    })
    checks.append({
        "name": "llm_citation_quality",
        "passed": cite >= 0.5,
        "detail": f"score={cite:.2f}",
    })

    new_score = round((eval_result.score + faith + cite) / 3, 2)
    return EvalResult(
        passed=eval_result.passed and faith >= 0.5,
        score=new_score,
        checks=checks,
    )
