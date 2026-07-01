"""Budget estimation and enforcement."""

from dataclasses import dataclass
from typing import Dict, List, Optional

from orchestrator.config import BudgetConfig, ModelPricing, ProviderModelConfig


class BudgetExceeded(RuntimeError):
    """Raised when a planned or actual call exceeds hard budget limits."""


@dataclass(frozen=True)
class UsageMetadata:
    """Token usage reported or estimated for one provider call."""

    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


@dataclass(frozen=True)
class CostRecord:
    """Cost record for one budget event."""

    provider_model: str
    usage: UsageMetadata
    estimated_usd: float
    actual_usd: float
    reason: str


class BudgetLedger:
    """Tracks estimated and actual spend for a single run."""

    def __init__(self, config: BudgetConfig, providers: Dict[str, ProviderModelConfig]):
        self.config = config
        self.providers = providers
        self.records: List[CostRecord] = []
        self.actual_usd = 0.0
        self.input_tokens = 0
        self.output_tokens = 0

    def estimate_cost(self, provider_model: str, usage: UsageMetadata) -> float:
        provider = self.providers.get(provider_model)
        pricing = provider.pricing if provider else ModelPricing()
        return (
            usage.input_tokens * pricing.input_per_million
            + usage.output_tokens * pricing.output_per_million
            + usage.cache_read_tokens * pricing.cache_read_per_million
            + usage.cache_write_tokens * pricing.cache_write_per_million
        ) / 1_000_000

    def remaining_usd(self) -> float:
        return max(0.0, self.config.max_usd - self.actual_usd)

    def assert_can_spend(
        self,
        provider_model: str,
        usage: UsageMetadata,
        reason: str = "provider_call",
    ) -> float:
        estimated_usd = self.estimate_cost(provider_model, usage)
        projected_usd = self.actual_usd + estimated_usd + self.config.reserved_final_report_usd
        projected_input = self.input_tokens + usage.input_tokens
        projected_output = self.output_tokens + usage.output_tokens

        if projected_usd > self.config.max_usd:
            raise BudgetExceeded(
                "Estimated cost %.6f exceeds remaining budget %.6f for %s"
                % (estimated_usd, self.remaining_usd(), reason)
            )
        if projected_input > self.config.max_input_tokens:
            raise BudgetExceeded("Estimated input tokens exceed run budget for %s" % reason)
        if projected_output > self.config.max_output_tokens:
            raise BudgetExceeded("Estimated output tokens exceed run budget for %s" % reason)
        return estimated_usd

    def record_actual(
        self,
        provider_model: str,
        usage: UsageMetadata,
        reason: str = "provider_call",
        estimated_usd: Optional[float] = None,
    ) -> CostRecord:
        if estimated_usd is None:
            estimated_usd = self.estimate_cost(provider_model, usage)
        actual_usd = self.estimate_cost(provider_model, usage)
        self.actual_usd += actual_usd
        self.input_tokens += usage.input_tokens
        self.output_tokens += usage.output_tokens
        record = CostRecord(
            provider_model=provider_model,
            usage=usage,
            estimated_usd=estimated_usd,
            actual_usd=actual_usd,
            reason=reason,
        )
        self.records.append(record)
        if self.actual_usd > self.config.max_usd:
            raise BudgetExceeded("Actual cost exceeded run budget after %s" % reason)
        return record

    def summary(self) -> Dict[str, float]:
        return {
            "actual_usd": round(self.actual_usd, 8),
            "remaining_usd": round(self.remaining_usd(), 8),
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "records": len(self.records),
        }
