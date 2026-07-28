"""SQL MCP Server — read-only database access for agents."""

from __future__ import annotations

import json
from typing import Any

import _bootstrap  # noqa: F401

from core.mcp.sql_tools import SqlToolError, describe_table, execute_query, list_tables
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

server = Server("sql-server")


@server.list_tools()
async def list_tools() -> list[Tool]:
    from config import get_settings

    settings = get_settings()
    return [
        Tool(
            name="list_tables",
            description="List all tables in the database.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="describe_table",
            description="Get column info for a table.",
            inputSchema={
                "type": "object",
                "properties": {"table_name": {"type": "string"}},
                "required": ["table_name"],
            },
        ),
        Tool(
            name="execute_query",
            description=f"Execute read-only SELECT. Max {settings.mcp_max_rows} rows.",
            inputSchema={
                "type": "object",
                "properties": {"sql": {"type": "string"}},
                "required": ["sql"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    try:
        if name == "list_tables":
            return [TextContent(type="text", text=json.dumps(list_tables(), ensure_ascii=False))]
        if name == "describe_table":
            result = describe_table(arguments["table_name"])
            return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, default=str))]
        if name == "execute_query":
            rows = execute_query(arguments["sql"])
            return [TextContent(type="text", text=json.dumps(rows, ensure_ascii=False, default=str))]
    except SqlToolError as exc:
        return [TextContent(type="text", text=json.dumps({"error": str(exc)}))]

    raise ValueError(f"Unknown tool: {name}")


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
