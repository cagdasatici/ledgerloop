"""Provider adapter contracts and deterministic fake provider."""

from dataclasses import dataclass
from typing import Dict, Optional

from orchestrator.budget import UsageMetadata


@dataclass(frozen=True)
class ProviderResponse:
    """Provider output plus usage metadata."""

    text: str
    usage: UsageMetadata
    metadata: Dict[str, str]


class ProviderAdapter:
    """Minimal provider adapter interface."""

    model_id: str

    def estimate_usage(self, prompt: str, max_output_tokens: int = 256) -> UsageMetadata:
        raise NotImplementedError

    def complete(
        self,
        prompt: str,
        role: str,
        max_output_tokens: int = 256,
        metadata: Optional[Dict[str, str]] = None,
    ) -> ProviderResponse:
        raise NotImplementedError


class FakeProviderAdapter(ProviderAdapter):
    """Deterministic provider used for local contract tests."""

    def __init__(self, model_id: str = "balanced-code-model", response_prefix: str = "fake"):
        self.model_id = model_id
        self.response_prefix = response_prefix

    def estimate_usage(self, prompt: str, max_output_tokens: int = 256) -> UsageMetadata:
        input_tokens = max(1, len(prompt.split()))
        output_tokens = max(1, min(max_output_tokens, 64))
        cache_read_tokens = input_tokens // 2
        return UsageMetadata(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens,
        )

    def complete(
        self,
        prompt: str,
        role: str,
        max_output_tokens: int = 256,
        metadata: Optional[Dict[str, str]] = None,
    ) -> ProviderResponse:
        usage = self.estimate_usage(prompt, max_output_tokens=max_output_tokens)
        marker = metadata.get("task_id", "task") if metadata else "task"
        text = "%s:%s:%s:%s" % (self.response_prefix, self.model_id, role, marker)
        return ProviderResponse(
            text=text,
            usage=usage,
            metadata={"provider": "fake", "model_id": self.model_id},
        )
