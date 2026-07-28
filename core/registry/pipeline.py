"""Pipeline node registry — control-plane agents from orchestrator config."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PIPELINE_PATH = ROOT / "agents" / "orchestrator" / "agent.yaml"


@dataclass
class PipelineNode:
    name: str
    role: str
    description: str
    model: str | None = None
    model_fallbacks: list[str] = field(default_factory=list)


@lru_cache
def load_pipeline_registry() -> dict[str, PipelineNode]:
    if not PIPELINE_PATH.exists():
        return {}

    data = yaml.safe_load(PIPELINE_PATH.read_text(encoding="utf-8")) or {}
    nodes: dict[str, PipelineNode] = {}

    for name, cfg in data.get("agents", {}).items():
        model = cfg.get("model")
        if isinstance(model, dict):
            # Legacy format: model.tier + deployment — map to profile if possible
            model = cfg.get("model", {}).get("deployment", "balanced")

        nodes[name] = PipelineNode(
            name=name,
            role=cfg.get("role", "control"),
            description=cfg.get("description", ""),
            model=model,
            model_fallbacks=cfg.get("model_fallbacks", []),
        )
    return nodes


def get_pipeline_node(name: str) -> PipelineNode | None:
    return load_pipeline_registry().get(name)
