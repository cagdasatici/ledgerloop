"""Bounded mock-first loop runner."""

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from orchestrator.budget import BudgetExceeded, BudgetLedger
from orchestrator.config import OrchestratorConfig, default_config
from orchestrator.events import EventLog, utc_now_iso
from orchestrator.memory import MemoryStore
from orchestrator.prompts import assemble_prompt_bundle, stable_memory_summary
from orchestrator.providers import FakeProviderAdapter, ProviderAdapter
from orchestrator.router import Router, RoutingDecision
from orchestrator.safety import SafetyPolicy


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
    task_id: str
    routing: RoutingDecision
    events: List[Dict[str, object]]
    budget: Dict[str, float]
    prompt_hash: str
    cacheable_hash: str
    message: str

    def to_dict(self) -> Dict[str, object]:
        return {
            "status": self.status,
            "task_id": self.task_id,
            "routing": self.routing.to_dict(),
            "events": list(self.events),
            "budget": dict(self.budget),
            "prompt_hash": self.prompt_hash,
            "cacheable_hash": self.cacheable_hash,
            "message": self.message,
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
    ) -> None:
        self.config = config or default_config()
        self.router = router or Router()
        self.memory = memory or MemoryStore(project_id=self.config.project_id)
        self.providers = providers or {
            model_id: FakeProviderAdapter(model_id=model_id)
            for model_id in self.config.providers.keys()
        }
        self.events = events or EventLog()
        self.safety = safety or SafetyPolicy(self.config.safety)
        self.budget = BudgetLedger(self.config.budget, self.config.providers)

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

        retrieved = self.memory.retrieve(user_goal)
        self.events.append(
            task_id,
            "resolve_memory",
            "memory_curator",
            message="Retrieved %d memory items." % len(retrieved),
        )

        prompt_bundle = assemble_prompt_bundle(
            system_contract={
                "role": "bounded local code-build-audit orchestrator",
                "safety": "use configured gates and budgets",
                "output": "structured loop events",
            },
            project_summary={"project_id": self.config.project_id},
            memory_summary=stable_memory_summary(self.memory.to_prompt_records(retrieved)),
            dynamic_context={"recent_events": self.events.to_list()[-3:]},
            current_task_payload={"task": envelope.to_dict(), "routing": routing.to_dict()},
        )
        self.events.append(
            task_id,
            "plan",
            "planner",
            message="Prompt bundle assembled.",
            output_refs=[prompt_bundle.full_hash],
        )

        provider = self._select_provider(routing)
        repair_attempts: Dict[str, int] = {}
        last_message = ""
        final_status = "failed"

        for iteration in range(1, self.config.budget.max_iterations + 1):
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

            validation = validator(iteration, response_text) if validator else ValidationResult.success()
            self.events.append(
                task_id,
                "validate",
                "auditor",
                provider="local",
                iteration=iteration,
                failure_fingerprint=validation.failure_fingerprint,
                status="succeeded" if validation.passed else "failed",
                message=validation.message,
            )
            if not validation.passed:
                final_status, last_message = self._handle_repair(
                    task_id, validation, repair_attempts, iteration
                )
                if final_status == "repairing":
                    continue
                break

            audit = auditor(iteration, response_text) if auditor else ValidationResult.success("audit ok")
            self.events.append(
                task_id,
                "audit",
                "auditor",
                provider="local",
                iteration=iteration,
                failure_fingerprint=audit.failure_fingerprint,
                status="succeeded" if audit.passed else "failed",
                message=audit.message,
            )
            if not audit.passed:
                final_status, last_message = self._handle_repair(task_id, audit, repair_attempts, iteration)
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

        self.events.append(task_id, "report", "reporter", status=final_status, message=last_message)
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
        response = provider.complete(prompt, role="builder", metadata={"task_id": task_id})
        record = self.budget.record_actual(
            provider.model_id,
            response.usage,
            reason="execute",
            estimated_usd=estimated_usd,
        )
        self.events.append(
            task_id,
            "execute",
            "builder",
            provider=provider.model_id,
            iteration=iteration,
            status="succeeded",
            cost={"estimated_usd": record.estimated_usd, "actual_usd": record.actual_usd},
            message=response.text,
        )
        return response.text

    def _handle_repair(
        self,
        task_id: str,
        result: ValidationResult,
        repair_attempts: Dict[str, int],
        iteration: int,
    ) -> tuple:
        fingerprint = result.failure_fingerprint or "unknown"
        attempts = repair_attempts.get(fingerprint, 0)
        if attempts >= self.config.budget.max_repair_attempts:
            message = "Repair limit reached for %s." % fingerprint
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
            return "blocked", message

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
        return "repairing", "Repair scheduled."

    def _select_provider(self, routing: RoutingDecision) -> ProviderAdapter:
        for model_id in routing.provider_preference:
            if model_id in self.providers:
                return self.providers[model_id]
        if self.providers:
            return next(iter(self.providers.values()))
        return FakeProviderAdapter()

    def _result(
        self,
        status: str,
        envelope: TaskEnvelope,
        routing: RoutingDecision,
        prompt_hash: str,
        cacheable_hash: str,
        message: str,
    ) -> LoopResult:
        return LoopResult(
            status=status,
            task_id=envelope.task_id,
            routing=routing,
            events=self.events.to_list(),
            budget=self.budget.summary(),
            prompt_hash=prompt_hash,
            cacheable_hash=cacheable_hash,
            message=message,
        )
