"""Provider adapter contracts and deterministic fake provider."""

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional

from orchestrator.budget import UsageMetadata
from orchestrator.safety import ProposedAction


@dataclass(frozen=True)
class RetryPolicy:
    """Provider retry policy without sleeping inside the core loop."""

    max_attempts: int = 2
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 30.0

    def can_retry(self, error: "ProviderError", attempt: int) -> bool:
        return error.retryable and attempt < self.max_attempts

    def delay_for(self, error: "ProviderError", attempt: int) -> float:
        if error.retry_after_seconds is not None:
            return min(error.retry_after_seconds, self.max_delay_seconds)
        delay = self.base_delay_seconds * (2 ** max(0, attempt - 1))
        return min(delay, self.max_delay_seconds)


class ProviderError(RuntimeError):
    """Base provider failure with explicit retry and repair semantics."""

    kind = "provider_error"
    retryable = False
    consumes_repair_attempt = False

    def __init__(
        self,
        message: str,
        provider_model: str = "",
        retry_after_seconds: Optional[float] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.provider_model = provider_model
        self.retry_after_seconds = retry_after_seconds

    @property
    def failure_fingerprint(self) -> str:
        model = self.provider_model or "unknown"
        return "provider:%s:%s" % (self.kind, model)


class ProviderTimeoutError(ProviderError):
    kind = "timeout"
    retryable = True
    consumes_repair_attempt = False


class ProviderRateLimitError(ProviderError):
    kind = "rate_limit"
    retryable = True
    consumes_repair_attempt = False


class ProviderAuthError(ProviderError):
    kind = "auth"
    retryable = False
    consumes_repair_attempt = False


class ProviderRefusalError(ProviderError):
    kind = "refusal"
    retryable = False
    consumes_repair_attempt = True


class ProviderMalformedOutputError(ProviderError):
    kind = "malformed_output"
    retryable = True
    consumes_repair_attempt = True


@dataclass(frozen=True)
class ProviderResponse:
    """Provider output plus usage metadata."""

    text: str
    usage: UsageMetadata
    metadata: Dict[str, str]
    actions: List[ProposedAction] = field(default_factory=list)


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

    def __init__(
        self,
        model_id: str = "balanced-code-model",
        response_prefix: str = "fake",
        actions: Optional[Iterable[ProposedAction]] = None,
        failures: Optional[Iterable[ProviderError]] = None,
    ):
        self.model_id = model_id
        self.response_prefix = response_prefix
        self.actions = list(actions or [])
        self.failures = list(failures or [])

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
        if role == "builder" and self.failures:
            error = self.failures.pop(0)
            if not error.provider_model:
                error.provider_model = self.model_id
            raise error
        usage = self.estimate_usage(prompt, max_output_tokens=max_output_tokens)
        marker = metadata.get("task_id", "task") if metadata else "task"
        text = "%s:%s:%s:%s" % (self.response_prefix, self.model_id, role, marker)
        return ProviderResponse(
            text=text,
            usage=usage,
            metadata={"provider": "fake", "model_id": self.model_id},
            actions=list(self.actions),
        )
