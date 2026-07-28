"""Model router — resolves model via 3-layer resolver + provider lookup."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from core.llm.models_config import ModelEntry, load_models_config
from core.llm.providers import BaseProvider, create_provider
from core.llm.resolver import ModelResolution, ResolveSource, resolve_model
from workflows.state import AgentId


@dataclass
class ResolvedModel:
    role: str
    model: ModelEntry
    provider: BaseProvider
    provider_configured: bool
    source: ResolveSource
    source_ref: str
    fallback_chain: list[str]


class ModelRouter:
    def __init__(self) -> None:
        self._cfg = load_models_config()
        self._providers: dict[str, BaseProvider] = {}

    def _get_provider(self, provider_name: str) -> BaseProvider:
        if provider_name not in self._providers:
            pcfg = self._cfg.providers.get(provider_name)
            if not pcfg:
                raise ValueError(f"Unknown provider: {provider_name}")
            self._providers[provider_name] = create_provider(pcfg)
        return self._providers[provider_name]

    def resolve(
        self,
        role: str,
        *,
        agent_id: AgentId | None = None,
        model_override: str | None = None,
    ) -> ResolvedModel:
        resolution = resolve_model(role, agent_id=agent_id, model_override=model_override)
        return self._to_resolved(resolution)

    def resolve_for_agent(self, agent_id: AgentId) -> ResolvedModel:
        return self.resolve(agent_id.value, agent_id=agent_id)

    def resolve_for_pipeline(self, node: str) -> ResolvedModel:
        return self.resolve(node)

    def get_fallback_models(self, resolution: ModelResolution) -> list[ResolvedModel]:
        results = []
        for entry in resolution.fallbacks:
            provider = self._get_provider(entry.provider)
            results.append(
                ResolvedModel(
                    role=resolution.role,
                    model=entry,
                    provider=provider,
                    provider_configured=provider.is_configured(),
                    source=resolution.source,
                    source_ref=resolution.source_ref,
                    fallback_chain=[],
                )
            )
        return results

    def _to_resolved(self, resolution: ModelResolution) -> ResolvedModel:
        model = resolution.primary
        provider = self._get_provider(model.provider)
        chain = [model.ref] + [f.ref for f in resolution.fallbacks]
        return ResolvedModel(
            role=resolution.role,
            model=model,
            provider=provider,
            provider_configured=provider.is_configured(),
            source=resolution.source,
            source_ref=resolution.source_ref,
            fallback_chain=chain,
        )

    def list_models(self) -> list[dict]:
        return [
            {
                "ref": m.ref,
                "provider": m.provider,
                "model_id": m.model_id,
                "tags": m.tags,
                "description": m.description,
            }
            for m in self._cfg.models.values()
        ]

    def any_provider_configured(self) -> bool:
        for name in self._cfg.providers:
            if self._get_provider(name).is_configured():
                return True
        return False


@lru_cache
def get_router() -> ModelRouter:
    return ModelRouter()
