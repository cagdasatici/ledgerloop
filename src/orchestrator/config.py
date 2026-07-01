"""Configuration contracts for the orchestrator."""

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass(frozen=True)
class ModelPricing:
    """Per-million token pricing for a provider model."""

    input_per_million: float = 0.0
    output_per_million: float = 0.0
    cache_read_per_million: float = 0.0
    cache_write_per_million: float = 0.0


@dataclass(frozen=True)
class ProviderModelConfig:
    """Static capability and pricing metadata for a provider model."""

    provider: str
    model_id: str
    pricing: ModelPricing = field(default_factory=ModelPricing)
    context_window: int = 128000
    supports_cache: bool = False
    supports_tools: bool = False
    supports_streaming: bool = False
    modalities: List[str] = field(default_factory=lambda: ["text"])


@dataclass(frozen=True)
class BudgetConfig:
    """Hard run-level limits."""

    max_usd: float = 1.0
    max_input_tokens: int = 200000
    max_output_tokens: int = 50000
    max_repair_attempts: int = 3
    max_iterations: int = 8
    reserved_final_report_usd: float = 0.0


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
        supports_cache=True,
    )
    balanced = ProviderModelConfig(
        provider="fake",
        model_id="balanced-code-model",
        pricing=ModelPricing(input_per_million=0.25, output_per_million=0.75),
        supports_cache=True,
        supports_tools=True,
    )
    strong = ProviderModelConfig(
        provider="fake",
        model_id="strong-audit-model",
        pricing=ModelPricing(input_per_million=1.00, output_per_million=3.00),
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
