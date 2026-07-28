"""Tests for rerank and LLM judge."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from core.control.evaluator import _check_citations_present
from core.control.llm_judge import enrich_eval_with_llm_judge
from core.search.citations import SourceCitation
from core.search.rerank import rerank_citations
from workflows.state import AgentId, EvalResult, IntentType, TriageResult, WorkerResult


@pytest.mark.asyncio
async def test_rerank_orders_by_similarity():
    citations = [
        SourceCitation(
            ref_id="D1", title="A", excerpt="unrelated topic",
            source_type="knowledge", backend="pgvector", score=0.1,
        ),
        SourceCitation(
            ref_id="D2", title="B", excerpt="hop dong lao dong viet nam",
            source_type="knowledge", backend="pgvector", score=0.5,
        ),
    ]

    with (
        patch("core.search.rerank.embed_query", new_callable=AsyncMock) as mock_q,
        patch("core.search.rerank.embed_text", new_callable=AsyncMock) as mock_d,
    ):
        mock_q.return_value = [1.0, 0.0]
        mock_d.side_effect = [
            [0.2, 0.98],
            [0.98, 0.2],
        ]
        ranked = await rerank_citations("hop dong lao dong", citations, top_k=2)

    assert ranked[0].ref_id == "D2"


def test_citations_present_check():
    triage = TriageResult(intent=IntentType.RESEARCH, complexity=0.3)
    workers = [
        WorkerResult(
            task_id="t1",
            agent=AgentId.RESEARCH_WORKER,
            summary="x",
            citations=[{"ref_id": "W1"}],
        )
    ]
    assert _check_citations_present(triage, workers, "Theo [W1] nguon web...")
    assert not _check_citations_present(triage, workers, "Khong co trich dan")


@pytest.mark.asyncio
async def test_enrich_eval_with_llm_judge():
    base = EvalResult(passed=True, score=0.8, checks=[])
    worker = WorkerResult(
        task_id="t1",
        agent=AgentId.RESEARCH_WORKER,
        summary="s",
        citations=[SourceCitation(
            ref_id="D1", title="Doc", excerpt="fact",
            source_type="knowledge", backend="pgvector",
        ).to_dict()],
    )

    with patch(
        "core.control.llm_judge.judge_rag_response",
        new_callable=AsyncMock,
        return_value={"faithfulness": 0.9, "citation_quality": 0.85, "notes": "ok"},
    ):
        result = await enrich_eval_with_llm_judge(
            base,
            user_message="q",
            response="answer [D1]",
            worker_results=[worker],
        )

    assert any(c["name"] == "llm_faithfulness" for c in result.checks)
    assert result.score > 0.8
