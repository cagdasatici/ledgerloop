import io
import json
import pathlib
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from orchestrator.budget import UsageMetadata
from orchestrator.cli import main
from orchestrator.memory import MemoryItem
from orchestrator.sqlite_store import SQLiteEventLog, SQLiteMemoryStore


class SQLiteStoreTests(unittest.TestCase):
    def test_memory_items_persist_and_merge_across_reload(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(pathlib.Path(tmpdir) / "ledgerloop.db")
            store = SQLiteMemoryStore.load("loop-orchestrator", db_path)
            first = MemoryItem(
                id="mem_1",
                project_id="loop-orchestrator",
                type="lesson",
                scope="src/memory.py",
                summary="Persist memory writes atomically through SQLite.",
                source_event_ids=["evt_1"],
                tags=["memory", "sqlite"],
            )
            second = MemoryItem(
                id="mem_2",
                project_id="loop-orchestrator",
                type="lesson",
                scope="src/memory.py",
                summary="Persist memory writes atomically through SQLite.",
                source_event_ids=["evt_2"],
                tags=["memory", "sqlite"],
            )

            self.assertEqual(store.add_or_merge(first)["action"], "created")
            self.assertEqual(store.add_or_merge(second)["action"], "merged")

            reloaded = SQLiteMemoryStore.load("loop-orchestrator", db_path)

        self.assertEqual(len(reloaded.items), 1)
        self.assertEqual(reloaded.items[0].version, 2)
        self.assertEqual(reloaded.items[0].source_event_ids, ["evt_1", "evt_2"])
        self.assertIn("mem_2", reloaded.items[0].supersedes)

    def test_stale_memory_writers_do_not_delete_each_other(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(pathlib.Path(tmpdir) / "ledgerloop.db")
            first_writer = SQLiteMemoryStore.load("loop-orchestrator", db_path)
            second_writer = SQLiteMemoryStore.load("loop-orchestrator", db_path)

            first_writer.add_or_merge(
                MemoryItem(
                    id="mem_a",
                    project_id="loop-orchestrator",
                    type="lesson",
                    scope="src/a.py",
                    summary="First writer memory should survive.",
                    tags=["a"],
                )
            )
            second_writer.add_or_merge(
                MemoryItem(
                    id="mem_b",
                    project_id="loop-orchestrator",
                    type="lesson",
                    scope="src/b.py",
                    summary="Second writer memory should not wipe the first.",
                    tags=["b"],
                )
            )

            reloaded = SQLiteMemoryStore.load("loop-orchestrator", db_path)

        self.assertEqual({item.id for item in reloaded.items}, {"mem_a", "mem_b"})

    def test_memory_summary_is_redacted_before_persistence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(pathlib.Path(tmpdir) / "ledgerloop.db")
            store = SQLiteMemoryStore.load("loop-orchestrator", db_path)
            store.add_or_merge(
                MemoryItem(
                    id="mem_secret",
                    project_id="loop-orchestrator",
                    type="lesson",
                    scope="global",
                    summary="Never persist api_key=sk-12345678901234567890 in memory.",
                    tags=["security"],
                )
            )

            reloaded = SQLiteMemoryStore.load("loop-orchestrator", db_path)

        self.assertIn("api_key=[REDACTED]", reloaded.items[0].summary)
        self.assertNotIn("sk-12345678901234567890", reloaded.items[0].summary)

    def test_event_log_persists_history_but_keeps_current_run_scoped(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(pathlib.Path(tmpdir) / "ledgerloop.db")
            first_log = SQLiteEventLog(db_path)
            first_log.append("task_1", "intake", "router", message="first")

            second_log = SQLiteEventLog(db_path)
            second_log.append("task_2", "intake", "router", message="second")

            current = second_log.to_list()
            all_events = second_log.all_events()
            task_1_events = second_log.events_for_task("task_1")

        self.assertEqual([event["task_id"] for event in current], ["task_2"])
        self.assertEqual([event["task_id"] for event in all_events], ["task_1", "task_2"])
        self.assertEqual(len(task_1_events), 1)
        self.assertEqual(task_1_events[0]["message"], "first")

    def test_v1_event_schema_migrates_project_and_run_columns(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(pathlib.Path(tmpdir) / "ledgerloop.db")
            connection = sqlite3.connect(db_path)
            connection.execute(
                """
                CREATE TABLE loop_events (
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
                INSERT INTO loop_events VALUES (
                    1, 'evt_0001', 'task_legacy', 'intake', 'router', 'local',
                    0, 0, NULL, '[]', '[]', 'succeeded', '{}', 'legacy',
                    '2026-07-04T00:00:00Z'
                )
                """
            )
            connection.commit()
            connection.close()

            events = SQLiteEventLog(db_path).all_events()

        self.assertEqual(events[0]["project_id"], "loop-orchestrator")
        self.assertEqual(events[0]["run_id"], "run_legacy")
        self.assertEqual(events[0]["task_id"], "task_legacy")

    def test_event_history_is_project_scoped(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(pathlib.Path(tmpdir) / "ledgerloop.db")
            project_a = SQLiteEventLog(db_path, project_id="project-a")
            project_b = SQLiteEventLog(db_path, project_id="project-b")
            project_a.append("task_shared", "intake", "router", message="a")
            project_b.append("task_shared", "intake", "router", message="b")

            a_events = project_a.all_events()
            b_events = project_b.all_events()

        self.assertEqual([event["project_id"] for event in a_events], ["project-a"])
        self.assertEqual([event["project_id"] for event in b_events], ["project-b"])
        self.assertEqual(a_events[0]["message"], "a")
        self.assertEqual(b_events[0]["message"], "b")

    def test_event_message_is_redacted_before_persistence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(pathlib.Path(tmpdir) / "ledgerloop.db")
            event_log = SQLiteEventLog(db_path)
            event_log.append(
                "task_secret",
                "execute",
                "builder",
                message="Builder echoed api_key=sk-12345678901234567890",
            )

            persisted = SQLiteEventLog(db_path).all_events()

        self.assertIn("api_key=[REDACTED]", persisted[0]["message"])
        self.assertNotIn("sk-12345678901234567890", persisted[0]["message"])

    def test_cli_uses_sqlite_backend_for_events(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(pathlib.Path(tmpdir) / "ledgerloop.db")
            code = main(
                [
                    "--sqlite-path",
                    db_path,
                    "--json",
                    "explain LedgerLoop architecture",
                ],
                stdout=stdout,
                stderr=stderr,
            )
            persisted_events = SQLiteEventLog(db_path).all_events()
            payload = json.loads(stdout.getvalue())

        self.assertEqual(code, 0)
        self.assertEqual(payload["status"], "succeeded")
        self.assertEqual(len(persisted_events), len(payload["events"]))
        self.assertEqual(persisted_events[-1]["state"], "report")

    def test_cli_repeated_default_task_id_gets_distinct_run_ids(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(pathlib.Path(tmpdir) / "ledgerloop.db")
            first_stdout = io.StringIO()
            second_stdout = io.StringIO()
            main(
                ["--sqlite-path", db_path, "--json", "explain LedgerLoop architecture"],
                stdout=first_stdout,
                stderr=io.StringIO(),
            )
            main(
                ["--sqlite-path", db_path, "--json", "explain LedgerLoop architecture"],
                stdout=second_stdout,
                stderr=io.StringIO(),
            )
            first_payload = json.loads(first_stdout.getvalue())
            second_payload = json.loads(second_stdout.getvalue())
            event_log = SQLiteEventLog(db_path)
            persisted_events = event_log.all_events()
            run_results = event_log.run_results()

        self.assertNotEqual(first_payload["run_id"], second_payload["run_id"])
        self.assertEqual(len({event["run_id"] for event in persisted_events}), 2)
        self.assertEqual(len(run_results), 2)
        self.assertEqual({result["task_id"] for result in run_results}, {"task_cli_0001"})

    def test_cost_records_accumulate_across_runs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(pathlib.Path(tmpdir) / "ledgerloop.db")
            first_log = SQLiteEventLog(db_path, project_id="loop-orchestrator")
            second_log = SQLiteEventLog(db_path, project_id="loop-orchestrator")
            first_log.record_cost(
                "task_1",
                "balanced-code-model",
                "execute",
                UsageMetadata(input_tokens=10, output_tokens=20),
                0.1,
                0.1,
            )
            second_log.record_cost(
                "task_2",
                "strong-audit-model",
                "plan",
                UsageMetadata(input_tokens=30, output_tokens=40),
                0.2,
                0.2,
            )

            total = second_log.total_spend_usd()

        self.assertAlmostEqual(total, 0.3)

    def test_cli_persists_artifacts_to_sqlite(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(pathlib.Path(tmpdir) / "ledgerloop.db")
            code = main(
                [
                    "--sqlite-path",
                    db_path,
                    "--json",
                    "explain LedgerLoop architecture",
                ],
                stdout=stdout,
                stderr=stderr,
            )
            payload = json.loads(stdout.getvalue())
            connection = sqlite3.connect(db_path)
            artifact_rows = connection.execute(
                """
                SELECT artifact_id FROM artifacts
                ORDER BY artifact_id
                """
            ).fetchall()
            artifact_ids = {row[0] for row in artifact_rows}
            connection.close()

        self.assertEqual(code, 0)
        self.assertEqual(len(artifact_rows), len(payload["artifacts"]))
        for event in payload["events"]:
            for output_ref in event["output_refs"]:
                if output_ref.startswith("art_"):
                    self.assertIn(output_ref, artifact_ids)


if __name__ == "__main__":
    unittest.main()
