"""MCP Tool Hub — merges internal tools + MCP stdio servers for app runtime."""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import Any

from core.mcp.config_loader import list_app_servers, load_mcp_catalog
from core.mcp.internal_tools import invoke_internal, list_internal_tools
from core.mcp.models import ToolCallResult, ToolDescriptor

logger = logging.getLogger(__name__)


class ToolHub:
    """Catalog + invoke tools from multiple MCP servers."""

    def list_tools(self, *, server_filter: set[str] | None = None) -> list[ToolDescriptor]:
        catalog = load_mcp_catalog()
        enabled_servers = {s.id for s in list_app_servers(include_disabled=False)}
        internal_ids = enabled_servers | {
            sid for sid, cfg in catalog.items() if cfg.kind == "internal" and cfg.enabled
        }
        if server_filter is not None:
            internal_ids &= server_filter

        internal = list_internal_tools(internal_ids if internal_ids else None)
        external = self._list_external_tools(server_filter)
        return sorted(internal + external, key=lambda t: t.id)

    def _list_external_tools(self, server_filter: set[str] | None) -> list[ToolDescriptor]:
        out: list[ToolDescriptor] = []
        for cfg in list_app_servers():
            if cfg.kind != "mcp":
                continue
            if server_filter is not None and cfg.id not in server_filter:
                continue
            for spec in cfg.tools:
                name = str(spec.get("name", "")).strip()
                if not name:
                    continue
                out.append(
                    ToolDescriptor(
                        id=f"{cfg.id}/{name}",
                        server_id=cfg.id,
                        name=name,
                        description=str(spec.get("description", cfg.description)),
                        input_schema=dict(spec.get("input_schema") or {"type": "object", "properties": {}}),
                        kind="mcp",
                    )
                )
        return out

    async def call_tool(self, tool_id: str, arguments: dict[str, Any] | None = None) -> ToolCallResult:
        args = arguments or {}
        server_id = tool_id.split("/", 1)[0]
        catalog = load_mcp_catalog()
        cfg = catalog.get(server_id)

        if cfg is None or not cfg.enabled:
            return ToolCallResult(
                tool_id=tool_id,
                success=False,
                content="",
                error=f"Server `{server_id}` is not enabled in config/mcp_servers.yaml",
            )

        if cfg.kind == "internal" or tool_id in _internal_tool_ids():
            return await invoke_internal(tool_id, args)

        return await self._call_external_mcp(cfg, tool_id, args)

    async def _call_external_mcp(self, cfg, tool_id: str, args: dict[str, Any]) -> ToolCallResult:
        tool_name = tool_id.split("/", 1)[-1]
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ImportError:
            return ToolCallResult(
                tool_id=tool_id,
                success=False,
                content="",
                error="Package mcp is not installed",
            )

        env = {**cfg.env}
        params = StdioServerParameters(command=cfg.command, args=cfg.args, env=env or None)
        try:
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, args)
                    chunks = []
                    for block in result.content:
                        if hasattr(block, "text"):
                            chunks.append(block.text)
                    return ToolCallResult(
                        tool_id=tool_id,
                        success=not result.isError,
                        content="\n".join(chunks),
                        error="" if not result.isError else "MCP tool returned error",
                    )
        except Exception as exc:
            detail = exc
            if hasattr(exc, "exceptions") and exc.exceptions:
                detail = exc.exceptions[0]
            logger.warning("External MCP %s failed: %s", cfg.id, detail)
            return ToolCallResult(
                tool_id=tool_id,
                success=False,
                content="",
                error=f"MCP `{cfg.id}`: {detail}",
            )

    def catalog_summary(self) -> list[dict[str, Any]]:
        servers = list_app_servers(include_disabled=True)
        tools = self.list_tools()
        by_server: dict[str, int] = {}
        for t in tools:
            by_server[t.server_id] = by_server.get(t.server_id, 0) + 1

        return [
            {
                "id": s.id,
                "description": s.description,
                "kind": s.kind,
                "runtime": s.runtime,
                "enabled": s.enabled,
                "tool_count": by_server.get(s.id, 0),
            }
            for s in servers
        ]


def _internal_tool_ids() -> set[str]:
    return {t.id for t in list_internal_tools()}


@lru_cache
def get_tool_hub() -> ToolHub:
    return ToolHub()


def format_tools_for_llm(tools: list[ToolDescriptor]) -> str:
    payload = [
        {
            "id": t.id,
            "description": t.description,
            "parameters": t.input_schema,
        }
        for t in tools
    ]
    return json.dumps(payload, ensure_ascii=False, indent=2)
