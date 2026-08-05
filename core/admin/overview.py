"""Admin dashboard data aggregation."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from config import get_settings
from config.version import SERVICE_VERSION
from core.database.engines import get_app_write_engine, platform_db_configured
from core.intelligence.feedback_store import list_feedback_records
from core.llm.secrets import resolve_env
from core.observability.audit import list_audit
from core.observability.tracing import tracing_enabled
from core.search.embeddings import embeddings_enabled
from core.search.web_search import web_search_enabled
from core.search.azure_search import azure_search_enabled


def build_admin_overview() -> dict[str, Any]:
    settings = get_settings()
    overview: dict[str, Any] = {
        "service": "multi-agent-platform",
        "version": SERVICE_VERSION,
        "capabilities": {
            "llm": bool(
                resolve_env("OPENROUTER_API_KEY")
                or resolve_env("OPENAI_API_KEY")
                or settings.azure_openai_api_key
            ),
            "embeddings": embeddings_enabled(),
            "azure_search": azure_search_enabled(),
            "web_search": web_search_enabled(),
            "tracing": tracing_enabled(),
            "rrf_fusion": True,
        },
        "counts": {},
        "recent_feedback": [],
        "recent_audit": [],
    }

    if settings.migrate_database_url or settings.database_url:
        engine = get_app_write_engine()
        with engine.connect() as conn:
            overview["counts"]["knowledge_documents"] = conn.execute(
                text("SELECT COUNT(*) FROM app.knowledge_documents")
            ).scalar() or 0
            overview["counts"]["knowledge_with_embedding"] = conn.execute(
                text("SELECT COUNT(*) FROM app.knowledge_documents WHERE embedding IS NOT NULL")
            ).scalar() or 0
            overview["counts"]["knowledge_promoted"] = conn.execute(
                text("SELECT COUNT(*) FROM app.knowledge_documents WHERE source = 'feedback_promoted'")
            ).scalar() or 0

    if platform_db_configured():
        from core.database.engines import get_platform_engine

        with get_platform_engine().connect() as conn:
            overview["counts"]["feedback"] = conn.execute(
                text("SELECT COUNT(*) FROM platform.feedback")
            ).scalar() or 0
            overview["counts"]["feedback_rated"] = conn.execute(
                text("SELECT COUNT(*) FROM platform.feedback WHERE rating IS NOT NULL")
            ).scalar() or 0
            overview["counts"]["feedback_promoted"] = conn.execute(
                text("SELECT COUNT(*) FROM platform.feedback WHERE promoted_to_rag = TRUE")
            ).scalar() or 0
            overview["counts"]["audit_log"] = conn.execute(
                text("SELECT COUNT(*) FROM platform.audit_log")
            ).scalar() or 0

    overview["recent_feedback"] = list_feedback_records(limit=10)
    overview["recent_audit"] = list_audit(limit=10)
    return overview
