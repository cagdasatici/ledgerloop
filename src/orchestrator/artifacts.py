"""Structured artifact tracking for loop runs.

Artifacts are the durable products of a loop: builder edits, validation and
audit results, and the final report. Each carries a content hash so downstream
consumers (event log, memory consolidation, real provider adapters) can
reference results without duplicating their bodies.
"""

import itertools
from dataclasses import dataclass, field
from typing import Any, Dict, List

from orchestrator.events import utc_now_iso
from orchestrator.prompts import sha256_text

# Kinds that represent a changed project artifact for the final report.
CHANGED_KINDS = ("edit", "file")


@dataclass(frozen=True)
class Artifact:
    artifact_id: str
    task_id: str
    kind: str
    ref: str
    summary: str
    iteration: int
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "task_id": self.task_id,
            "kind": self.kind,
            "ref": self.ref,
            "summary": self.summary,
            "iteration": self.iteration,
            "created_at": self.created_at,
        }


class ArtifactStore:
    """In-memory artifact registry for one loop run."""

    def __init__(self) -> None:
        self._counter = itertools.count(1)
        self.artifacts: List[Artifact] = []

    def add(
        self,
        task_id: str,
        kind: str,
        content: str,
        summary: str = "",
        iteration: int = 0,
    ) -> Artifact:
        artifact = Artifact(
            artifact_id="art_%04d" % next(self._counter),
            task_id=task_id,
            kind=kind,
            ref=sha256_text(content),
            summary=summary or content[:80],
            iteration=iteration,
        )
        self.artifacts.append(artifact)
        return artifact

    def to_list(self) -> List[Dict[str, Any]]:
        return [artifact.to_dict() for artifact in self.artifacts]

    def changed(self) -> List[Dict[str, Any]]:
        """Artifacts that represent a change to project files."""

        return [artifact.to_dict() for artifact in self.artifacts if artifact.kind in CHANGED_KINDS]
