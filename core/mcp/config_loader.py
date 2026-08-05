"""Load MCP server catalog from config/mcp_servers.yaml."""

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path

import yaml

from config.settings import ROOT_DIR
from core.mcp.models import McpServerConfig

_CATALOG_PATH = ROOT_DIR / "config" / "mcp_servers.yaml"
_ENV_PATTERN = re.compile(r"\$\{([^}]+)\}")


def _substitute_env(value: str) -> str:
    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        if key == "WORKSPACE_ROOT":
            return str(ROOT_DIR)
        return os.environ.get(key, "")

    return _ENV_PATTERN.sub(repl, value)


def _resolve_env_map(env: dict[str, str] | None) -> dict[str, str]:
    if not env:
        return {}
    return {k: _substitute_env(v) for k, v in env.items()}


@lru_cache
def load_mcp_catalog() -> dict[str, McpServerConfig]:
    if not _CATALOG_PATH.exists():
        return {}

    raw = yaml.safe_load(_CATALOG_PATH.read_text(encoding="utf-8")) or {}
    servers: dict[str, McpServerConfig] = {}

    for server_id, item in (raw.get("servers") or {}).items():
        if not isinstance(item, dict):
            continue
        kind = item.get("kind", "mcp")
        servers[server_id] = McpServerConfig(
            id=server_id,
            description=str(item.get("description", "")),
            kind=kind,
            runtime=item.get("runtime", "app"),
            enabled=bool(item.get("enabled", False)),
            transport=item.get("transport", "stdio"),
            command=str(item.get("command", "")),
            args=[_substitute_env(str(a)) for a in item.get("args", [])],
            env=_resolve_env_map(item.get("env")),
            tools=list(item.get("tools") or []),
        )
    return servers


def list_app_servers(*, include_disabled: bool = False) -> list[McpServerConfig]:
    catalog = load_mcp_catalog()
    out: list[McpServerConfig] = []
    for cfg in catalog.values():
        if cfg.runtime not in ("app", "both"):
            continue
        if not include_disabled and not cfg.enabled:
            continue
        out.append(cfg)
    return sorted(out, key=lambda s: s.id)
