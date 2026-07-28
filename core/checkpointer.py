"""PostgreSQL checkpointer for LangGraph — Postgres prod, MemorySaver dev fallback."""

from __future__ import annotations

import logging

from langgraph.checkpoint.memory import MemorySaver

from config import get_settings

logger = logging.getLogger(__name__)


async def create_checkpointer():
    """Return AsyncPostgresSaver if configured, else MemorySaver."""
    settings = get_settings()
    if not settings.platform_database_url:
        logger.info("PLATFORM_DATABASE_URL not set — using MemorySaver")
        return MemorySaver()

    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from psycopg_pool import AsyncConnectionPool

        from core.database.engines import to_psycopg_conninfo

        pool = AsyncConnectionPool(
            conninfo=to_psycopg_conninfo(settings.platform_database_url),
            min_size=1,
            max_size=5,
            kwargs={"autocommit": True, "prepare_threshold": 0},
            open=False,
        )
        await pool.open()
        checkpointer = AsyncPostgresSaver(pool)
        await checkpointer.setup()
        logger.info("PostgresSaver checkpointer ready")
        return checkpointer
    except Exception as exc:
        logger.warning("Postgres checkpointer unavailable (%s) — using MemorySaver", exc)
        return MemorySaver()
