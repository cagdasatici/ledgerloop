"""Intent-based routing policy."""

from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class RoutingDecision:
    tier: str
    roles: List[str]
    provider_preference: List[str]
    estimated_cost_usd: float
    estimated_input_tokens: int
    estimated_output_tokens: int
    requires_approval: bool
    reason: str
    risk: str
    complexity: str
    intent: str

    def to_dict(self) -> dict:
        return {
            "tier": self.tier,
            "roles": list(self.roles),
            "provider_preference": list(self.provider_preference),
            "estimated_cost_usd": self.estimated_cost_usd,
            "estimated_input_tokens": self.estimated_input_tokens,
            "estimated_output_tokens": self.estimated_output_tokens,
            "requires_approval": self.requires_approval,
            "reason": self.reason,
            "risk": self.risk,
            "complexity": self.complexity,
            "intent": self.intent,
        }


@dataclass
class Router:
    """Small deterministic router for Phase 1."""

    cheap_models: List[str] = field(default_factory=lambda: ["cheap-fast-model"])
    balanced_models: List[str] = field(default_factory=lambda: ["balanced-code-model", "cheap-fast-model"])
    strong_models: List[str] = field(default_factory=lambda: ["strong-audit-model", "balanced-code-model"])

    def route_task(self, task_description: str, user_override: str = "") -> RoutingDecision:
        text = (task_description + " " + user_override).lower()
        intent = self._intent(text)
        risk = self._risk(text)
        complexity = self._complexity(text, intent, risk)
        estimated_input = max(1000, len(task_description.split()) * 300)
        estimated_output = 1200 if complexity == "low" else 4000 if complexity == "medium" else 9000

        if risk == "high" or complexity == "high":
            tier = "high"
            roles = ["planner", "builder", "auditor"]
            providers = self.strong_models
            estimated_cost = 0.50
        elif complexity == "medium":
            tier = "medium"
            roles = ["planner", "builder", "auditor"]
            providers = self.balanced_models
            estimated_cost = 0.15
        else:
            tier = "low"
            roles = ["router", "builder"]
            providers = self.cheap_models
            estimated_cost = 0.03

        requires_approval = risk == "high"
        reason = "%s intent with %s complexity and %s risk." % (intent, complexity, risk)
        return RoutingDecision(
            tier=tier,
            roles=roles,
            provider_preference=providers,
            estimated_cost_usd=estimated_cost,
            estimated_input_tokens=estimated_input,
            estimated_output_tokens=estimated_output,
            requires_approval=requires_approval,
            reason=reason,
            risk=risk,
            complexity=complexity,
            intent=intent,
        )

    def _intent(self, text: str) -> str:
        if any(word in text for word in ["audit", "review", "red-team", "security"]):
            return "audit"
        if any(word in text for word in ["implement", "build", "add", "fix"]):
            return "edit"
        if any(word in text for word in ["test", "validate", "ci"]):
            return "test"
        if any(word in text for word in ["release", "deploy", "push"]):
            return "release"
        if any(word in text for word in ["explain", "summarize", "document"]):
            return "explain"
        return "execute"

    def _risk(self, text: str) -> str:
        high_terms = ["deploy", "production", "credential", "secret", "push", "delete", "destructive"]
        if any(term in text for term in high_terms):
            return "high"
        medium_terms = ["install", "dependency", "migration", "write", "edit", "refactor"]
        if any(term in text for term in medium_terms):
            return "medium"
        return "low"

    def _complexity(self, text: str, intent: str, risk: str) -> str:
        if risk == "high" or intent == "audit" or "refactor" in text:
            return "high"
        if "architecture" in text and intent != "explain":
            return "high"
        if intent in ("edit", "test") or any(term in text for term in ["multiple", "database"]):
            return "medium"
        return "low"
