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


def upload_documents_from_pg(*, domain: str | None = None) -> tuple[int, int]:
    """Upload app.knowledge_documents rows to Azure Search. Returns (ok, total)."""
    _require_azure_search()
    from sqlalchemy import create_engine, text

    from azure.search.documents import SearchClient

    settings = get_settings()
    index_name = settings.azure_search_index_name or DEFAULT_INDEX_NAME
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

    if not rows:
        return 0, 0

    client = SearchClient(
        endpoint=settings.azure_search_endpoint,
        index_name=index_name,
        credential=_credential(),
    )

    docs = [
        {
            "id": r["doc_id"],
            "doc_id": r["doc_id"],
            "title": r["title"],
            "content": r["content"],
            "domain": r["domain"],
            "source": r["source"],
        }
        for r in rows
    ]

    result = client.upload_documents(documents=docs)
    succeeded = sum(1 for r in result if r.succeeded)
    return succeeded, len(docs)
