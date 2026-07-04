"""Structured event logging for loop execution."""

import itertools
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


SECRET_VALUE_RE = re.compile(
    r"(?i)\b(api[_-]?key|token|secret|password)\s*[:=]\s*([^\s,;]+)"
)
SECRET_TOKEN_RE = re.compile(
    r"\b(sk-[A-Za-z0-9_-]{12,}|xox[abprs]-[A-Za-z0-9-]{12,}|gh[pousr]_[A-Za-z0-9_]{12,})\b"
)


def new_run_id() -> str:
    return "run_" + uuid.uuid4().hex[:12]


def redact_text(text: str) -> str:
    """Redact common secret shapes before durable persistence."""

    redacted = SECRET_VALUE_RE.sub(lambda match: "%s=[REDACTED]" % match.group(1), text)
    return SECRET_TOKEN_RE.sub("[REDACTED]", redacted)


@dataclass(frozen=True)
class LoopEvent:
    event_id: str
    project_id: str
    run_id: str
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
            "project_id": self.project_id,
            "run_id": self.run_id,
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

    def __init__(self, project_id: str = "loop-orchestrator", run_id: Optional[str] = None) -> None:
        self.project_id = project_id
        self.run_id = run_id or new_run_id()
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
            project_id=self.project_id,
            run_id=self.run_id,
            task_id=task_id,
            state=state,
            role=role,
            provider=provider,
            iteration=iteration,
            repair_attempt=repair_attempt,
            failure_fingerprint=failure_fingerprint,
            status=status,
            message=redact_text(message),
            cost=cost or {},
            input_refs=input_refs or [],
            output_refs=output_refs or [],
        )
        self.events.append(event)
        return event

    def to_list(self) -> List[Dict[str, Any]]:
        return [event.to_dict() for event in self.events]
