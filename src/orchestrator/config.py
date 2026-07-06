"""Configuration contracts for the orchestrator."""

import json
from dataclasses import dataclass, field, fields, replace
from pathlib import Path
from typing import Any, Dict, List


@dataclass(frozen=True)
class ModelPricing:
    """Per-million token pricing for a provider model."""

    input_per_million: float = 0.0
    output_per_million: float = 0.0
    cache_read_per_million: float = 0.0
    cache_write_per_million: float = 0.0

    def cost_for(
        self,
        input_tokens: int,
        output_tokens: int,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
    ) -> float:
        """Single source of truth for token -> USD conversion.

        Both the router's pre-flight estimate and the budget ledger's hard
        enforcement call this so their numbers can never diverge.
        """

        return (
            input_tokens * self.input_per_million
            + output_tokens * self.output_per_million
            + cache_read_tokens * self.cache_read_per_million
            + cache_write_tokens * self.cache_write_per_million
        ) / 1_000_000


@dataclass(frozen=True)
class ProviderModelConfig:
    """Static capability and pricing metadata for a provider model."""

    provider: str
    model_id: str
    pricing: ModelPricing = field(default_factory=ModelPricing)
    # Score 0-3 per phase; 0 = do not use, 1 = usable for low-complexity,
    # 2 = solid for medium, 3 = strong enough for high.
    capabilities: Dict[str, int] = field(default_factory=dict)
    context_window: int = 128000
    supports_cache: bool = False
    supports_tools: bool = False
    supports_streaming: bool = False
    modalities: List[str] = field(default_factory=lambda: ["text"])


@dataclass(frozen=True)
class BudgetConfig:
    """Hard run-level limits."""

    max_usd: float = 1.0
    global_max_usd: float = 0.0
    max_input_tokens: int = 200000
    max_output_tokens: int = 50000
    max_repair_attempts: int = 3
    max_iterations: int = 8
    reserved_final_report_usd: float = 0.02


@dataclass(frozen=True)
class SafetyConfig:
    """Controls for actions that can affect the local environment."""

    allow_network: bool = False
    allow_global_dependency_changes: bool = False
    approved_project_env_names: List[str] = field(default_factory=lambda: [".venv", "venv"])


@dataclass(frozen=True)
class OrchestratorConfig:
    """Top-level orchestrator configuration."""

    project_id: str = "loop-orchestrator"
    budget: BudgetConfig = field(default_factory=BudgetConfig)
    safety: SafetyConfig = field(default_factory=SafetyConfig)
    providers: Dict[str, ProviderModelConfig] = field(default_factory=dict)


def default_config() -> OrchestratorConfig:
    """Return a deterministic local configuration for mock-first runs."""

    cheap = ProviderModelConfig(
        provider="fake",
        model_id="cheap-fast-model",
        pricing=ModelPricing(input_per_million=0.05, output_per_million=0.10),
        capabilities={"plan": 1, "build": 1, "audit": 1},
        supports_cache=True,
    )
    balanced = ProviderModelConfig(
        provider="fake",
        model_id="balanced-code-model",
        pricing=ModelPricing(input_per_million=0.25, output_per_million=0.75),
        capabilities={"plan": 2, "build": 3, "audit": 2},
        supports_cache=True,
        supports_tools=True,
    )
    strong = ProviderModelConfig(
        provider="fake",
        model_id="strong-audit-model",
        pricing=ModelPricing(input_per_million=1.00, output_per_million=3.00),
        capabilities={"plan": 3, "build": 2, "audit": 3},
        supports_cache=True,
        supports_tools=True,
    )
    return OrchestratorConfig(
        providers={
            cheap.model_id: cheap,
            balanced.model_id: balanced,
            strong.model_id: strong,
        }
    )


def _replace_known(instance: Any, updates: Dict[str, Any]) -> Any:
    """Apply only recognised keys onto a frozen dataclass instance."""

    valid = {f.name for f in fields(instance)}
    return replace(instance, **{key: value for key, value in updates.items() if key in valid})


def _pricing_from_dict(data: Dict[str, Any]) -> ModelPricing:
    valid = {f.name for f in fields(ModelPricing)}
    return ModelPricing(**{key: float(value) for key, value in data.items() if key in valid})


def _provider_from_dict(model_id: str, data: Dict[str, Any]) -> ProviderModelConfig:
    known = {f.name for f in fields(ProviderModelConfig)}
    kwargs = {key: value for key, value in data.items() if key in known}
    kwargs["model_id"] = model_id
    kwargs.setdefault("provider", data.get("provider", "custom"))
    if "pricing" in data:
        kwargs["pricing"] = _pricing_from_dict(data["pricing"])
    return ProviderModelConfig(**kwargs)


def config_from_dict(data: Dict[str, Any]) -> OrchestratorConfig:
    """Build a config from a parsed dict, layering onto the mock defaults."""

    base = default_config()
    project_id = data.get("project_id", base.project_id)
    budget = _replace_known(base.budget, data["budget"]) if "budget" in data else base.budget
    safety = _replace_known(base.safety, data["safety"]) if "safety" in data else base.safety

    if "providers" in data:
        providers = {
            model_id: _provider_from_dict(model_id, provider_data)
            for model_id, provider_data in data["providers"].items()
        }
    else:
        providers = base.providers

    return OrchestratorConfig(
        project_id=project_id,
        budget=budget,
        safety=safety,
        providers=providers,
    )


def load_config(path: str) -> OrchestratorConfig:
    """Load an orchestrator config from a JSON or TOML file."""

    text = Path(path).read_text(encoding="utf-8")
    if path.endswith(".toml"):
        try:
            import tomllib
        except ModuleNotFoundError as exc:  # pragma: no cover - py<3.11
            raise RuntimeError("TOML config requires Python 3.11+; use JSON instead.") from exc
        data = tomllib.loads(text)
    else:
        data = json.loads(text)
    return config_from_dict(data)
