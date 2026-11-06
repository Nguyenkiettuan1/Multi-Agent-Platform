"""FastAPI Gateway — Layer 2 (API Controller)."""

from __future__ import annotations

import logging
import base64
import binascii
import re
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.exc import DataError

from config import get_settings
from config.version import SERVICE_VERSION
from core.chat import store as chat_store
from core.checkpointer import create_checkpointer
from core.mcp.attachments import materialize_attachments
from core.planning.media_tasks import image_only_default_message
from core.observability.logging import setup_logging
from core.search.ingestion import MAX_PARENT_DOC_ID_LEN
from core.security.auth import Principal, require_admin, require_user, warm_up
from core.security.throttle import purge_old_attempts
from gateway.auth_routes import router as auth_router
from workflows.graph import build_graph
from workflows.runner import GENERIC_ERROR_MESSAGE, run_agent_workflow, set_graph, stream_agent_workflow

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    # Fail before accepting a single request: without these every login would
    # 500 (no secret to sign cookies) or sessions could not be stored.
    if not settings.auth_secret_key:
        raise RuntimeError("AUTH_SECRET_KEY is not set; refusing to start (see .env.example)")
    if not settings.platform_database_url:
        raise RuntimeError("PLATFORM_DATABASE_URL is not set; refusing to start (sessions live in the platform DB)")
    setup_logging(settings.log_level)
    if not settings.auth_cookie_secure and settings.app_env != "local":
        logger.warning("AUTH_COOKIE_SECURE is off with APP_ENV=%s: session cookies can travel over plain HTTP", settings.app_env)
    warm_up()  # build the argon2 dummy hash now so the first unknown-email login is not a timing tell
    purge_old_attempts()
    checkpointer = await create_checkpointer()
    set_graph(build_graph(checkpointer))
    logger.info("Gateway ready — checkpointer=%s", type(checkpointer).__name__)
    yield


def _docs_kwargs(app_env: str) -> dict:
    """The interactive docs and the OpenAPI schema list every route, so only a local run serves them."""
    if app_env == "local":
        return {}
    return {"docs_url": None, "redoc_url": None, "openapi_url": None}


app = FastAPI(
    title="Multi-Agent Platform API",
    description="Triage → Plan → Agents → Eval",
    version=SERVICE_VERSION,
    lifespan=lifespan,
    **_docs_kwargs(get_settings().app_env),
)
app.include_router(auth_router)


# Every id the app generates (uuid4 hex, trace ids) and every legacy id in the DB (checked
# 2026-11-06: 166 sessions, 242 feedback traces, max 32 chars) fits this; anything else cannot exist.
_ID_PATTERN = r"^[A-Za-z0-9_-]+$"
_ID_MAX_LENGTH = 100
_CURSOR_MAX_LENGTH = 300


def _reject_nul(value: str) -> str:
    # Postgres text cannot hold NUL: it surfaces as a DB error (HTTP 500) instead of a clean 422.
    if "\x00" in value:
        raise ValueError("NUL characters are not allowed")
    return value


class ChatAttachment(BaseModel):
    filename: str = Field("attachment", max_length=255)
    mime_type: str = Field("image/png", max_length=255)
    data: str = Field(..., min_length=1, max_length=8_000_000)

    _no_nul = field_validator("filename", "mime_type")(_reject_nul)

    @field_validator("data")
    @classmethod
    def _valid_base64(cls, value: str) -> str:
        # Checked here, before a session is created or a file written. Same "data:...,<b64>" split
        # as materialize_attachments; whitespace is tolerated, anything else non-base64 is not.
        payload = "".join(value.split(",")[-1].split())
        try:
            base64.b64decode(payload, validate=True)
        except (binascii.Error, ValueError):
            raise ValueError("data must be base64") from None
        return value


class ChatRequest(BaseModel):
    message: str = Field(default="", max_length=8000)
    session_id: str | None = Field(default=None, max_length=_ID_MAX_LENGTH, pattern=_ID_PATTERN)
    attachments: list[ChatAttachment] = Field(default_factory=list, max_length=3)

    _no_nul = field_validator("message")(_reject_nul)

    @model_validator(mode="after")
    def require_message_or_attachment(self) -> "ChatRequest":
        if not self.message.strip() and not self.attachments:
            raise ValueError("Message or attachment required")
        return self


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
    trace_id: str = Field(..., max_length=_ID_MAX_LENGTH, pattern=_ID_PATTERN)
    rating: int = Field(..., ge=1, le=5)
    comment: str = Field("", max_length=2000)

    _no_nul = field_validator("comment")(_reject_nul)


_DOC_ID_RE = re.compile(r"[A-Za-z0-9_.-]+")
_MAX_DOC_ID_READ = 200
# app.knowledge_documents.doc_id is VARCHAR(100): a writer cannot store anything longer, so
# POST /admin/knowledge is capped at the column width (read routes still accept up to 200).
_MAX_DOC_ID_COLUMN = 100


def check_doc_id(value: str, max_length: int = _MAX_DOC_ID_READ) -> str:
    """Single source of truth for knowledge doc_ids (routes, JSON body and upload form).

    Dot-only ids are refused because URL resolution turns `.`/`..` into other routes.
    """
    if not (1 <= len(value) <= max_length) or not _DOC_ID_RE.fullmatch(value) or not value.strip("."):
        raise ValueError(f"doc_id must be 1-{max_length} characters of A-Z a-z 0-9 _ . - and not only dots")
    return value


class KnowledgeIngestRequest(BaseModel):
    doc_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1, max_length=500)
    content: str = Field(..., min_length=1)
    domain: str = "general"
    source: str = "api"

    @field_validator("doc_id")
    @classmethod
    def _check_doc_id(cls, value: str) -> str:
        return check_doc_id(value, _MAX_DOC_ID_COLUMN)


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
        "service": "multi-agent-platform",
        "version": SERVICE_VERSION,
        "graph_ready": get_graph() is not None,
    }


@app.get("/api/v1/models")
async def list_models(_: Principal = Depends(require_admin)):
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


@app.get("/api/v1/mcp/catalog")
async def mcp_catalog(_: Principal = Depends(require_admin)):
    """List MCP servers + tools for app runtime (chat agents)."""
    from core.mcp.hub import format_tools_for_llm, get_tool_hub

    hub = get_tool_hub()
    tools = hub.list_tools()
    return {
        "servers": hub.catalog_summary(),
        "tools": [
            {
                "id": t.id,
                "server_id": t.server_id,
                "name": t.name,
                "description": t.description,
                "kind": t.kind,
            }
            for t in tools
        ],
        "tools_json": format_tools_for_llm(tools),
    }


@app.post("/api/v1/feedback")
async def submit_feedback(request: FeedbackRequest, principal: Principal = Depends(require_user)):
    from core.intelligence.feedback_store import apply_user_rating

    # Same 404 as an unknown trace: a different answer would confirm that someone else's trace exists.
    if chat_store.trace_owner(request.trace_id) != principal.user_id:
        raise HTTPException(status_code=404, detail=f"trace_id not found: {request.trace_id}")
    ok = apply_user_rating(
        trace_id=request.trace_id,
        rating=request.rating,
        comment=request.comment,
        # Promotion copies the Q&A into the RAG store every user searches: admin ratings only.
        auto_promote=principal.role == "admin",
    )
    if not ok:
        raise HTTPException(status_code=404, detail=f"trace_id not found: {request.trace_id}")
    return {"status": "ok", "trace_id": request.trace_id}


@app.get("/api/v1/admin/overview")
async def admin_overview(_: Principal = Depends(require_admin)):
    from core.admin.overview import build_admin_overview

    return build_admin_overview()


@app.post("/api/v1/admin/feedback/{trace_id}/promote")
async def admin_promote_feedback(trace_id: str, _: Principal = Depends(require_admin)):
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
async def admin_stats(_: Principal = Depends(require_admin)):
    from core.admin.overview import build_admin_overview

    overview = build_admin_overview()
    return overview.get("counts", {})


@app.get("/api/v1/admin/audit")
async def admin_audit(
    limit: int = 50,
    trace_id: str | None = None,
    _: Principal = Depends(require_admin),
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
    _: Principal = Depends(require_admin),
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
    _: Principal = Depends(require_admin),
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
    _: Principal = Depends(require_admin),
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
    _: Principal = Depends(require_admin),
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
    _: Principal = Depends(require_admin),
):
    """Preview chunks + quality score — does NOT write to DB."""
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
    _: Principal = Depends(require_admin),
):
    """Dry-run: embed query and score each chunk — check if chunking is reasonable."""
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
        return "OPENROUTER_API_KEY or OPENAI_API_KEY required for semantic evaluation."
    top = rankings[0].get("score", 0)
    if top < 0.5:
        return "Low score — try reducing chunk_size, increasing overlap, or check query content."
    if analysis.get("quality_score", 1) < 0.7:
        return "Low chunking quality — see warnings and adjust chunk_size/overlap."
    if len(rankings) > 1 and rankings[0].get("score", 0) - rankings[1].get("score", 0) < 0.05:
        return "Multiple chunks with similar scores — overlap may be too high or chunks too similar."
    return "Chunking looks good — top chunk matches query well."


@app.post("/api/v1/admin/knowledge/upload")
async def admin_upload_knowledge(
    file: UploadFile = File(...),
    doc_id: str | None = Form(None),
    domain: str = Form("general"),
    chunk_size: int | None = Form(None),
    chunk_overlap: int | None = Form(None),
    preview_only: bool = Form(False),
    _: Principal = Depends(require_admin),
):
    """Upload PDF/DOCX/TXT → chunk → embed → store. preview_only=true returns chunks only."""
    from core.search.ingestion import ingest_file_bytes, preview_document
    from core.search.parsers import parse_file

    if doc_id:  # empty/absent -> id generated from the title
        try:
            check_doc_id(doc_id, MAX_PARENT_DOC_ID_LEN)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"doc_id: {exc}") from None

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


def _valid_doc_id(doc_id: str) -> str:
    try:
        return check_doc_id(doc_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@app.get("/api/v1/admin/knowledge/documents")
def admin_list_knowledge_documents(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    domain: str | None = None,
    _: Principal = Depends(require_admin),
):
    """One entry per document (chunks grouped); limit/offset count documents."""
    from core.search.azure_search import azure_search_enabled
    from core.search.pgvector_store import count_parent_documents, list_parent_documents

    items = list_parent_documents(limit=limit, offset=offset, domain=domain)
    for r in items:
        for k in ("created_at", "updated_at"):
            if r.get(k):
                r[k] = r[k].isoformat()
    return {
        "items": items,
        "total": count_parent_documents(domain=domain),
        "azure_enabled": azure_search_enabled(),
    }


# The /documents routes are declared before the legacy `/{parent_doc_id}/chunks` route:
# FastAPI matches in declaration order.
@app.get("/api/v1/admin/knowledge/documents/{doc_id}")
def admin_get_knowledge_document(
    _: Principal = Depends(require_admin),  # before doc_id: auth must run before validation
    doc_id: str = Depends(_valid_doc_id),
):
    from core.search.azure_search import azure_search_enabled
    from core.search.pgvector_store import get_document_with_chunks

    doc = get_document_with_chunks(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Knowledge document not found")
    for k in ("created_at", "updated_at"):
        if doc.get(k):
            doc[k] = doc[k].isoformat()
    return {**doc, "azure_enabled": azure_search_enabled()}


@app.delete("/api/v1/admin/knowledge/documents/{doc_id}")
def admin_delete_knowledge_document(
    _: Principal = Depends(require_admin),  # before doc_id: auth must run before validation
    doc_id: str = Depends(_valid_doc_id),
):
    """Hard delete (Azure first, then Postgres). Azure failure -> 502 and Postgres is kept."""
    from core.search.ingestion import AzureSyncError, KnowledgeDocumentNotFound, delete_document

    try:
        result = delete_document(doc_id)
    except KnowledgeDocumentNotFound:
        raise HTTPException(status_code=404, detail="Knowledge document not found") from None
    except AzureSyncError as exc:
        _audit_knowledge_delete(doc_id, deleted_rows=0, error=type(exc).__name__)
        raise HTTPException(status_code=502, detail="Azure Search delete failed; document kept") from None
    _audit_knowledge_delete(doc_id, deleted_rows=result["deleted_rows"], azure=result["azure"])
    return result


def _audit_knowledge_delete(doc_id: str, *, deleted_rows: int, azure: dict | None = None, error: str | None = None) -> None:
    """Record the attempt in platform.audit_log. Ids and counts only, never document content.

    write_audit never raises: it logs DB failures and silently does nothing when
    PLATFORM_DATABASE_URL is unset, so a delete is unaudited in that setup.
    """
    import uuid

    from core.observability.audit import write_audit

    payload: dict = {"doc_id": doc_id, "deleted_rows": deleted_rows}
    if azure is not None:
        payload["azure"] = azure
    if error is not None:
        payload["error"] = error
    write_audit(
        trace_id=f"knowledge-delete-{uuid.uuid4().hex}",
        action="knowledge_delete",
        agent_name="admin_api",
        payload=payload,
    )


@app.get("/api/v1/admin/knowledge/{parent_doc_id}/chunks")
async def admin_list_document_chunks(
    parent_doc_id: str,
    _: Principal = Depends(require_admin),
):
    from core.search.ingestion import get_parent_chunks

    chunks = get_parent_chunks(parent_doc_id)
    return {"parent_doc_id": parent_doc_id, "chunks": chunks, "count": len(chunks)}


@app.get("/api/v1/chat/sessions")
async def chat_sessions(
    limit: int = Query(30, ge=1),
    before: str | None = Query(None, max_length=_CURSOR_MAX_LENGTH),
    principal: Principal = Depends(require_user),
):
    try:
        items, next_before = chat_store.list_sessions(
            principal.user_id, limit=min(limit, 100), before=before
        )
    # DataError: a cursor that decodes cleanly but carries a NUL in its session id; the store
    # hands it to Postgres, which refuses it.
    except (ValueError, DataError):
        raise HTTPException(status_code=422, detail="Invalid 'before' cursor") from None
    return {
        "items": items,
        "count": len(items),
        "has_more": next_before is not None,
        "next_before": next_before,
    }


@app.get("/api/v1/chat/history")
async def chat_history(
    session_id: str = Query(..., max_length=_ID_MAX_LENGTH, pattern=_ID_PATTERN),
    limit: int = Query(50, ge=1),
    before: str | None = Query(None, max_length=_CURSOR_MAX_LENGTH),
    principal: Principal = Depends(require_user),
):
    before_id: int | None = None
    if before is not None:
        try:
            before_id = int(before)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid 'before' cursor") from None
        # Ids are positive bigints; anything else is a forged cursor, so reject before the DB sees it.
        if not 0 < before_id <= 2**63 - 1:
            raise HTTPException(status_code=422, detail="Invalid 'before' cursor")
    if chat_store.get_owned_session(session_id, principal.user_id) is None:
        raise HTTPException(status_code=404, detail="Session not found")
    turns, has_more, next_before = chat_store.list_turns(
        session_id, limit=min(limit, 100), before=before_id
    )
    return {
        "session_id": session_id,
        "turns": turns,
        "count": len(turns),
        "has_more": has_more,
        "next_before": next_before,
    }


def _chat_message_for_workflow(message: str, attachments: list) -> str:
    text = message.strip()
    if text:
        return text
    if attachments:
        return image_only_default_message()
    return text


def _require_owned_session(request: ChatRequest, principal: Principal) -> None:
    """A given id must be owned by the caller; a missing or foreign one is the same 404 so ids of
    other users' sessions cannot be probed. Runs before anything is written."""
    if request.session_id is not None and chat_store.get_owned_session(request.session_id, principal.user_id) is None:
        raise HTTPException(status_code=404, detail="Session not found")


def _session_for_turn(request: ChatRequest, principal: Principal, message: str) -> str:
    """The owned session, or a new one. Called last, once the request is known to be good, so a
    bad request never leaves an empty session behind."""
    if request.session_id is None:
        return chat_store.create_session(principal.user_id, message)
    return request.session_id


def _chat_failure(session_id: str | None) -> JSONResponse:
    """Generic 500 for a failed turn. The session id rides along whenever one exists (same as the
    SSE `error` event), so the client retries in it instead of creating an orphan."""
    body: dict = {"detail": GENERIC_ERROR_MESSAGE}
    if session_id is not None:
        body["session_id"] = session_id
    return JSONResponse(status_code=500, content=body)


@app.post("/api/v1/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, principal: Principal = Depends(require_user)):
    message = _chat_message_for_workflow(request.message, request.attachments)
    _require_owned_session(request, principal)
    try:
        attachments = materialize_attachments([a.model_dump() for a in request.attachments])
    except Exception:
        logger.exception("chat attachments failed session=%s", request.session_id)
        return _chat_failure(request.session_id)
    session_id = _session_for_turn(request, principal, message)
    try:
        return ChatResponse(**await run_agent_workflow(
            message,
            user_id=principal.user_id,
            session_id=session_id,
            attachments=attachments,
        ))
    except Exception:
        logger.exception("chat failed session=%s", session_id)
        return _chat_failure(session_id)


@app.post("/api/v1/chat/stream")
async def chat_stream(request: ChatRequest, principal: Principal = Depends(require_user)):
    message = _chat_message_for_workflow(request.message, request.attachments)
    _require_owned_session(request, principal)
    try:
        attachments = materialize_attachments([a.model_dump() for a in request.attachments])
    except Exception:
        logger.exception("chat stream attachments failed session=%s", request.session_id)
        return _chat_failure(request.session_id)
    session_id = _session_for_turn(request, principal, message)
    return StreamingResponse(
        stream_agent_workflow(
            message,
            user_id=principal.user_id,
            session_id=session_id,
            attachments=attachments,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


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
