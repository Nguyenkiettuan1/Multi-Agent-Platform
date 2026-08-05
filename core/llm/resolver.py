"""Model resolution — 3-layer industry pattern.

Resolution priority (highest → lowest):
  1. Runtime override (explicit model_override param)
  2. Agent registry  (agents/registry.yaml)      — Swarm / CrewAI / Anthropic
  3. Pipeline registry (orchestrator/agent.yaml)   — LangGraph control nodes
  4. Default model     (config/models.yaml)

Fallback chain (LiteLLM pattern):
  node/agent model_fallbacks → global fallbacks → default_model
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from core.llm.availability import pick_available_model_ref
from core.llm.models_config import ModelEntry, ModelsConfig, load_models_config, resolve_model_ref
from core.registry.agents import AgentDefinition, load_registry
from core.registry.pipeline import PipelineNode, get_pipeline_node
from workflows.state import AgentId


class ResolveSource(str, Enum):
    OVERRIDE = "override"
    AGENT = "agent"
    PIPELINE = "pipeline"
    DEFAULT = "default"


@dataclass
class ModelResolution:
    """Resolve result — records where the model came from."""

    role: str
    primary: ModelEntry
    fallbacks: list[ModelEntry]
    source: ResolveSource
    source_ref: str  # agent id or pipeline node name


def resolve_model(
    role: str,
    *,
    agent_id: AgentId | None = None,
    model_override: str | None = None,
    cfg: ModelsConfig | None = None,
) -> ModelResolution:
    cfg = cfg or load_models_config()

    # 1. Runtime override
    if model_override:
        primary_ref = model_override
        source = ResolveSource.OVERRIDE
        source_ref = model_override
        local_fallbacks: list[str] = []
    # 2. Agent registry (worker agents)
    elif agent_id and agent_id in load_registry():
        agent = load_registry()[agent_id]
        primary_ref, local_fallbacks = _agent_model_refs(agent)
        source = ResolveSource.AGENT
        source_ref = agent_id.value
    # 3. Pipeline registry (control nodes)
    elif get_pipeline_node(role):
        node = get_pipeline_node(role)
        primary_ref = node.model or cfg.default_model
        local_fallbacks = list(node.model_fallbacks)
        source = ResolveSource.PIPELINE
        source_ref = role
    # 4. Default
    else:
        primary_ref = cfg.default_model
        local_fallbacks = []
        source = ResolveSource.DEFAULT
        source_ref = "default"

    primary_ref = pick_available_model_ref(primary_ref, cfg=cfg)
    primary = resolve_model_ref(cfg, primary_ref)
    fallback_refs = _build_fallback_chain(cfg, primary.ref, local_fallbacks)
    fallbacks = [
        resolve_model_ref(cfg, pick_available_model_ref(ref, cfg=cfg))
        for ref in fallback_refs
    ]

    return ModelResolution(
        role=role,
        primary=primary,
        fallbacks=fallbacks,
        source=source,
        source_ref=source_ref,
    )


def _agent_model_refs(agent: AgentDefinition) -> tuple[str, list[str]]:
    if agent.model:
        return agent.model, list(agent.model_fallbacks)
    return "balanced", []


def _build_fallback_chain(
    cfg: ModelsConfig,
    primary_ref: str,
    local_fallbacks: list[str],
) -> list[str]:
    """Merge local + global fallbacks, dedupe, exclude primary."""
    seen = {primary_ref}
    chain: list[str] = []

    for ref in local_fallbacks + cfg.fallbacks.get(primary_ref, []):
        resolved = cfg.profiles.get(ref, ref)
        if resolved not in seen:
            seen.add(resolved)
            chain.append(ref)

    return chain
