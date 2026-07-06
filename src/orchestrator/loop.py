"""Bounded mock-first loop runner."""

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from orchestrator.artifacts import ArtifactStore
from orchestrator.budget import BudgetExceeded, BudgetLedger
from orchestrator.config import OrchestratorConfig, default_config
from orchestrator.events import EventLog, utc_now_iso
from orchestrator.memory import MemoryStore
from orchestrator.prompts import PromptBundle, assemble_prompt_bundle, stable_memory_summary
from orchestrator.providers import FakeProviderAdapter, ProviderAdapter, ProviderError, RetryPolicy
from orchestrator.router import Router, RoutingDecision
from orchestrator.safety import ActionSafetyBlocked, ProposedAction, SafetyPolicy


@dataclass(frozen=True)
class TaskEnvelope:
    task_id: str
    project_id: str
    user_goal: str
    requested_mode: str = "auto"
    risk_tolerance: str = "normal"
    constraints: List[str] = field(default_factory=list)
    artifacts: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso)

    @classmethod
    def from_goal(cls, project_id: str, user_goal: str, task_id: str = "task_0001") -> "TaskEnvelope":
        return cls(task_id=task_id, project_id=project_id, user_goal=user_goal)

    def to_dict(self) -> Dict[str, object]:
        return {
            "task_id": self.task_id,
            "project_id": self.project_id,
            "user_goal": self.user_goal,
            "requested_mode": self.requested_mode,
            "risk_tolerance": self.risk_tolerance,
            "constraints": list(self.constraints),
            "artifacts": list(self.artifacts),
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class ValidationResult:
    passed: bool
    message: str = ""
    failure_fingerprint: Optional[str] = None

    @classmethod
    def success(cls, message: str = "ok") -> "ValidationResult":
        return cls(True, message, None)

    @classmethod
    def failure(cls, fingerprint: str, message: str) -> "ValidationResult":
        return cls(False, message, fingerprint)


@dataclass(frozen=True)
class LoopResult:
    status: str
    project_id: str
    run_id: str
    task_id: str
    routing: RoutingDecision
    events: List[Dict[str, object]]
    budget: Dict[str, float]
    prompt_hash: str
    cacheable_hash: str
    message: str
    artifacts: List[Dict[str, object]] = field(default_factory=list)
    changed_artifacts: List[Dict[str, object]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "status": self.status,
            "project_id": self.project_id,
            "run_id": self.run_id,
            "task_id": self.task_id,
            "routing": self.routing.to_dict(),
            "events": list(self.events),
            "budget": dict(self.budget),
            "prompt_hash": self.prompt_hash,
            "cacheable_hash": self.cacheable_hash,
            "message": self.message,
            "artifacts": list(self.artifacts),
            "changed_artifacts": list(self.changed_artifacts),
        }


Validator = Callable[[int, str], ValidationResult]


class LoopRunner:
    """Runs a bounded local loop using provider adapters and structured events."""

    def __init__(
        self,
        config: Optional[OrchestratorConfig] = None,
        router: Optional[Router] = None,
        memory: Optional[MemoryStore] = None,
        providers: Optional[Dict[str, ProviderAdapter]] = None,
        events: Optional[EventLog] = None,
        safety: Optional[SafetyPolicy] = None,
        retry_policy: Optional[RetryPolicy] = None,
    ) -> None:
        self.config = config or default_config()
        self.router = router or Router(
            pricing={
                model_id: provider.pricing
                for model_id, provider in self.config.providers.items()
            },
            capabilities={
                model_id: dict(provider.capabilities)
                for model_id, provider in self.config.providers.items()
            },
        )
        self.memory = memory or MemoryStore(project_id=self.config.project_id)
        self.providers = providers or {
            model_id: FakeProviderAdapter(model_id=model_id)
            for model_id in self.config.providers.keys()
        }
        self.events = events or EventLog(project_id=self.config.project_id)
        self.safety = safety or SafetyPolicy(self.config.safety)
        self.retry_policy = retry_policy or RetryPolicy()
        self.budget = BudgetLedger(self.config.budget, self.config.providers)
        self.artifacts = ArtifactStore()

    def run(
        self,
        user_goal: str,
        task_id: str = "task_0001",
        validator: Optional[Validator] = None,
        auditor: Optional[Validator] = None,
    ) -> LoopResult:
        envelope = TaskEnvelope.from_goal(self.config.project_id, user_goal, task_id=task_id)
        self.events.append(task_id, "intake", "router", message="Task envelope created.")

        routing = self.router.route_task(user_goal)
        self.events.append(
            task_id,
            "route",
            "router",
            message=routing.reason,
            cost={"estimated_usd": routing.estimated_cost_usd},
        )
        if routing.requires_approval:
            self.events.append(
                task_id,
                "report",
                "reporter",
                status="blocked",
                message="Routing requires approval for high-risk task.",
            )
            return self._result("blocked", envelope, routing, "", "", "Approval required.")

        safety_decision = self.safety.evaluate_task(user_goal)
        self.events.append(
            task_id,
            "safety_gate",
            "safety",
            status="succeeded" if safety_decision.allowed else "blocked",
            message=safety_decision.reason,
        )
        if not safety_decision.allowed:
            self.events.append(
                task_id,
                "report",
                "reporter",
                status="blocked",
                message=safety_decision.reason,
            )
            return self._result("blocked", envelope, routing, "", "", safety_decision.reason)

        retrieved = self.memory.retrieve(user_goal)
        self.events.append(
            task_id,
            "resolve_memory",
            "memory_curator",
            message="Retrieved %d memory items." % len(retrieved),
        )

        prompt_bundle = self._build_bundle(envelope, routing, retrieved, None, {})
        provider = self._select_provider_for_phase(routing, "build")
        audit_provider = self._select_provider_for_phase(routing, "audit")
        plan_provider = self._select_provider_for_phase(routing, "plan")
        self.events.append(
            task_id,
            "plan",
            "planner",
            provider=plan_provider.model_id,
            message="Prompt bundle assembled.",
            output_refs=[prompt_bundle.full_hash],
        )
        repair_attempts: Dict[str, int] = {}
        last_failure: Optional[ValidationResult] = None
        last_message = ""
        final_status = "failed"

        for iteration in range(1, self.config.budget.max_iterations + 1):
            if last_failure is not None:
                # Closed-loop repair: rebuild the dynamic sections so the next
                # attempt sees what failed. Cacheable prefix stays stable.
                prompt_bundle = self._build_bundle(
                    envelope, routing, retrieved, last_failure, repair_attempts
                )
            try:
                response_text = self._execute_provider(
                    provider=provider,
                    prompt=prompt_bundle.full_prompt,
                    task_id=task_id,
                    iteration=iteration,
                )
            except BudgetExceeded as exc:
                final_status = "blocked"
                last_message = str(exc)
                self.events.append(
                    task_id,
                    "report",
                    "reporter",
                    iteration=iteration,
                    status=final_status,
                    message=last_message,
                )
                return self._result(
                    final_status,
                    envelope,
                    routing,
                    prompt_bundle.full_hash,
                    prompt_bundle.cacheable_hash,
                    last_message,
                )
            except ActionSafetyBlocked as exc:
                final_status = "blocked"
                last_message = exc.decision.reason
                self.events.append(
                    task_id,
                    "report",
                    "reporter",
                    iteration=iteration,
                    status=final_status,
                    message=last_message,
                )
                return self._result(
                    final_status,
                    envelope,
                    routing,
                    prompt_bundle.full_hash,
                    prompt_bundle.cacheable_hash,
                    last_message,
                )
            except ProviderError as exc:
                if exc.consumes_repair_attempt:
                    last_failure = ValidationResult.failure(
                        exc.failure_fingerprint,
                        "Provider %s failure from %s: %s"
                        % (exc.kind, provider.model_id, exc.message),
                    )
                    final_status, last_message, provider = self._handle_repair(
                        task_id, last_failure, repair_attempts, iteration, provider
                    )
                    if final_status == "repairing":
                        continue
                    break

                final_status = "blocked"
                last_message = (
                    "Provider %s failure from %s: %s"
                    % (exc.kind, provider.model_id, exc.message)
                )
                self.events.append(
                    task_id,
                    "report",
                    "reporter",
                    iteration=iteration,
                    status=final_status,
                    message=last_message,
                )
                return self._result(
                    final_status,
                    envelope,
                    routing,
                    prompt_bundle.full_hash,
                    prompt_bundle.cacheable_hash,
                    last_message,
                )

            validation = validator(iteration, response_text) if validator else ValidationResult.success()
            validation_artifact = self.artifacts.add(
                task_id,
                "validation",
                validation.message,
                summary=validation.message,
                iteration=iteration,
            )
            self.events.append(
                task_id,
                "validate",
                "auditor",
                provider="local",
                iteration=iteration,
                failure_fingerprint=validation.failure_fingerprint,
                status="succeeded" if validation.passed else "failed",
                message=validation.message,
                output_refs=[validation_artifact.artifact_id],
            )
            if not validation.passed:
                last_failure = validation
                final_status, last_message, provider = self._handle_repair(
                    task_id, validation, repair_attempts, iteration, provider
                )
                if final_status == "repairing":
                    continue
                break

            audit = auditor(iteration, response_text) if auditor else ValidationResult.success("audit ok")
            audit_artifact = self.artifacts.add(
                task_id,
                "audit",
                audit.message,
                summary=audit.message,
                iteration=iteration,
            )
            self.events.append(
                task_id,
                "audit",
                "auditor",
                provider=audit_provider.model_id,
                iteration=iteration,
                failure_fingerprint=audit.failure_fingerprint,
                status="succeeded" if audit.passed else "failed",
                message=audit.message,
                output_refs=[audit_artifact.artifact_id],
            )
            if not audit.passed:
                last_failure = audit
                final_status, last_message, provider = self._handle_repair(
                    task_id, audit, repair_attempts, iteration, provider
                )
                if final_status == "repairing":
                    continue
                break

            self.events.append(
                task_id,
                "consolidate_memory",
                "memory_curator",
                iteration=iteration,
                message="No new lesson proposed in mock run.",
            )
            final_status = "succeeded"
            last_message = "Task completed and audited."
            break
        else:
            final_status = "blocked"
            last_message = "Iteration limit reached."

        report_artifact = self.artifacts.add(
            task_id,
            "report",
            "%s: %s" % (final_status, last_message),
            summary="Final report (%s)." % final_status,
        )
        self.events.append(
            task_id,
            "report",
            "reporter",
            status=final_status,
            message=last_message,
            output_refs=[report_artifact.artifact_id],
        )
        return self._result(
            final_status,
            envelope,
            routing,
            prompt_bundle.full_hash,
            prompt_bundle.cacheable_hash,
            last_message,
        )

    def _execute_provider(
        self,
        provider: ProviderAdapter,
        prompt: str,
        task_id: str,
        iteration: int,
    ) -> str:
        estimate = provider.estimate_usage(prompt)
        estimated_usd = self.budget.assert_can_spend(provider.model_id, estimate, "execute")
        response = self._complete_provider_with_retry(
            provider=provider,
            prompt=prompt,
            task_id=task_id,
            iteration=iteration,
        )
        record = self.budget.record_actual(
            provider.model_id,
            response.usage,
            reason="execute",
            estimated_usd=estimated_usd,
        )
        self.events.append(
            task_id,
            "provider_call",
            "builder",
            provider=provider.model_id,
            iteration=iteration,
            status="succeeded",
            cost={"estimated_usd": record.estimated_usd, "actual_usd": record.actual_usd},
            message="Provider response received.",
        )
        self._gate_proposed_actions(task_id, response.actions, iteration)
        artifact = self.artifacts.add(
            task_id,
            "edit",
            response.text,
            summary="Builder output from %s." % provider.model_id,
            iteration=iteration,
        )
        self.events.append(
            task_id,
            "execute",
            "builder",
            provider=provider.model_id,
            iteration=iteration,
            status="succeeded",
            message=response.text,
            output_refs=[artifact.artifact_id],
        )
        return response.text

    def _complete_provider_with_retry(
        self,
        provider: ProviderAdapter,
        prompt: str,
        task_id: str,
        iteration: int,
    ):
        attempt = 1
        while True:
            try:
                return provider.complete(prompt, role="builder", metadata={"task_id": task_id})
            except ProviderError as exc:
                if not exc.provider_model:
                    exc.provider_model = provider.model_id
                self.events.append(
                    task_id,
                    "provider_error",
                    "builder",
                    provider=provider.model_id,
                    iteration=iteration,
                    status=exc.kind,
                    message=exc.message,
                    failure_fingerprint=exc.failure_fingerprint,
                )
                if self.retry_policy.can_retry(exc, attempt):
                    delay = self.retry_policy.delay_for(exc, attempt)
                    self.events.append(
                        task_id,
                        "provider_retry",
                        "builder",
                        provider=provider.model_id,
                        iteration=iteration,
                        status="scheduled",
                        message=(
                            "Retrying provider %s after %.2fs due to %s."
                            % (provider.model_id, delay, exc.kind)
                        ),
                        failure_fingerprint=exc.failure_fingerprint,
                    )
                    attempt += 1
                    continue
                raise

    def _gate_proposed_actions(
        self,
        task_id: str,
        actions: List[ProposedAction],
        iteration: int,
    ) -> None:
        for action in actions:
            decision = self.safety.evaluate_action(action)
            self.events.append(
                task_id,
                "action_safety_gate",
                "safety",
                iteration=iteration,
                status="succeeded" if decision.allowed else "blocked",
                message="%s: %s" % (action.action_id, decision.reason),
                input_refs=[action.action_id],
            )
            if not decision.allowed:
                raise ActionSafetyBlocked(decision)

    def _handle_repair(
        self,
        task_id: str,
        result: ValidationResult,
        repair_attempts: Dict[str, int],
        iteration: int,
        provider: ProviderAdapter,
    ) -> tuple:
        fingerprint = result.failure_fingerprint or "unknown"
        attempts = repair_attempts.get(fingerprint, 0)
        if attempts >= self.config.budget.max_repair_attempts:
            stronger = self._stronger_provider(provider)
            if stronger is not None:
                # Spec: escalate to a stronger tier before pausing at a gate.
                repair_attempts[fingerprint] = 0
                message = "Escalating %s from %s to %s after repair limit." % (
                    fingerprint,
                    provider.model_id,
                    stronger.model_id,
                )
                self.events.append(
                    task_id,
                    "repair",
                    "planner",
                    provider=stronger.model_id,
                    iteration=iteration,
                    repair_attempt=attempts,
                    failure_fingerprint=fingerprint,
                    status="escalated",
                    message=message,
                )
                return "repairing", message, stronger

            message = "Repair limit reached for %s and no stronger tier available." % fingerprint
            self.events.append(
                task_id,
                "repair",
                "planner",
                iteration=iteration,
                repair_attempt=attempts,
                failure_fingerprint=fingerprint,
                status="blocked",
                message=message,
            )
            return "blocked", message, provider

        attempts += 1
        repair_attempts[fingerprint] = attempts
        self.events.append(
            task_id,
            "repair",
            "planner",
            iteration=iteration,
            repair_attempt=attempts,
            failure_fingerprint=fingerprint,
            status="scheduled",
            message="Scheduling repair attempt %d for %s." % (attempts, fingerprint),
        )
        return "repairing", "Repair scheduled.", provider

    def _stronger_provider(self, current: ProviderAdapter) -> Optional[ProviderAdapter]:
        """Return the cheapest configured provider stronger than the current one.

        Strength is ordered by configured input pricing; the mock and any real
        config both express tiering that way.
        """

        current_config = self.config.providers.get(current.model_id)
        if current_config is None:
            return None
        current_price = current_config.pricing.input_per_million
        candidates = [
            (provider_config.pricing.input_per_million, model_id)
            for model_id, provider_config in self.config.providers.items()
            if provider_config.pricing.input_per_million > current_price
            and model_id in self.providers
        ]
        if not candidates:
            return None
        candidates.sort()
        return self.providers[candidates[0][1]]

    def _build_bundle(
        self,
        envelope: TaskEnvelope,
        routing: RoutingDecision,
        retrieved: List,
        last_failure: Optional[ValidationResult],
        repair_attempts: Dict[str, int],
    ) -> PromptBundle:
        repair_context: Dict[str, object] = {}
        if last_failure is not None:
            repair_context = {
                "failure_fingerprint": last_failure.failure_fingerprint,
                "failure_message": last_failure.message,
                "repair_attempts": dict(repair_attempts),
            }
        return assemble_prompt_bundle(
            system_contract={
                "role": "bounded local code-build-audit orchestrator",
                "safety": "use configured gates and budgets",
                "output": "structured loop events",
            },
            project_summary={"project_id": self.config.project_id},
            memory_summary=stable_memory_summary(self.memory.to_prompt_records(retrieved)),
            dynamic_context={
                "recent_events": self.events.to_list()[-3:],
                "repair_context": repair_context,
            },
            current_task_payload={"task": envelope.to_dict(), "routing": routing.to_dict()},
        )

    def _select_provider(self, routing: RoutingDecision) -> ProviderAdapter:
        for model_id in routing.provider_preference:
            if model_id in self.providers:
                return self.providers[model_id]
        if self.providers:
            return next(iter(self.providers.values()))
        return FakeProviderAdapter()

    def _select_provider_for_phase(
        self, routing: RoutingDecision, phase: str
    ) -> ProviderAdapter:
        preference = routing.phase_providers.get(phase) or routing.provider_preference
        for model_id in preference:
            if model_id in self.providers:
                return self.providers[model_id]
        return self._select_provider(routing)

    def _result(
        self,
        status: str,
        envelope: TaskEnvelope,
        routing: RoutingDecision,
        prompt_hash: str,
        cacheable_hash: str,
        message: str,
    ) -> LoopResult:
        result = LoopResult(
            status=status,
            project_id=self.config.project_id,
            run_id=self.events.run_id,
            task_id=envelope.task_id,
            routing=routing,
            events=self.events.to_list(),
            budget=self.budget.summary(),
            prompt_hash=prompt_hash,
            cacheable_hash=cacheable_hash,
            message=message,
            artifacts=self.artifacts.to_list(),
            changed_artifacts=self.artifacts.changed(),
        )
        recorder = getattr(self.events, "record_run_result", None)
        if recorder:
            recorder(result)
        return result
