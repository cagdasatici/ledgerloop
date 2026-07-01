"""Safety policy and environment isolation checks."""

import os
from dataclasses import dataclass
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


class SafetyPolicy:
    """Classifies actions and blocks unsafe execution."""

    def __init__(self, config: Optional[SafetyConfig] = None, project_root: str = "."):
        self.config = config or SafetyConfig()
        self.project_root = os.path.abspath(project_root)

    def classify_action(self, action: str, command: str = "") -> str:
        action_l = action.lower()
        command_l = command.lower()
        if any(term in action_l or term in command_l for term in ["push", "deploy", "delete"]):
            return "high"
        if any(term in action_l or term in command_l for term in ["install", "dependency"]):
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
