"""Azure AI Search index schema and setup helpers."""

from __future__ import annotations

import logging
from typing import Any

from config import get_settings
from core.search.azure_search import azure_search_enabled

logger = logging.getLogger(__name__)

DEFAULT_INDEX_NAME = "knowledge-index"
KNOWLEDGE_INDEX_FIELD_NAMES = ("id", "doc_id", "title", "content", "domain", "source")


def _require_azure_search() -> None:
    if not azure_search_enabled():
        raise RuntimeError(
            "Set AZURE_SEARCH_ENDPOINT and AZURE_SEARCH_API_KEY in .env before running."
        )


def _credential():
    from azure.core.credentials import AzureKeyCredential

    settings = get_settings()
    return AzureKeyCredential(settings.azure_search_api_key)


def _index_client():
    from azure.search.documents.indexes import SearchIndexClient

    settings = get_settings()
    return SearchIndexClient(settings.azure_search_endpoint, _credential())


def build_knowledge_index(index_name: str = DEFAULT_INDEX_NAME):
    """Return SearchIndex definition matching azure_search.py + index_azure.py."""
    from azure.search.documents.indexes.models import (
        SearchableField,
        SearchFieldDataType,
        SearchIndex,
        SimpleField,
    )

    return SearchIndex(
        name=index_name,
        fields=[
            SimpleField(
                name="id",
                type=SearchFieldDataType.String,
                key=True,
                filterable=True,
            ),
            SimpleField(
                name="doc_id",
                type=SearchFieldDataType.String,
                filterable=True,
            ),
            SearchableField(
                name="title",
                type=SearchFieldDataType.String,
            ),
            SearchableField(
                name="content",
                type=SearchFieldDataType.String,
            ),
            SimpleField(
                name="domain",
                type=SearchFieldDataType.String,
                filterable=True,
                facetable=True,
            ),
            SimpleField(
                name="source",
                type=SearchFieldDataType.String,
                filterable=True,
            ),
        ],
    )


def create_or_update_knowledge_index(
    index_name: str | None = None,
) -> str:
    """Create or update the knowledge index on Azure AI Search."""
    _require_azure_search()
    settings = get_settings()
    name = index_name or settings.azure_search_index_name or DEFAULT_INDEX_NAME
    client = _index_client()
    index = build_knowledge_index(name)
    client.create_or_update_index(index)
    logger.info("Azure Search index ready: %s", name)
    return name


def index_exists(index_name: str | None = None) -> bool:
    _require_azure_search()
    settings = get_settings()
    name = index_name or settings.azure_search_index_name or DEFAULT_INDEX_NAME
    client = _index_client()
    try:
        client.get_index(name)
        return True
    except Exception:
        return False


def describe_index(index_name: str | None = None) -> dict[str, Any]:
    _require_azure_search()
    settings = get_settings()
    name = index_name or settings.azure_search_index_name or DEFAULT_INDEX_NAME
    client = _index_client()
    idx = client.get_index(name)
    return {
        "name": idx.name,
        "fields": [f.name for f in idx.fields],
        "field_count": len(idx.fields),
    }


def _search_client():
    """Single SearchClient factory shared by every write path to the knowledge index."""
    from azure.search.documents import SearchClient

    settings = get_settings()
    return SearchClient(
        endpoint=settings.azure_search_endpoint,
        index_name=settings.azure_search_index_name or DEFAULT_INDEX_NAME,
        credential=_credential(),
    )


def _to_index_doc(row: Any) -> dict[str, Any]:
    """Map a knowledge_documents row to the index schema (key id = doc_id)."""
    return {
        "id": row["doc_id"],
        "doc_id": row["doc_id"],
        "title": row["title"],
        "content": row["content"],
        "domain": row["domain"],
        "source": row["source"],
    }


# Azure rejects indexing batches above 1000 actions.
_MAX_BATCH = 1000


class AzureBatchRejected(RuntimeError):
    """Azure answered HTTP 207 with per-key failures; the SDK does not raise for those."""


def _check_results(results: list, expected: int, op: str) -> None:
    """Raise unless every key succeeded. Deleting a missing key succeeds, so any failure is real."""
    failed = [getattr(r, "status_code", None) for r in results if not r.succeeded]
    if failed or len(results) != expected:
        raise AzureBatchRejected(
            f"Azure {op}: {len(failed)} of {expected} keys rejected "
            f"(status codes {sorted(set(failed))}), {len(results)} results returned"
        )


def _upload_batches(docs: list[dict[str, Any]], *, strict: bool) -> int:
    """Upload in batches of <=1000; returns accepted count. strict: raise on any rejected key."""
    accepted = 0
    with _search_client() as client:
        for start in range(0, len(docs), _MAX_BATCH):
            batch = docs[start:start + _MAX_BATCH]
            results = client.upload_documents(documents=[_to_index_doc(d) for d in batch])
            if strict:
                _check_results(results, len(batch), "upload")
            accepted += sum(1 for r in results if r.succeeded)
    return accepted


def index_chunks(docs: list[dict[str, Any]]) -> tuple[int, int]:
    """Upload rows (doc_id, title, content, domain, source) to Azure.

    All-or-raise: any rejected key raises AzureBatchRejected. Returns (succeeded, total).
    """
    if not docs:
        return 0, 0
    return _upload_batches(docs, strict=True), len(docs)


def delete_by_ids(ids: list[str]) -> int:
    """Delete documents by key; returns len(ids). Missing keys succeed, so retrying is safe.

    Transport errors and per-key rejections (AzureBatchRejected) both raise: the caller must
    know the index was not cleaned.
    """
    if not ids:
        return 0
    with _search_client() as client:
        for start in range(0, len(ids), _MAX_BATCH):
            batch = ids[start:start + _MAX_BATCH]
            results = client.delete_documents(documents=[{"id": i} for i in batch])
            _check_results(results, len(batch), "delete")
    return len(ids)


def upload_documents_from_pg(*, domain: str | None = None) -> tuple[int, int]:
    """Upload app.knowledge_documents rows to Azure Search. Returns (ok, total)."""
    _require_azure_search()
    from sqlalchemy import create_engine, text

    settings = get_settings()
    engine = create_engine(settings.migrate_database_url or settings.database_url)

    domain_filter = "WHERE domain = :domain" if domain else ""
    sql = f"""
        SELECT doc_id, title, content, domain, source
        FROM app.knowledge_documents
        {domain_filter}
        ORDER BY doc_id
    """
    params: dict[str, Any] = {"domain": domain} if domain else {}

    with engine.connect() as conn:
        rows = conn.execute(text(sql), params).mappings().all()

    # Bulk script contract: report (ok, total) instead of raising on per-key rejections.
    docs = list(rows)
    if not docs:
        return 0, 0
    return _upload_batches(docs, strict=False), len(docs)
