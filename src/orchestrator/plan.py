"""Planner output schema."""

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass(frozen=True)
class PlanSpec:
    """Structured plan handed from the plan phase to the build phase."""

    goal: str
    produced_by: str
    steps: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    acceptance: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "goal": self.goal,
            "produced_by": self.produced_by,
            "steps": list(self.steps),
            "constraints": list(self.constraints),
            "acceptance": list(self.acceptance),
        }


def plan_from_provider_text(goal: str, model_id: str, text: str) -> PlanSpec:
    """Build a PlanSpec from a (mock) provider response.

    Phase 1 mock: each non-empty line of the response becomes one step. Real
    adapters will emit structured output later; this function is the single
    seam where that parsing will live.
    """

    steps = [line.strip() for line in text.splitlines() if line.strip()]
    if not steps:
        steps = [text.strip() or "no plan produced"]
    return PlanSpec(goal=goal, produced_by=model_id, steps=steps)
