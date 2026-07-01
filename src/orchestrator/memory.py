"""Persistent memory contracts and JSON-backed store."""

import json
import os
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Callable, Dict, Iterable, List, Optional, Set

from orchestrator.events import utc_now_iso
from orchestrator.prompts import sha256_text


VOLATILE_RE = re.compile(r"\b(evt|task|mem|err)_[0-9a-fA-F_-]+\b|\b\d{4}-\d{2}-\d{2}\b")


def normalize_summary(text: str) -> str:
    cleaned = VOLATILE_RE.sub("", text.lower())
    return " ".join(cleaned.split())


def token_set(text: str) -> Set[str]:
    return set(re.findall(r"[a-z0-9_]+", normalize_summary(text)))


def text_similarity(left: str, right: str) -> float:
    left_norm = normalize_summary(left)
    right_norm = normalize_summary(right)
    if not left_norm or not right_norm:
        return 0.0
    left_tokens = token_set(left_norm)
    right_tokens = token_set(right_norm)
    overlap = len(left_tokens & right_tokens) / float(max(1, len(left_tokens | right_tokens)))
    sequence = SequenceMatcher(None, left_norm, right_norm).ratio()
    return max(overlap, sequence)


@dataclass
class MemoryItem:
    id: str
    project_id: str
    type: str
    scope: str
    summary: str
    status: str = "active"
    version: int = 1
    confidence: float = 1.0
    source_event_ids: List[str] = field(default_factory=list)
    supersedes: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    content_hash: str = ""

    def __post_init__(self) -> None:
        if not self.content_hash:
            self.content_hash = sha256_text(self.summary)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "type": self.type,
            "scope": self.scope,
            "summary": self.summary,
            "status": self.status,
            "version": self.version,
            "confidence": self.confidence,
            "source_event_ids": list(self.source_event_ids),
            "supersedes": list(self.supersedes),
            "content_hash": self.content_hash,
            "tags": list(self.tags),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryItem":
        return cls(
            id=data["id"],
            project_id=data["project_id"],
            type=data["type"],
            scope=data.get("scope", "global"),
            summary=data["summary"],
            status=data.get("status", "active"),
            version=int(data.get("version", 1)),
            confidence=float(data.get("confidence", 1.0)),
            source_event_ids=list(data.get("source_event_ids", [])),
            supersedes=list(data.get("supersedes", [])),
            tags=list(data.get("tags", [])),
            created_at=data.get("created_at", utc_now_iso()),
            updated_at=data.get("updated_at", utc_now_iso()),
            content_hash=data.get("content_hash", ""),
        )


Curator = Callable[[MemoryItem, MemoryItem, float], str]


class MemoryStore:
    """Simple memory store with semantic deduplication scaffolding."""

    def __init__(
        self,
        project_id: str,
        path: Optional[str] = None,
        duplicate_threshold: float = 0.90,
        refinement_threshold: float = 0.72,
        curator: Optional[Curator] = None,
    ) -> None:
        self.project_id = project_id
        self.path = path
        self.duplicate_threshold = duplicate_threshold
        self.refinement_threshold = refinement_threshold
        self.curator = curator
        self.items: List[MemoryItem] = []

    @classmethod
    def load(cls, project_id: str, path: str) -> "MemoryStore":
        store = cls(project_id=project_id, path=path)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            store.items = [MemoryItem.from_dict(item) for item in data.get("items", [])]
        return store

    def save(self) -> None:
        if not self.path:
            return
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        tmp_path = self.path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(
                {"project_id": self.project_id, "items": [item.to_dict() for item in self.items]},
                handle,
                sort_keys=True,
                indent=2,
            )
            handle.write("\n")
        os.replace(tmp_path, self.path)

    def active_items(self) -> List[MemoryItem]:
        return [item for item in self.items if item.status in ("active", "enforced")]

    def retrieve(self, query: str, scope: Optional[str] = None, limit: int = 8) -> List[MemoryItem]:
        scored = []
        for item in self.active_items():
            if scope and item.scope not in (scope, "global"):
                continue
            score = text_similarity(query + " " + " ".join(item.tags), item.summary)
            if scope and item.scope == scope:
                score += 0.1
            if score > 0:
                scored.append((score, item))
        scored.sort(key=lambda pair: (-pair[0], pair[1].id))
        return [item for _, item in scored[:limit]]

    def add_or_merge(self, incoming: MemoryItem) -> Dict[str, Any]:
        candidate, score = self._best_candidate(incoming)
        if candidate is None:
            self.items.append(incoming)
            self.save()
            return {"action": "created", "memory_id": incoming.id, "score": 0.0}

        relationship = self._classify_relationship(candidate, incoming, score)
        if relationship in ("duplicate", "refinement"):
            candidate.version += 1
            candidate.updated_at = utc_now_iso()
            candidate.confidence = max(candidate.confidence, incoming.confidence)
            candidate.source_event_ids = sorted(
                set(candidate.source_event_ids + incoming.source_event_ids)
            )
            if incoming.id not in candidate.supersedes and incoming.id != candidate.id:
                candidate.supersedes.append(incoming.id)
            if relationship == "refinement" and len(incoming.summary) > len(candidate.summary):
                candidate.summary = incoming.summary
            candidate.tags = sorted(set(candidate.tags + incoming.tags))
            candidate.content_hash = sha256_text(candidate.summary)
            self.save()
            return {
                "action": "merged",
                "relationship": relationship,
                "memory_id": candidate.id,
                "superseded": incoming.id,
                "score": round(score, 4),
            }

        self.items.append(incoming)
        self.save()
        return {
            "action": "created",
            "relationship": relationship,
            "memory_id": incoming.id,
            "score": round(score, 4),
        }

    def _best_candidate(self, incoming: MemoryItem) -> Any:
        best = None
        best_score = 0.0
        incoming_tags = set(incoming.tags)
        for item in self.active_items():
            if item.project_id != incoming.project_id:
                continue
            if item.type != incoming.type:
                continue
            if item.scope != incoming.scope:
                continue
            if incoming_tags and item.tags and not incoming_tags.intersection(item.tags):
                continue
            score = text_similarity(item.summary, incoming.summary)
            if score > best_score:
                best = item
                best_score = score
        if best_score >= self.refinement_threshold:
            return best, best_score
        return None, 0.0

    def _classify_relationship(
        self, existing: MemoryItem, incoming: MemoryItem, score: float
    ) -> str:
        if self.curator:
            return self.curator(existing, incoming, score)
        if score >= self.duplicate_threshold:
            return "duplicate"
        if score >= self.refinement_threshold:
            return "refinement"
        return "unrelated"

    def to_prompt_records(self, items: Optional[Iterable[MemoryItem]] = None) -> List[Dict[str, Any]]:
        selected = items if items is not None else self.active_items()
        return [
            {
                "id": item.id,
                "type": item.type,
                "scope": item.scope,
                "summary": item.summary,
                "status": item.status,
                "version": item.version,
                "tags": list(item.tags),
            }
            for item in selected
        ]
