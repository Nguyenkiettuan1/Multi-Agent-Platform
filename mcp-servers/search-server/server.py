"""Search MCP Server — hybrid RAG + web search tools."""

from __future__ import annotations

import json
from typing import Any

import _bootstrap  # noqa: F401

from core.mcp.search_tools import search_documents
from core.search.web_search import web_search
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

server = Server("search-server")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="search_documents",
            description="Search knowledge base + optional web (Tavily). Returns citations.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "top_k": {"type": "integer", "default": 5},
                    "domain": {"type": "string"},
                    "include_web": {"type": "boolean", "default": True},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="web_search",
            description="Search the public web via Tavily API.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "top_k": {"type": "integer", "default": 5},
                },
                "required": ["query"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    if name == "search_documents":
        result = await search_documents(
            arguments["query"],
            top_k=arguments.get("top_k", 5),
            domain=arguments.get("domain"),
            include_web=arguments.get("include_web", True),
        )
        payload = {
            "backends": result.backends_used,
            "citations": [c.to_dict() for c in result.citations],
            "context": result.context_for_llm,
        }
        return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]

    if name == "web_search":
        hits = await web_search(arguments["query"], top_k=arguments.get("top_k", 5))
        return [TextContent(type="text", text=json.dumps({"results": hits}, ensure_ascii=False))]

    raise ValueError(f"Unknown tool: {name}")


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
