"""Agent registry — fleet agents with per-agent model config."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from workflows.state import AgentId

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "agents" / "registry.yaml"


@dataclass
class AgentDefinition:
    id: AgentId
    name: str
    description: str
    skills: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    model: str | None = None
    model_fallbacks: list[str] = field(default_factory=list)
    domain: str | None = None


def load_registry() -> dict[AgentId, AgentDefinition]:
    if not REGISTRY_PATH.exists():
        return _default_registry()

    data = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8")) or {}
    agents: dict[AgentId, AgentDefinition] = {}

    for item in data.get("agents", []):
        if item.get("enabled") is False:
            continue
        agent_id = AgentId(item["id"])
        agents[agent_id] = AgentDefinition(
            id=agent_id,
            name=item["name"],
            description=item["description"].strip(),
            skills=item.get("skills", []),
            tools=item.get("tools", []),
            model=item.get("model"),
            model_fallbacks=item.get("model_fallbacks", []),
            domain=item.get("domain"),
        )
    return agents


def get_agent_model(agent_id: AgentId) -> str | None:
    agent = load_registry().get(agent_id)
    return agent.model if agent else None


def _default_registry() -> dict[AgentId, AgentDefinition]:
    return {
        AgentId.GENERAL: AgentDefinition(
            id=AgentId.GENERAL,
            name="General Assistant",
            description="Q&A, writing, explanations — like GPT",
            skills=["general-assistant"],
            model="balanced",
        ),
        AgentId.DB_WORKER: AgentDefinition(
            id=AgentId.DB_WORKER,
            name="DB Worker",
            description="Read-only PostgreSQL queries",
            skills=["database-query"],
            tools=["sql-mcp"],
            model="cheap",
        ),
        AgentId.RESEARCH_WORKER: AgentDefinition(
            id=AgentId.RESEARCH_WORKER,
            name="Research Worker",
            description="Generic document search",
            skills=["document-research"],
            tools=["search-mcp"],
            model="balanced",
        ),
        AgentId.LEGAL_WORKER: AgentDefinition(
            id=AgentId.LEGAL_WORKER,
            name="Legal Domain Agent",
            description="Legal domain — plug-in",
            skills=["legal-research"],
            tools=["search-mcp"],
            model="or-claude-sonnet",
            domain="legal",
        ),
        AgentId.ACTION_WORKER: AgentDefinition(
            id=AgentId.ACTION_WORKER,
            name="Action Worker",
            description="Notifications, API calls",
            skills=[],
            tools=["api-mcp"],
            model="fast",
        ),
        AgentId.DEFAULT: AgentDefinition(
            id=AgentId.DEFAULT,
            name="Default Agent",
            description="Fallback",
            skills=[],
            tools=[],
            model="fast",
        ),
    }


def format_registry_for_planner(agents: dict[AgentId, AgentDefinition]) -> str:
    lines = []
    for agent in agents.values():
        if agent.id == AgentId.DEFAULT:
            continue
        tag = f" [domain:{agent.domain}]" if agent.domain else ""
        model_info = f" (model: {agent.model})" if agent.model else ""
        lines.append(f"- {agent.id.value}{tag}{model_info}: {agent.description}")
    return "\n".join(lines)
