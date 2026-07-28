"""Web search — Tavily API (optional)."""

from __future__ import annotations

import logging

import httpx

from config import get_settings
from core.llm.secrets import resolve_env

logger = logging.getLogger(__name__)

TAVILY_URL = "https://api.tavily.com/search"


def web_search_enabled() -> bool:
    return bool(resolve_env("TAVILY_API_KEY"))


async def web_search(query: str, *, top_k: int | None = None) -> list[dict]:
    """Return list of {title, url, content, score}."""
    api_key = resolve_env("TAVILY_API_KEY")
    if not api_key:
        return []

    settings = get_settings()
    limit = top_k or settings.web_search_max_results

    payload = {
        "api_key": api_key,
        "query": query,
        "max_results": limit,
        "search_depth": settings.web_search_depth,
        "include_answer": False,
        "include_raw_content": True,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(TAVILY_URL, json=payload)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.warning("Web search failed: %s", exc)
        return []

    results = []
    for item in data.get("results", []):
        content = item.get("raw_content") or item.get("content") or ""
        results.append({
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "content": content,
            "score": float(item.get("score", 0.0)),
        })
    logger.info("Web search: query=%r hits=%d", query[:80], len(results))
    return results
