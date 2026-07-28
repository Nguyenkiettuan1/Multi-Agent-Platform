"""PostgreSQL pgvector + full-text search."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from functools import lru_cache

from sqlalchemy import text

from core.database.engines import get_app_read_engine, get_app_write_engine
from core.search.embeddings import embed_query

logger = logging.getLogger(__name__)


@dataclass
class SearchHit:
    doc_id: str
    title: str
    content: str
    source: str
    domain: str
    score: float
    backend: str  # pgvector | pg_fts


@lru_cache
def _read_engine():
    return get_app_read_engine()


@lru_cache
def _write_engine():
    return get_app_write_engine()


async def vector_search(query: str, *, top_k: int = 5, domain: str | None = None) -> list[SearchHit]:
    """Semantic search: embed query → cosine similarity against stored chunk embeddings."""
    embedding = await embed_query(query)
    if embedding is None:
        logger.info("vector_search: no query embedding — falling back to FTS")
        return keyword_search(query, top_k=top_k, domain=domain)

    logger.debug("vector_search: query embedded, searching pgvector top_k=%d", top_k)

    vec_literal = "[" + ",".join(str(x) for x in embedding) + "]"
    domain_filter = "AND domain = :domain" if domain else ""

    sql = f"""
        SELECT doc_id, title, content, source, domain,
               1 - (embedding <=> CAST(:vec AS vector)) AS score
        FROM app.knowledge_documents
        WHERE embedding IS NOT NULL {domain_filter}
        ORDER BY embedding <=> CAST(:vec AS vector)
        LIMIT :top_k
    """

    try:
        with _read_engine().connect() as conn:
            params: dict = {"vec": vec_literal, "top_k": top_k}
            if domain:
                params["domain"] = domain
            rows = conn.execute(text(sql), params).mappings().all()
    except Exception as exc:
        logger.warning("vector_search failed (%s) — falling back to FTS", exc)
        return keyword_search(query, top_k=top_k, domain=domain)

    return [
        SearchHit(
            doc_id=r["doc_id"],
            title=r["title"],
            content=r["content"],
            source=r["source"],
            domain=r["domain"],
            score=float(r["score"]),
            backend="pgvector",
        )
        for r in rows
    ]


def keyword_search(query: str, *, top_k: int = 5, domain: str | None = None) -> list[SearchHit]:
    domain_filter = "AND domain = :domain" if domain else ""
    sql = f"""
        SELECT doc_id, title, content, source, domain,
               ts_rank(tsv, plainto_tsquery('simple', :q)) AS score
        FROM app.knowledge_documents
        WHERE tsv @@ plainto_tsquery('simple', :q) {domain_filter}
        ORDER BY score DESC
        LIMIT :top_k
    """
    try:
        with _read_engine().connect() as conn:
            params: dict = {"q": query, "top_k": top_k}
            if domain:
                params["domain"] = domain
            rows = conn.execute(text(sql), params).mappings().all()
    except Exception as exc:
        logger.warning("keyword_search failed (%s)", exc)
        return []

    if not rows:
        return _fallback_like_search(query, top_k=top_k, domain=domain)

    return [
        SearchHit(
            doc_id=r["doc_id"],
            title=r["title"],
            content=r["content"],
            source=r["source"],
            domain=r["domain"],
            score=float(r["score"]),
            backend="pg_fts",
        )
        for r in rows
    ]


def _fallback_like_search(query: str, *, top_k: int = 5, domain: str | None = None) -> list[SearchHit]:
    domain_filter = "AND domain = :domain" if domain else ""
    sql = f"""
        SELECT doc_id, title, content, source, domain, 0.5 AS score
        FROM app.knowledge_documents
        WHERE (title ILIKE :pat OR content ILIKE :pat) {domain_filter}
        LIMIT :top_k
    """
    with _read_engine().connect() as conn:
        params: dict = {"pat": f"%{query[:100]}%", "top_k": top_k}
        if domain:
            params["domain"] = domain
        rows = conn.execute(text(sql), params).mappings().all()

    return [
        SearchHit(
            doc_id=r["doc_id"],
            title=r["title"],
            content=r["content"][:2000],
            source=r["source"],
            domain=r["domain"],
            score=float(r["score"]),
            backend="pg_fts",
        )
        for r in rows
    ]


def upsert_document(
    *,
    doc_id: str,
    title: str,
    content: str,
    source: str = "internal",
    domain: str = "general",
    embedding: list[float] | None = None,
    metadata: dict | None = None,
    parent_doc_id: str | None = None,
    chunk_index: int | None = None,
) -> None:
    meta = metadata or {}
    base_params = {
        "doc_id": doc_id, "title": title, "content": content,
        "source": source, "domain": domain,
        "metadata": json.dumps(meta),
        "parent_doc_id": parent_doc_id,
        "chunk_index": chunk_index,
    }

    if embedding:
        vec_literal = "[" + ",".join(str(x) for x in embedding) + "]"
        sql = """
            INSERT INTO app.knowledge_documents
                (doc_id, title, content, source, domain, metadata, embedding,
                 parent_doc_id, chunk_index)
            VALUES
                (:doc_id, :title, :content, :source, :domain, CAST(:metadata AS jsonb), CAST(:embedding AS vector),
                 :parent_doc_id, :chunk_index)
            ON CONFLICT (doc_id) DO UPDATE SET
                title = EXCLUDED.title, content = EXCLUDED.content,
                embedding = EXCLUDED.embedding, metadata = EXCLUDED.metadata,
                parent_doc_id = EXCLUDED.parent_doc_id, chunk_index = EXCLUDED.chunk_index,
                updated_at = NOW()
        """
        params = {**base_params, "embedding": vec_literal}
    else:
        sql = """
            INSERT INTO app.knowledge_documents
                (doc_id, title, content, source, domain, metadata, parent_doc_id, chunk_index)
            VALUES
                (:doc_id, :title, :content, :source, :domain, CAST(:metadata AS jsonb),
                 :parent_doc_id, :chunk_index)
            ON CONFLICT (doc_id) DO UPDATE SET
                title = EXCLUDED.title, content = EXCLUDED.content,
                metadata = EXCLUDED.metadata,
                parent_doc_id = EXCLUDED.parent_doc_id, chunk_index = EXCLUDED.chunk_index,
                updated_at = NOW()
        """
        params = base_params

    with _write_engine().connect() as conn:
        conn.execute(text(sql), params)
        conn.commit()


def delete_chunks_by_parent(parent_doc_id: str) -> int:
    sql = "DELETE FROM app.knowledge_documents WHERE parent_doc_id = :pid OR doc_id = :pid"
    with _write_engine().connect() as conn:
        result = conn.execute(text(sql), {"pid": parent_doc_id})
        conn.commit()
        return result.rowcount


def list_documents(
    *,
    limit: int = 50,
    domain: str | None = None,
) -> list[dict]:
    """List knowledge documents (metadata only, no content body)."""
    where = "WHERE domain = :domain" if domain else ""
    sql = f"""
        SELECT doc_id, title, source, domain, parent_doc_id, chunk_index,
               length(content) AS content_length,
               embedding IS NOT NULL AS has_embedding,
               created_at, updated_at
        FROM app.knowledge_documents
        {where}
        ORDER BY COALESCE(parent_doc_id, doc_id), chunk_index NULLS FIRST, updated_at DESC
        LIMIT :limit
    """
    params: dict = {"limit": min(limit, 200)}
    if domain:
        params["domain"] = domain
    with _read_engine().connect() as conn:
        rows = conn.execute(text(sql), params).mappings().all()
    return [dict(r) for r in rows]


def count_documents(*, with_embedding: bool | None = None) -> int:
    clause = ""
    if with_embedding is True:
        clause = "WHERE embedding IS NOT NULL"
    elif with_embedding is False:
        clause = "WHERE embedding IS NULL"
    sql = f"SELECT COUNT(*) FROM app.knowledge_documents {clause}"
    with _read_engine().connect() as conn:
        return conn.execute(text(sql)).scalar() or 0


def count_documents_by_source(source: str) -> int:
    with _read_engine().connect() as conn:
        return conn.execute(
            text("SELECT COUNT(*) FROM app.knowledge_documents WHERE source = :source"),
            {"source": source},
        ).scalar() or 0


def list_chunks(parent_doc_id: str) -> list[dict]:
    sql = """
        SELECT doc_id, title, content, chunk_index,
               embedding IS NOT NULL AS has_embedding
        FROM app.knowledge_documents
        WHERE parent_doc_id = :pid OR doc_id = :pid
        ORDER BY chunk_index NULLS LAST, doc_id
    """
    with _read_engine().connect() as conn:
        rows = conn.execute(text(sql), {"pid": parent_doc_id}).mappings().all()
    return [dict(r) for r in rows]
