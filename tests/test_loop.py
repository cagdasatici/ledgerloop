import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from orchestrator.config import BudgetConfig, OrchestratorConfig, default_config
from orchestrator.loop import LoopRunner, ValidationResult


class LoopRunnerTests(unittest.TestCase):
    def test_full_mock_loop_succeeds(self):
        runner = LoopRunner(config=default_config())
        result = runner.run("implement a small budget ledger improvement", task_id="task_success")

        self.assertEqual(result.status, "succeeded")
        states = [event["state"] for event in result.events]
        self.assertIn("execute", states)
        self.assertIn("validate", states)
        self.assertIn("audit", states)
        self.assertIn("consolidate_memory", states)
        self.assertTrue(result.prompt_hash.startswith("sha256:"))
        self.assertTrue(result.cacheable_hash.startswith("sha256:"))

    def test_repair_limit_blocks_repeated_failure_fingerprint(self):
        base = default_config()
        config = OrchestratorConfig(
            project_id=base.project_id,
            budget=BudgetConfig(max_repair_attempts=1, max_iterations=5),
            safety=base.safety,
            providers=base.providers,
        )

        def always_fail(iteration, response_text):
            return ValidationResult.failure("validate:test:logic", "logic is still failing")

        runner = LoopRunner(config=config)
        result = runner.run(
            "implement a feature with a repeated validation failure",
            task_id="task_fail",
            validator=always_fail,
        )

        self.assertEqual(result.status, "blocked")
        repair_events = [event for event in result.events if event["state"] == "repair"]
        self.assertEqual(repair_events[-1]["status"], "blocked")
        self.assertEqual(repair_events[-1]["failure_fingerprint"], "validate:test:logic")

    def test_high_risk_task_stops_for_approval(self):
        runner = LoopRunner(config=default_config())
        result = runner.run("deploy and push credentials to production", task_id="task_high")

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.message, "Approval required.")


if __name__ == "__main__":
    unittest.main()
