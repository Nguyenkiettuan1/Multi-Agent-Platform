"""Azure AI Search — cloud RAG (optional)."""

from __future__ import annotations

import logging
from functools import lru_cache

from config import get_settings
from core.search.pgvector_store import SearchHit

logger = logging.getLogger(__name__)


@lru_cache
def azure_search_enabled() -> bool:
    s = get_settings()
    return bool(s.azure_search_endpoint and s.azure_search_api_key)


async def azure_search(query: str, *, top_k: int = 5) -> list[SearchHit]:
    if not azure_search_enabled():
        return []

    settings = get_settings()
    try:
        from azure.core.credentials import AzureKeyCredential
        from azure.search.documents import SearchClient

        client = SearchClient(
            endpoint=settings.azure_search_endpoint,
            index_name=settings.azure_search_index_name,
            credential=AzureKeyCredential(settings.azure_search_api_key),
        )
        results = client.search(search_text=query, top=top_k)

        hits: list[SearchHit] = []
        for r in results:
            hits.append(
                SearchHit(
                    doc_id=str(r.get("doc_id", r.get("id", ""))),
                    title=str(r.get("title", "")),
                    content=str(r.get("content", r.get("chunk", ""))),
                    source="azure_search",
                    domain=str(r.get("domain", "general")),
                    score=float(r.get("@search.score", 0.5)),
                    backend="azure_search",
                )
            )
        return hits
    except Exception as exc:
        logger.warning("Azure Search failed: %s", exc)
        return []
