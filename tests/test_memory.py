import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from orchestrator.memory import MemoryItem, MemoryStore


class MemoryStoreTests(unittest.TestCase):
    def test_repeated_lesson_is_merged_not_appended(self):
        store = MemoryStore(project_id="loop-orchestrator")
        first = MemoryItem(
            id="mem_1",
            project_id="loop-orchestrator",
            type="lesson",
            scope="src/router.py",
            summary="Route high-risk tasks through an auditor before reporting.",
            source_event_ids=["evt_1"],
            tags=["routing", "safety"],
        )
        second = MemoryItem(
            id="mem_2",
            project_id="loop-orchestrator",
            type="lesson",
            scope="src/router.py",
            summary="Route high-risk tasks through an auditor before reporting.",
            source_event_ids=["evt_2"],
            tags=["routing", "safety"],
        )

        self.assertEqual(store.add_or_merge(first)["action"], "created")
        merge = store.add_or_merge(second)

        self.assertEqual(merge["action"], "merged")
        self.assertEqual(len(store.items), 1)
        self.assertEqual(store.items[0].version, 2)
        self.assertEqual(store.items[0].source_event_ids, ["evt_1", "evt_2"])
        self.assertIn("mem_2", store.items[0].supersedes)

    def test_retrieve_excludes_irrelevant_memory(self):
        store = MemoryStore(project_id="loop-orchestrator")
        store.add_or_merge(
            MemoryItem(
                id="mem_router",
                project_id="loop-orchestrator",
                type="lesson",
                scope="src/router.py",
                summary="Routing decisions must explain risk and complexity.",
                tags=["routing"],
            )
        )
        store.add_or_merge(
            MemoryItem(
                id="mem_ui",
                project_id="loop-orchestrator",
                type="lesson",
                scope="src/ui.py",
                summary="Use compact visual controls in dashboards.",
                tags=["frontend"],
            )
        )

        results = store.retrieve("routing risk complexity", scope="src/router.py")

        self.assertEqual([item.id for item in results], ["mem_router"])


if __name__ == "__main__":
    unittest.main()
