import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from orchestrator.prompts import assemble_prompt_bundle


class PromptAssemblyTests(unittest.TestCase):
    def test_cacheable_hash_ignores_current_task_payload(self):
        base_kwargs = {
            "system_contract": {"rules": ["bounded", "safe"]},
            "project_summary": {"project_id": "loop-orchestrator"},
            "memory_summary": [{"id": "mem_1", "summary": "Use scoped retrieval."}],
            "dynamic_context": {"events": []},
        }
        first = assemble_prompt_bundle(current_task_payload={"goal": "A"}, **base_kwargs)
        second = assemble_prompt_bundle(current_task_payload={"goal": "B"}, **base_kwargs)

        self.assertEqual(first.cacheable_hash, second.cacheable_hash)
        self.assertNotEqual(first.full_hash, second.full_hash)

    def test_sorted_json_makes_hash_deterministic(self):
        first = assemble_prompt_bundle(
            system_contract={"b": 2, "a": 1},
            project_summary={},
            memory_summary=[],
            dynamic_context={},
            current_task_payload={},
        )
        second = assemble_prompt_bundle(
            system_contract={"a": 1, "b": 2},
            project_summary={},
            memory_summary=[],
            dynamic_context={},
            current_task_payload={},
        )

        self.assertEqual(first.full_hash, second.full_hash)


if __name__ == "__main__":
    unittest.main()
