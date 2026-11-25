"""DB worker — uses shared sql-mcp tools layer."""

from __future__ import annotations

import logging

from core.mcp.sql_query_builder import build_sql
from core.mcp.sql_tools import SqlToolError, execute_query_json
from core.skills.loader import load_skill_instructions
from workflows.llm_service import complete_worker_task
from workflows.state import AgentId, SubTask, WorkerResult

logger = logging.getLogger(__name__)

# What the user sees when the step breaks; the exception itself (SQL, schema names, paths) only goes to the log.
GENERIC_WORKER_ERROR = "The database lookup failed. Please try again."


async def run_db_worker(task: SubTask, *, chat_history: list[dict] | None = None) -> WorkerResult:
    skill = load_skill_instructions("database-query")
    tools_called: list[str] = ["execute_query"]

    try:
        sql = build_sql(task.description)
        logger.info("db-worker SQL: %s", sql[:200])
        db_data = execute_query_json(sql)

        llm_summary = await complete_worker_task(
            AgentId.DB_WORKER,
            task.description,
            skill_name="database-query",
            extra_context=f"SQL:\n{sql}\n\nResults:\n{db_data}",
            chat_history=chat_history,
        )
        summary = llm_summary or f"DB results: {db_data}"

        return WorkerResult(
            task_id=task.id,
            agent=AgentId.DB_WORKER,
            summary=summary,
            success=True,
            sources=["database-query", "sql-mcp"] if skill else ["sql-mcp"],
            tools_called=tools_called,
        )
    except SqlToolError as exc:
        return WorkerResult(
            task_id=task.id,
            agent=AgentId.DB_WORKER,
            summary=f"Rejected: {exc}",
            success=False,
            tools_called=tools_called,
        )
    except Exception:
        logger.exception("db-worker failed")
        return WorkerResult(
            task_id=task.id,
            agent=AgentId.DB_WORKER,
            summary=GENERIC_WORKER_ERROR,
            success=False,
            tools_called=tools_called,
        )
