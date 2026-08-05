"""MCP hub data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class McpServerConfig:
    id: str
    description: str = ""
    kind: Literal["internal", "mcp"] = "mcp"
    runtime: Literal["cursor", "app", "both"] = "app"
    enabled: bool = False
    transport: str = "stdio"
    command: str = ""
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    tools: list[dict] = field(default_factory=list)


@dataclass
class ToolDescriptor:
    id: str
    server_id: str
    name: str
    description: str
    input_schema: dict[str, Any]
    kind: Literal["internal", "mcp"] = "internal"


@dataclass
class ToolCallResult:
    tool_id: str
    success: bool
    content: str
    error: str = ""
