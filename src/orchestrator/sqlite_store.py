"""SQLite-backed memory and event persistence.

The JSON memory store remains the bootstrap/default path. These classes provide
an opt-in durable backend with migrations, transactional writes, WAL mode, and a
busy timeout so multiple local processes can coordinate more safely.
"""

import json
import os
import sqlite3
from typing import Any, Dict, List, Optional

from orchestrator.events import EventLog, LoopEvent, utc_now_iso
from orchestrator.memory import Curator, MemoryItem, MemoryStore


SCHEMA_VERSION = 1


def _json_dump(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def _json_load(text: str, fallback: Any) -> Any:
    if not text:
        return fallback
    return json.loads(text)


class SQLiteMixin:
    """Shared SQLite setup helpers."""

    def __init__(self, sqlite_path: str) -> None:
        self.sqlite_path = sqlite_path
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        directory = os.path.dirname(self.sqlite_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        connection = sqlite3.connect(self.sqlite_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS ledgerloop_schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_items (
                    project_id TEXT NOT NULL,
                    id TEXT NOT NULL,
                    type TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    status TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    confidence REAL NOT NULL,
                    source_event_ids_json TEXT NOT NULL,
                    supersedes_json TEXT NOT NULL,
                    tags_json TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (project_id, id)
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_memory_project_scope_status
                ON memory_items (project_id, scope, status)
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS loop_events (
                    sequence INTEGER PRIMARY KEY,
                    event_id TEXT NOT NULL UNIQUE,
                    task_id TEXT NOT NULL,
                    state TEXT NOT NULL,
                    role TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    iteration INTEGER NOT NULL,
                    repair_attempt INTEGER NOT NULL,
                    failure_fingerprint TEXT,
                    input_refs_json TEXT NOT NULL,
                    output_refs_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    cost_json TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_loop_events_task_sequence
                ON loop_events (task_id, sequence)
                """
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO ledgerloop_schema_migrations (version, applied_at)
                VALUES (?, ?)
                """,
                (SCHEMA_VERSION, utc_now_iso()),
            )


class SQLiteMemoryStore(SQLiteMixin, MemoryStore):
    """SQLite-backed memory store with the same public interface as MemoryStore."""

    def __init__(
        self,
        project_id: str,
        sqlite_path: str,
        duplicate_threshold: float = 0.90,
        refinement_threshold: float = 0.72,
        curator: Optional[Curator] = None,
    ) -> None:
        MemoryStore.__init__(
            self,
            project_id=project_id,
            path=None,
            duplicate_threshold=duplicate_threshold,
            refinement_threshold=refinement_threshold,
            curator=curator,
        )
        SQLiteMixin.__init__(self, sqlite_path)
        self.items = self._load_items()

    @classmethod
    def load(cls, project_id: str, path: str) -> "SQLiteMemoryStore":
        return cls(project_id=project_id, sqlite_path=path)

    def save(self) -> None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "DELETE FROM memory_items WHERE project_id = ?",
                (self.project_id,),
            )
            connection.executemany(
                """
                INSERT INTO memory_items (
                    project_id, id, type, scope, summary, status, version,
                    confidence, source_event_ids_json, supersedes_json, tags_json,
                    content_hash, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [self._item_to_row(item) for item in self.items],
            )
            connection.commit()

    def _load_items(self) -> List[MemoryItem]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM memory_items
                WHERE project_id = ?
                ORDER BY scope, id
                """,
                (self.project_id,),
            ).fetchall()
        return [self._row_to_item(row) for row in rows]

    def _item_to_row(self, item: MemoryItem) -> tuple:
        return (
            item.project_id,
            item.id,
            item.type,
            item.scope,
            item.summary,
            item.status,
            item.version,
            item.confidence,
            _json_dump(item.source_event_ids),
            _json_dump(item.supersedes),
            _json_dump(item.tags),
            item.content_hash,
            item.created_at,
            item.updated_at,
        )

    def _row_to_item(self, row: sqlite3.Row) -> MemoryItem:
        return MemoryItem(
            id=row["id"],
            project_id=row["project_id"],
            type=row["type"],
            scope=row["scope"],
            summary=row["summary"],
            status=row["status"],
            version=row["version"],
            confidence=row["confidence"],
            source_event_ids=_json_load(row["source_event_ids_json"], []),
            supersedes=_json_load(row["supersedes_json"], []),
            tags=_json_load(row["tags_json"], []),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            content_hash=row["content_hash"],
        )


class SQLiteEventLog(SQLiteMixin, EventLog):
    """Event log that persists appended events to SQLite.

    `to_list()` intentionally returns only events appended through this instance,
    preserving the per-run semantics expected by LoopRunner. Use `all_events()`
    or `events_for_task()` to inspect persisted history.
    """

    def __init__(self, sqlite_path: str) -> None:
        EventLog.__init__(self)
        SQLiteMixin.__init__(self, sqlite_path)

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
        cost = cost or {}
        input_refs = input_refs or []
        output_refs = output_refs or []
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            sequence = connection.execute(
                "SELECT COALESCE(MAX(sequence), 0) + 1 FROM loop_events"
            ).fetchone()[0]
            event = LoopEvent(
                event_id="evt_%04d" % sequence,
                task_id=task_id,
                state=state,
                role=role,
                provider=provider,
                iteration=iteration,
                repair_attempt=repair_attempt,
                failure_fingerprint=failure_fingerprint,
                status=status,
                message=message,
                cost=cost,
                input_refs=input_refs,
                output_refs=output_refs,
            )
            connection.execute(
                """
                INSERT INTO loop_events (
                    sequence, event_id, task_id, state, role, provider,
                    iteration, repair_attempt, failure_fingerprint,
                    input_refs_json, output_refs_json, status, cost_json,
                    message, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._event_to_row(sequence, event),
            )
            connection.commit()
        self.events.append(event)
        return event

    def all_events(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        query = "SELECT * FROM loop_events ORDER BY sequence"
        params: tuple = ()
        if limit is not None:
            query = "SELECT * FROM loop_events ORDER BY sequence DESC LIMIT ?"
            params = (limit,)
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        events = [self._row_to_event(row).to_dict() for row in rows]
        if limit is not None:
            events.reverse()
        return events

    def events_for_task(self, task_id: str) -> List[Dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM loop_events
                WHERE task_id = ?
                ORDER BY sequence
                """,
                (task_id,),
            ).fetchall()
        return [self._row_to_event(row).to_dict() for row in rows]

    def _event_to_row(self, sequence: int, event: LoopEvent) -> tuple:
        return (
            sequence,
            event.event_id,
            event.task_id,
            event.state,
            event.role,
            event.provider,
            event.iteration,
            event.repair_attempt,
            event.failure_fingerprint,
            _json_dump(event.input_refs),
            _json_dump(event.output_refs),
            event.status,
            _json_dump(event.cost),
            event.message,
            event.created_at,
        )

    def _row_to_event(self, row: sqlite3.Row) -> LoopEvent:
        return LoopEvent(
            event_id=row["event_id"],
            task_id=row["task_id"],
            state=row["state"],
            role=row["role"],
            provider=row["provider"],
            iteration=row["iteration"],
            repair_attempt=row["repair_attempt"],
            failure_fingerprint=row["failure_fingerprint"],
            input_refs=_json_load(row["input_refs_json"], []),
            output_refs=_json_load(row["output_refs_json"], []),
            status=row["status"],
            cost=_json_load(row["cost_json"], {}),
            message=row["message"],
            created_at=row["created_at"],
        )
