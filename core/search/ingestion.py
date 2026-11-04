"""Document ingestion pipeline — parse → chunk → embed → store."""

from __future__ import annotations

import logging
import math
import re
from dataclasses import asdict

from core.search.azure_index import AzureBatchRejected, delete_by_ids, index_chunks
from core.search.azure_search import azure_search_enabled
from core.search.chunking import TextChunk, analyze_chunks, chunk_text
from core.search.embeddings import embed_query, embed_text
from core.search.parsers import ParsedDocument, parse_file
from core.search.pgvector_store import (
    delete_rows_by_ids,
    list_chunks,
    list_document_row_ids,
    set_azure_indexed,
    upsert_document,
)

logger = logging.getLogger(__name__)

_SLUG = re.compile(r"[^a-z0-9_-]+")


class KnowledgeDocumentNotFound(LookupError):
    """No knowledge row belongs to the requested document id."""


class AzureSyncError(RuntimeError):
    """Azure AI Search could not be updated; Postgres was left untouched."""


# doc_id / parent_doc_id are VARCHAR(100) and every chunk id appends "__chunk_NNNN" (12 chars),
# so a parent id longer than 88 makes the chunk insert fail with a truncation error.
MAX_PARENT_DOC_ID_LEN = 100 - len("__chunk_0000")


def slugify_doc_id(name: str) -> str:
    s = name.lower().strip().replace(" ", "-")
    s = _SLUG.sub("-", s)
    return s.strip("-")[:MAX_PARENT_DOC_ID_LEN] or "document"


def preview_document(
    content: str,
    *,
    title: str = "preview",
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> dict:
    """Preview chunks + quality analysis without writing to DB."""
    chunks = chunk_text(content, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    analysis = analyze_chunks(chunks, overlap_chars=chunk_overlap)
    return {
        "title": title,
        "total_chars": len(content),
        "analysis": asdict(analysis),
        "chunks": [
            {
                "index": c.index,
                "char_count": c.char_count,
                "token_estimate": c.token_estimate,
                "preview": c.content[:300] + ("..." if len(c.content) > 300 else ""),
                "content": c.content,
            }
            for c in chunks
        ],
    }


async def evaluate_chunks_for_query(chunks: list[TextChunk], query: str) -> list[dict]:
    """Dry-run: embed query and score each chunk — verify chunking retrieves correctly."""
    query_vec = await embed_query(query)
    if query_vec is None:
        return [{"index": c.index, "score": None, "note": "no embedding API key"} for c in chunks]

    results = []
    for c in chunks:
        chunk_vec = await embed_text(f"{c.metadata.get('title', '')}\n{c.content}")
        if chunk_vec is None:
            results.append({"index": c.index, "score": None, "preview": c.content[:200]})
            continue
        score = _cosine_similarity(query_vec, chunk_vec)
        results.append({
            "index": c.index,
            "score": round(score, 4),
            "char_count": c.char_count,
            "preview": c.content[:200],
        })
    results.sort(key=lambda x: x.get("score") or -1, reverse=True)
    return results


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


async def ingest_parsed_document(
    parsed: ParsedDocument,
    *,
    doc_id: str | None = None,
    domain: str = "general",
    source: str | None = None,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
    replace_existing: bool = True,
) -> dict:
    """Chunk, embed, and store all chunks for a parsed document."""
    parent_id = doc_id or slugify_doc_id(parsed.title)
    src = source or parsed.source_type

    # Captured before the delete so ids that disappear on re-ingest can be purged from Azure.
    old_ids: list[str] = list_document_row_ids(parent_id) if replace_existing else []
    if replace_existing:
        # Exactly the rows purged from Azure below; a parent-based delete is broader (it also
        # matches a row whose doc_id equals parent_id) and would desync the two stores.
        delete_rows_by_ids(old_ids)

    chunks = chunk_text(
        parsed.content,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        metadata={"parent_doc_id": parent_id, "title": parsed.title, **parsed.metadata},
    )
    analysis = analyze_chunks(chunks, overlap_chars=chunk_overlap)

    stored = 0
    embedded = 0
    azure_docs: list[dict] = []
    for c in chunks:
        chunk_doc_id = f"{parent_id}__chunk_{c.index:04d}"
        embed_input = f"{parsed.title}\n{c.content}"
        embedding = await embed_text(embed_input)
        chunk_title = f"{parsed.title} (chunk {c.index + 1}/{len(chunks)})"
        upsert_document(
            doc_id=chunk_doc_id,
            title=chunk_title,
            content=c.content,
            domain=domain,
            source=src,
            embedding=embedding,
            parent_doc_id=parent_id,
            chunk_index=c.index,
            metadata={
                "parent_doc_id": parent_id,
                "chunk_index": c.index,
                "chunk_count": len(chunks),
                **parsed.metadata,
            },
        )
        stored += 1
        if embedding:
            embedded += 1
        azure_docs.append({
            "doc_id": chunk_doc_id, "title": chunk_title, "content": c.content,
            "domain": domain, "source": src,
        })

    new_ids = {d["doc_id"] for d in azure_docs}
    azure = _sync_to_azure(parent_id, azure_docs, stale_ids=[i for i in old_ids if i not in new_ids])

    logger.info(
        "Ingested %s: %d chunks, %d embedded (quality=%.2f)",
        parent_id, stored, embedded, analysis.quality_score,
    )
    return {
        "parent_doc_id": parent_id,
        "chunks_stored": stored,
        "embedded_count": embedded,
        "analysis": asdict(analysis),
        "has_embeddings": embedded == stored,
        "azure": azure,
    }


def _sync_to_azure(parent_id: str, docs: list[dict], *, stale_ids: list[str]) -> dict:
    """Mirror freshly stored chunks to Azure. Never raises: Postgres is the source of truth."""
    if not azure_search_enabled():
        return {"enabled": False, "indexed": 0, "total": 0, "error": None}
    total = len(docs)
    try:
        delete_by_ids(stale_ids)
        succeeded, total = index_chunks(docs)
    except Exception as exc:
        # Our own AzureBatchRejected message holds only counts and status codes; SDK messages may
        # echo endpoints, so for those only the class and status code are logged.
        detail = str(exc) if isinstance(exc, AzureBatchRejected) else ""
        logger.warning(
            "Azure sync failed for %s: %s (status %s) %s",
            parent_id, type(exc).__name__, getattr(exc, "status_code", None), detail,
        )
        try:
            set_azure_indexed(parent_id, False)
        except Exception as flag_exc:
            # Chunks are already stored; a failed flag write must not turn the upload into a 500.
            logger.warning(
                "Could not flag azure_indexed=false for %s: %s", parent_id, type(flag_exc).__name__
            )
        # Class name only: SDK messages can echo endpoints or request details.
        return {"enabled": True, "indexed": 0, "total": total, "error": f"{type(exc).__name__}: Azure sync failed"}
    try:
        set_azure_indexed(parent_id, True)
    except Exception as flag_exc:
        # Chunks are stored and in Azure; only the flag is stale. Do not fail the upload.
        logger.warning(
            "Could not flag azure_indexed=true for %s: %s", parent_id, type(flag_exc).__name__
        )
    return {"enabled": True, "indexed": succeeded, "total": total, "error": None}


def delete_document(doc_id: str) -> dict:
    """Hard-delete a document: Azure first, then Postgres, so a failed Azure call is retryable.

    Raises KnowledgeDocumentNotFound when nothing exists and AzureSyncError when Azure fails
    (Postgres is then untouched).
    """
    ids = list_document_row_ids(doc_id)
    if not ids:
        raise KnowledgeDocumentNotFound(doc_id)

    enabled = azure_search_enabled()
    azure_deleted = 0
    if enabled:
        try:
            azure_deleted = delete_by_ids(ids)
        except Exception as exc:
            logger.warning(
                "Azure delete failed for %s: %s (status %s)",
                doc_id, type(exc).__name__, getattr(exc, "status_code", None),
            )
            raise AzureSyncError(f"Azure delete failed for {doc_id}: {type(exc).__name__}") from exc

    # Same id list as sent to Azure, so both stores lose exactly the same rows. If this fails after
    # the Azure delete succeeded the caller sees a 500 and nothing is audited, but a retry is
    # idempotent (Azure ignores missing keys) and finishes the job.
    deleted_rows = delete_rows_by_ids(ids)
    logger.info("Deleted knowledge document %s: %d rows", doc_id, deleted_rows)
    return {
        "doc_id": doc_id,
        "deleted_rows": deleted_rows,
        "azure": {"enabled": enabled, "deleted": azure_deleted, "error": None},
    }


async def ingest_file_bytes(
    data: bytes,
    filename: str,
    **kwargs,
) -> dict:
    parsed = parse_file(data, filename)
    return await ingest_parsed_document(parsed, **kwargs)


def get_parent_chunks(parent_doc_id: str) -> list[dict]:
    rows = list_chunks(parent_doc_id)
    return [
        {
            "doc_id": r["doc_id"],
            "chunk_index": r["chunk_index"],
            "title": r["title"],
            "char_count": len(r["content"]),
            "has_embedding": r.get("has_embedding", False),
            "preview": r["content"][:300],
        }
        for r in rows
    ]
