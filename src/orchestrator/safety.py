"""Safety policy and environment isolation checks."""

import os
from dataclasses import dataclass, field
from typing import Dict, Optional

from orchestrator.config import SafetyConfig


class SafetyViolation(RuntimeError):
    """Raised when an action violates the configured safety policy."""


@dataclass(frozen=True)
class SafetyDecision:
    action: str
    risk: str
    allowed: bool
    reason: str
    action_id: str = ""


@dataclass(frozen=True)
class ProposedAction:
    """Action proposed by a builder before the orchestrator executes it."""

    action_id: str
    kind: str
    description: str
    command: str = ""
    path: str = ""
    metadata: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        return {
            "action_id": self.action_id,
            "kind": self.kind,
            "description": self.description,
            "command": self.command,
            "path": self.path,
            "metadata": dict(self.metadata),
        }


class ActionSafetyBlocked(SafetyViolation):
    """Raised when a proposed action is blocked at execution time."""

    def __init__(self, decision: SafetyDecision):
        super().__init__(decision.reason)
        self.decision = decision


DEPENDENCY_TERMS = (
    "install",
    "dependency",
    "dependencies",
    "lockfile",
    "requirements",
    "pip ",
    "pip install",
    "package",
    "packages",
    "poetry",
    "npm",
)


class SafetyPolicy:
    """Classifies actions and blocks unsafe execution."""

    def __init__(self, config: Optional[SafetyConfig] = None, project_root: str = "."):
        self.config = config or SafetyConfig()
        self.project_root = os.path.abspath(project_root)

    def evaluate_task(
        self,
        description: str,
        command: str = "",
        env: Optional[Dict[str, str]] = None,
    ) -> SafetyDecision:
        """Gate a task before execution.

        This is the single entry point the loop calls. Dependency-changing
        tasks must run inside an approved isolated environment; everything else
        is allowed through at its classified risk level.
        """

        risk = self.classify_action(description, command)
        text = (description + " " + command).lower()
        if any(term in text for term in DEPENDENCY_TERMS):
            dependency = self.verify_dependency_environment(env=env)
            if not dependency.allowed:
                return SafetyDecision("dependency_change", "high", False, dependency.reason)
            return SafetyDecision("dependency_change", risk, True, dependency.reason)
        return SafetyDecision(
            "execute", risk, True, "No isolation-sensitive action detected."
        )

    def evaluate_action(
        self,
        action: ProposedAction,
        env: Optional[Dict[str, str]] = None,
    ) -> SafetyDecision:
        """Gate a builder-proposed action at execution time."""

        risk = self.classify_action(action.kind + " " + action.description, action.command)
        text = ("%s %s %s" % (action.kind, action.description, action.command)).lower()
        if any(term in text for term in DEPENDENCY_TERMS):
            dependency = self.verify_dependency_environment(env=env)
            return SafetyDecision(
                action=action.kind,
                risk="high" if not dependency.allowed else risk,
                allowed=dependency.allowed,
                reason=dependency.reason,
                action_id=action.action_id,
            )
        if risk == "high":
            return SafetyDecision(
                action=action.kind,
                risk=risk,
                allowed=False,
                reason="High-risk action requires explicit approval before execution.",
                action_id=action.action_id,
            )
        return SafetyDecision(
            action=action.kind,
            risk=risk,
            allowed=True,
            reason="Proposed action passed execution-time safety policy.",
            action_id=action.action_id,
        )

    def classify_action(self, action: str, command: str = "") -> str:
        action_l = action.lower()
        command_l = command.lower()
        if any(
            term in action_l or term in command_l
            for term in ["push", "deploy", "delete", "rm -rf", "release"]
        ):
            return "high"
        if any(
            term in action_l or term in command_l
            for term in ["install", "dependency", "pip ", "npm ", "poetry"]
        ):
            return "medium"
        if any(term in action_l for term in ["read", "test", "inspect", "format"]):
            return "low"
        return "medium"

    def verify_dependency_environment(self, env: Optional[Dict[str, str]] = None) -> SafetyDecision:
        env = env or dict(os.environ)
        if self.config.allow_global_dependency_changes:
            return SafetyDecision(
                "dependency_change",
                "medium",
                True,
                "Global dependency changes are explicitly allowed by policy.",
            )

        virtual_env = env.get("VIRTUAL_ENV") or env.get("CONDA_PREFIX")
        if virtual_env and self._is_inside_project(virtual_env):
            return SafetyDecision(
                "dependency_change",
                "medium",
                True,
                "Active environment is inside the project.",
            )

        if env.get("LOOP_ORCHESTRATOR_CONTAINER") == "1":
            return SafetyDecision(
                "dependency_change",
                "medium",
                True,
                "Configured container environment is active.",
            )

        return SafetyDecision(
            "dependency_change",
            "high",
            False,
            "No approved project-local virtual environment or container is active.",
        )

    def assert_dependency_change_allowed(self, env: Optional[Dict[str, str]] = None) -> None:
        decision = self.verify_dependency_environment(env=env)
        if not decision.allowed:
            raise SafetyViolation(decision.reason)

    def _is_inside_project(self, path: str) -> bool:
        abs_path = os.path.abspath(path)
        try:
            return os.path.commonpath([self.project_root, abs_path]) == self.project_root
        except ValueError:
            return False
