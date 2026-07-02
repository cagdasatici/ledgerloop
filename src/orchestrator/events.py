"""Structured event logging for loop execution."""

import itertools
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class LoopEvent:
    event_id: str
    task_id: str
    state: str
    role: str
    provider: str
    iteration: int
    repair_attempt: int
    failure_fingerprint: Optional[str]
    input_refs: List[str] = field(default_factory=list)
    output_refs: List[str] = field(default_factory=list)
    status: str = "succeeded"
    cost: Dict[str, float] = field(default_factory=dict)
    message: str = ""
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "task_id": self.task_id,
            "state": self.state,
            "role": self.role,
            "provider": self.provider,
            "iteration": self.iteration,
            "repair_attempt": self.repair_attempt,
            "failure_fingerprint": self.failure_fingerprint,
            "input_refs": list(self.input_refs),
            "output_refs": list(self.output_refs),
            "status": self.status,
            "cost": dict(self.cost),
            "message": self.message,
            "created_at": self.created_at,
        }


class EventLog:
    """In-memory event log for Phase 1."""

    def __init__(self) -> None:
        self._counter = itertools.count(1)
        self.events: List[LoopEvent] = []

    def append(
        self,
        task_id: str,
        state: str,
        role: str,
        provider: str = "local",
        iteration: int = 0,
        repair_attempt: int = 0,
        failure_fingerprint: Optional[str] = None,
        status: str = "succeeded",
        message: str = "",
        cost: Optional[Dict[str, float]] = None,
        input_refs: Optional[List[str]] = None,
        output_refs: Optional[List[str]] = None,
    ) -> LoopEvent:
        event = LoopEvent(
            event_id="evt_%04d" % next(self._counter),
            task_id=task_id,
            state=state,
            role=role,
            provider=provider,
            iteration=iteration,
            repair_attempt=repair_attempt,
            failure_fingerprint=failure_fingerprint,
            status=status,
            message=message,
            cost=cost or {},
            input_refs=input_refs or [],
            output_refs=output_refs or [],
        )
        self.events.append(event)
        return event

    def to_list(self) -> List[Dict[str, Any]]:
        return [event.to_dict() for event in self.events]
