"""Shared SQLAlchemy engines — single place for DB connection policy."""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy import Engine, create_engine

from config import get_settings


def to_psycopg_conninfo(url: str) -> str:
    """Convert SQLAlchemy URL (postgresql+psycopg://) to libpq conninfo for psycopg pool."""
    if url.startswith("postgresql+psycopg://"):
        return "postgresql://" + url[len("postgresql+psycopg://") :]
    if url.startswith("postgres+psycopg://"):
        return "postgres://" + url[len("postgres+psycopg://") :]
    return url


@lru_cache
def get_app_read_engine() -> Engine:
    """Read-only app schema (agent_reader) — search, list."""
    return create_engine(get_settings().database_url, hide_parameters=True)


@lru_cache
def get_app_write_engine() -> Engine:
    """Write app schema — ingest, migrations, admin."""
    settings = get_settings()
    return create_engine(settings.migrate_database_url or settings.database_url, hide_parameters=True)


@lru_cache
def get_platform_engine() -> Engine:
    """Platform schema — feedback, audit, checkpointer."""
    settings = get_settings()
    if not settings.platform_database_url:
        raise RuntimeError("PLATFORM_DATABASE_URL is not configured")
    return create_engine(settings.platform_database_url, hide_parameters=True)


def platform_db_configured() -> bool:
    return bool(get_settings().platform_database_url)
