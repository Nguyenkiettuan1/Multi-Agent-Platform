"""Document ingestion pipeline — parse → chunk → embed → store."""

from __future__ import annotations

import logging
import math
import re
from dataclasses import asdict

from core.search.chunking import TextChunk, analyze_chunks, chunk_text
from core.search.embeddings import embed_query, embed_text
from core.search.parsers import ParsedDocument, parse_file
from core.search.pgvector_store import delete_chunks_by_parent, list_chunks, upsert_document

logger = logging.getLogger(__name__)

_SLUG = re.compile(r"[^a-z0-9_-]+")


def slugify_doc_id(name: str) -> str:
    s = name.lower().strip().replace(" ", "-")
    s = _SLUG.sub("-", s)
    return s.strip("-")[:90] or "document"


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

    if replace_existing:
        delete_chunks_by_parent(parent_id)

    chunks = chunk_text(
        parsed.content,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        metadata={"parent_doc_id": parent_id, "title": parsed.title, **parsed.metadata},
    )
    analysis = analyze_chunks(chunks, overlap_chars=chunk_overlap)

    stored = 0
    for c in chunks:
        chunk_doc_id = f"{parent_id}__chunk_{c.index:04d}"
        embed_input = f"{parsed.title}\n{c.content}"
        embedding = await embed_text(embed_input)
        upsert_document(
            doc_id=chunk_doc_id,
            title=f"{parsed.title} (chunk {c.index + 1}/{len(chunks)})",
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

    logger.info("Ingested %s: %d chunks (quality=%.2f)", parent_id, stored, analysis.quality_score)
    return {
        "parent_doc_id": parent_id,
        "chunks_stored": stored,
        "analysis": asdict(analysis),
        "has_embeddings": True,  # may be false per chunk if no API key
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
