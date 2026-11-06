"""MA-AU-T13 fixes outside the chat routes: worker error text, engine parameter hiding, docs routes."""

from __future__ import annotations

import asyncio
import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DataError

import gateway.main as gateway_main
from core.database.engines import get_app_read_engine, get_app_write_engine, get_platform_engine
from workflows.state import AgentId, SubTask
from workflows.workers import db_worker, legal_worker

SECRET = "SELECT secret_col FROM hidden_schema.t WHERE token='s3cr3t'"


def _task(agent: AgentId) -> SubTask:
    return SubTask(id="t1", description="đếm khách hàng", assigned_agent=agent)


def test_db_worker_unexpected_error_is_generic_and_logged(monkeypatch, caplog):
    def boom(_description):
        raise RuntimeError(SECRET)

    monkeypatch.setattr(db_worker, "build_sql", boom)
    with caplog.at_level(logging.ERROR, logger="workflows.workers.db_worker"):
        result = asyncio.run(db_worker.run_db_worker(_task(AgentId.DB_WORKER)))

    assert result.success is False
    assert result.summary == db_worker.GENERIC_WORKER_ERROR
    assert "hidden_schema" not in result.summary
    assert any("hidden_schema" in (r.exc_text or "") for r in caplog.records)


def test_db_worker_rejection_keeps_the_curated_explanation(monkeypatch):
    # SqlToolError texts are written by us (no SQL or driver output), so users still get the hint.
    result = asyncio.run(db_worker.run_db_worker(_task(AgentId.DB_WORKER).model_copy(update={"description": "xyz?"})))

    assert result.success is False
    assert result.summary.startswith("Rejected: ")
    assert "hidden_schema" not in result.summary


def test_legal_worker_unexpected_error_is_generic_and_logged(monkeypatch, caplog):
    async def boom(*_args, **_kwargs):
        raise RuntimeError(SECRET)

    monkeypatch.setattr(legal_worker, "search_documents", boom)
    with caplog.at_level(logging.ERROR, logger="workflows.workers.legal_worker"):
        result = asyncio.run(legal_worker.run_legal_worker(_task(AgentId.LEGAL_WORKER)))

    assert result.success is False
    assert result.summary == legal_worker.GENERIC_WORKER_ERROR
    assert any("hidden_schema" in (r.exc_text or "") for r in caplog.records)


@pytest.mark.parametrize("factory", [get_platform_engine, get_app_read_engine, get_app_write_engine])
def test_engines_hide_bound_parameters(factory):
    assert factory().hide_parameters is True


def test_driver_error_text_does_not_echo_bound_values():
    # A NUL makes Postgres refuse the value; the SQLAlchemy message used to append "[parameters: ...]".
    with pytest.raises(DataError) as caught:
        with get_platform_engine().connect() as conn:
            conn.execute(text("SELECT :v"), {"v": "private-text\x00"})

    assert "private-text" not in str(caught.value)


def test_docs_are_served_only_for_local():
    assert gateway_main._docs_kwargs("local") == {}
    for env in ("production", "staging", ""):
        app = FastAPI(**gateway_main._docs_kwargs(env))
        client = TestClient(app)
        assert [client.get(p).status_code for p in ("/docs", "/redoc", "/openapi.json")] == [404, 404, 404]

    local = TestClient(FastAPI(**gateway_main._docs_kwargs("local")))
    assert [local.get(p).status_code for p in ("/docs", "/redoc", "/openapi.json")] == [200, 200, 200]


def test_real_app_follows_app_env():
    from config import get_settings

    expected = "/openapi.json" if get_settings().app_env == "local" else None
    assert gateway_main.app.openapi_url == expected
