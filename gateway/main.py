"""FastAPI Gateway — Layer 2 (API Controller)."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from config import get_settings
from config.version import SERVICE_VERSION
from core.checkpointer import create_checkpointer
from core.observability.logging import setup_logging
from core.security.auth import verify_api_key
from workflows.graph import build_graph
from workflows.runner import run_agent_workflow, set_graph, stream_agent_workflow

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(settings.log_level)
    checkpointer = await create_checkpointer()
    set_graph(build_graph(checkpointer))
    logger.info("Gateway ready — checkpointer=%s", type(checkpointer).__name__)
    yield


app = FastAPI(
    title="PHANLAW Multi-Agent API",
    description="Triage → Plan → Agents → Eval",
    version=SERVICE_VERSION,
    lifespan=lifespan,
)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)
    session_id: str | None = None
    user_id: str = "anonymous"


class ChatResponse(BaseModel):
    trace_id: str
    session_id: str
    triage: dict | None = None
    topology_mode: str | None
    plan: dict | None
    worker_results: list[dict]
    review_status: str | None
    eval: dict | None = None
    response: str
    redacted_types: list[str] = Field(default_factory=list)
    citations: list[dict] = Field(default_factory=list)
    pipeline: list[dict] = Field(default_factory=list)
    model_usage: list[dict] = Field(default_factory=list)


class FeedbackRequest(BaseModel):
    trace_id: str
    rating: int = Field(..., ge=1, le=5)
    comment: str = ""


class KnowledgeIngestRequest(BaseModel):
    doc_id: str = Field(..., min_length=1, max_length=100)
    title: str = Field(..., min_length=1, max_length=500)
    content: str = Field(..., min_length=1)
    domain: str = "general"
    source: str = "api"


class ChunkPreviewRequest(BaseModel):
    content: str = Field(..., min_length=1)
    title: str = "preview"
    chunk_size: int | None = None
    chunk_overlap: int | None = None


class ChunkEvalRequest(BaseModel):
    content: str = Field(..., min_length=1)
    query: str = Field(..., min_length=1)
    title: str = "preview"
    chunk_size: int | None = None
    chunk_overlap: int | None = None


@app.get("/health")
async def health():
    from workflows.runner import get_graph

    return {
        "status": "ok",
        "service": "phanlaw-multi-agent",
        "version": SERVICE_VERSION,
        "graph_ready": get_graph() is not None,
    }


@app.get("/api/v1/models")
async def list_models(_: str | None = Depends(verify_api_key)):
    from core.llm.router import get_router
    from core.registry.agents import load_registry
    from core.registry.pipeline import load_pipeline_registry

    router = get_router()
    agents = {
        aid.value: {
            "model": router.resolve_for_agent(aid).model.ref,
            "source": router.resolve_for_agent(aid).source.value,
            "fallback_chain": router.resolve_for_agent(aid).fallback_chain,
        }
        for aid in load_registry()
    }
    pipeline = {
        name: {
            "model": router.resolve_for_pipeline(name).model.ref,
            "source": router.resolve_for_pipeline(name).source.value,
        }
        for name in load_pipeline_registry()
    }
    return {
        "catalog": router.list_models(),
        "agents": agents,
        "pipeline": pipeline,
        "llm_enabled": router.any_provider_configured(),
    }


@app.post("/api/v1/feedback")
async def submit_feedback(request: FeedbackRequest, _: str | None = Depends(verify_api_key)):
    from core.intelligence.feedback_store import apply_user_rating

    ok = apply_user_rating(
        trace_id=request.trace_id,
        rating=request.rating,
        comment=request.comment,
    )
    if not ok:
        raise HTTPException(status_code=404, detail=f"trace_id not found: {request.trace_id}")
    return {"status": "ok", "trace_id": request.trace_id}


@app.get("/api/v1/admin/overview")
async def admin_overview(_: str | None = Depends(verify_api_key)):
    from core.admin.overview import build_admin_overview

    return build_admin_overview()


@app.post("/api/v1/admin/feedback/{trace_id}/promote")
async def admin_promote_feedback(trace_id: str, _: str | None = Depends(verify_api_key)):
    from core.intelligence.knowledge_promotion import load_feedback_for_promotion, promote_feedback_to_knowledge

    record = load_feedback_for_promotion(trace_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"trace_id not found or already promoted: {trace_id}")
    result = await promote_feedback_to_knowledge(
        trace_id=trace_id,
        user_message=record["user_message"],
        response=record["response"],
    )
    return result


@app.get("/api/v1/admin/stats")
async def admin_stats(_: str | None = Depends(verify_api_key)):
    from core.admin.overview import build_admin_overview

    overview = build_admin_overview()
    return overview.get("counts", {})


@app.get("/api/v1/admin/audit")
async def admin_audit(
    limit: int = 50,
    trace_id: str | None = None,
    _: str | None = Depends(verify_api_key),
):
    from core.observability.audit import list_audit

    rows = list_audit(limit=min(limit, 200), trace_id=trace_id)
    for r in rows:
        if r.get("created_at"):
            r["created_at"] = r["created_at"].isoformat()
    return {"items": rows, "count": len(rows)}


@app.get("/api/v1/admin/feedback")
async def admin_feedback(
    limit: int = 50,
    min_rating: int | None = None,
    _: str | None = Depends(verify_api_key),
):
    from core.intelligence.feedback_store import list_feedback_records

    items = list_feedback_records(limit=min(limit, 200), min_rating=min_rating)
    return {"items": items, "count": len(items)}


@app.get("/api/v1/admin/feedback/export")
async def admin_feedback_export(
    min_rating: int = 4,
    min_eval_score: float = 0.0,
    format: str = "jsonl",
    limit: int = 1000,
    _: str | None = Depends(verify_api_key),
):
    from fastapi.responses import PlainTextResponse

    from core.intelligence.feedback_store import export_training_dataset

    if format not in ("jsonl", "openai", "pairs"):
        raise HTTPException(status_code=400, detail="format must be jsonl, openai, or pairs")

    body = export_training_dataset(
        min_rating=min_rating,
        min_eval_score=min_eval_score,
        fmt=format,  # type: ignore[arg-type]
        limit=limit,
    )
    return PlainTextResponse(
        content=body or "",
        media_type="application/x-ndjson",
        headers={"Content-Disposition": f'attachment; filename="feedback-{format}.jsonl"'},
    )


@app.get("/api/v1/admin/knowledge")
async def admin_list_knowledge(
    limit: int = 50,
    domain: str | None = None,
    _: str | None = Depends(verify_api_key),
):
    from core.search.pgvector_store import list_documents

    items = list_documents(limit=limit, domain=domain)
    for r in items:
        for k in ("created_at", "updated_at"):
            if r.get(k):
                r[k] = r[k].isoformat()
    return {"items": items, "count": len(items)}


@app.post("/api/v1/admin/knowledge")
async def admin_ingest_knowledge(
    request: KnowledgeIngestRequest,
    _: str | None = Depends(verify_api_key),
):
    from core.search.embeddings import embed_text
    from core.search.pgvector_store import upsert_document

    embedding = await embed_text(f"{request.title}\n{request.content}")
    upsert_document(
        doc_id=request.doc_id,
        title=request.title,
        content=request.content,
        domain=request.domain,
        source=request.source,
        embedding=embedding,
    )
    return {
        "status": "ok",
        "doc_id": request.doc_id,
        "has_embedding": embedding is not None,
    }


@app.post("/api/v1/admin/knowledge/chunk-preview")
async def admin_chunk_preview(
    request: ChunkPreviewRequest,
    _: str | None = Depends(verify_api_key),
):
    """Xem trước chunks + quality score — KHÔNG ghi DB."""
    from core.search.ingestion import preview_document

    return preview_document(
        request.content,
        title=request.title,
        chunk_size=request.chunk_size,
        chunk_overlap=request.chunk_overlap,
    )


@app.post("/api/v1/admin/knowledge/chunk-eval")
async def admin_chunk_eval(
    request: ChunkEvalRequest,
    _: str | None = Depends(verify_api_key),
):
    """Dry-run: embed query và score từng chunk — kiểm tra chunking có hợp lý không."""
    from core.search.chunking import chunk_text
    from core.search.ingestion import evaluate_chunks_for_query, preview_document

    preview = preview_document(
        request.content,
        title=request.title,
        chunk_size=request.chunk_size,
        chunk_overlap=request.chunk_overlap,
    )
    chunks = chunk_text(
        request.content,
        chunk_size=request.chunk_size,
        chunk_overlap=request.chunk_overlap,
    )
    rankings = await evaluate_chunks_for_query(chunks, request.query)
    return {
        "query": request.query,
        "analysis": preview["analysis"],
        "rankings": rankings,
        "recommendation": _chunk_eval_recommendation(rankings, preview["analysis"]),
    }


def _chunk_eval_recommendation(rankings: list[dict], analysis: dict) -> str:
    if not rankings or rankings[0].get("score") is None:
        return "Cần OPENROUTER_API_KEY hoặc OPENAI_API_KEY để đánh giá semantic."
    top = rankings[0].get("score", 0)
    if top < 0.5:
        return "Score thấp — thử giảm chunk_size, tăng overlap, hoặc kiểm tra nội dung query."
    if analysis.get("quality_score", 1) < 0.7:
        return "Chunking chất lượng thấp — xem warnings và chỉnh chunk_size/overlap."
    if len(rankings) > 1 and rankings[0].get("score", 0) - rankings[1].get("score", 0) < 0.05:
        return "Nhiều chunk score gần nhau — có thể overlap quá nhiều hoặc chunk quá giống nhau."
    return "Chunking ổn — chunk top-1 khớp query tốt."


@app.post("/api/v1/admin/knowledge/upload")
async def admin_upload_knowledge(
    file: UploadFile = File(...),
    doc_id: str | None = Form(None),
    domain: str = Form("general"),
    chunk_size: int | None = Form(None),
    chunk_overlap: int | None = Form(None),
    preview_only: bool = Form(False),
    _: str | None = Depends(verify_api_key),
):
    """Upload PDF/DOCX/TXT → chunk → embed → store. preview_only=true chỉ xem chunks."""
    from core.search.ingestion import ingest_file_bytes, preview_document
    from core.search.parsers import parse_file

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")

    filename = file.filename or "document.txt"

    if preview_only:
        parsed = parse_file(data, filename)
        return preview_document(
            parsed.content,
            title=parsed.title,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

    try:
        result = await ingest_file_bytes(
            data,
            filename,
            doc_id=doc_id,
            domain=domain,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ImportError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {"status": "ok", **result}


@app.get("/api/v1/admin/knowledge/{parent_doc_id}/chunks")
async def admin_list_document_chunks(
    parent_doc_id: str,
    _: str | None = Depends(verify_api_key),
):
    from core.search.ingestion import get_parent_chunks

    chunks = get_parent_chunks(parent_doc_id)
    return {"parent_doc_id": parent_doc_id, "chunks": chunks, "count": len(chunks)}


@app.get("/api/v1/chat/sessions")
async def chat_sessions(
    limit: int = 30,
    _: str | None = Depends(verify_api_key),
):
    from core.intelligence.feedback_store import list_recent_sessions

    items = list_recent_sessions(limit=min(limit, 100))
    return {"items": items, "count": len(items)}


@app.get("/api/v1/chat/history")
async def chat_history(
    session_id: str,
    limit: int = 50,
    _: str | None = Depends(verify_api_key),
):
    from core.intelligence.feedback_store import list_session_traces

    items = list_session_traces(session_id, limit=min(limit, 100))
    return {"session_id": session_id, "turns": items, "count": len(items)}


@app.post("/api/v1/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, _: str | None = Depends(verify_api_key)):
    try:
        return ChatResponse(**await run_agent_workflow(
            request.message,
            user_id=request.user_id,
            session_id=request.session_id,
        ))
    except Exception as exc:
        logger.exception("chat failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/v1/chat/stream")
async def chat_stream(request: ChatRequest, _: str | None = Depends(verify_api_key)):
    try:
        return StreamingResponse(
            stream_agent_workflow(
                request.message,
                user_id=request.user_id,
                session_id=request.session_id,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    except Exception as exc:
        logger.exception("chat stream failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def main():
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "gateway.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.app_env == "local",
    )


if __name__ == "__main__":
    main()
