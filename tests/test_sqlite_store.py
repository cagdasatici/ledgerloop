import io
import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

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


if __name__ == "__main__":
    unittest.main()
