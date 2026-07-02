import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from orchestrator.config import BudgetConfig, OrchestratorConfig, default_config
from orchestrator.loop import LoopRunner, ValidationResult
from orchestrator.safety import SafetyPolicy


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

    def test_safety_gate_blocks_dependency_change_without_isolation(self):
        config = default_config()
        safety = SafetyPolicy(config.safety, project_root="/tmp/definitely-not-this-project")
        runner = LoopRunner(config=config, safety=safety)

        result = runner.run("install the new dependency for parsing", task_id="task_dep")

        self.assertEqual(result.status, "blocked")
        gate_events = [event for event in result.events if event["state"] == "safety_gate"]
        self.assertEqual(len(gate_events), 1)
        self.assertEqual(gate_events[0]["status"], "blocked")

    def test_safety_gate_passes_normal_task(self):
        runner = LoopRunner(config=default_config())
        result = runner.run("implement a small budget ledger improvement", task_id="task_ok")

        self.assertEqual(result.status, "succeeded")
        gate_events = [event for event in result.events if event["state"] == "safety_gate"]
        self.assertEqual(gate_events[0]["status"], "succeeded")

    def test_repair_cap_escalates_to_stronger_tier_before_blocking(self):
        base = default_config()
        config = OrchestratorConfig(
            project_id=base.project_id,
            budget=BudgetConfig(max_repair_attempts=1, max_iterations=8),
            safety=base.safety,
            providers=base.providers,
        )

        def always_fail(iteration, response_text):
            return ValidationResult.failure("validate:test:logic", "logic is still failing")

        runner = LoopRunner(config=config)
        result = runner.run(
            "implement a feature with a repeated validation failure",
            task_id="task_escalate",
            validator=always_fail,
        )

        self.assertEqual(result.status, "blocked")
        repair_statuses = [
            event["status"] for event in result.events if event["state"] == "repair"
        ]
        self.assertIn("escalated", repair_statuses)
        self.assertEqual(repair_statuses[-1], "blocked")
        escalated = [
            event
            for event in result.events
            if event["state"] == "repair" and event["status"] == "escalated"
        ]
        self.assertEqual(escalated[0]["provider"], "strong-audit-model")
        executed_models = {
            event["provider"] for event in result.events if event["state"] == "execute"
        }
        self.assertIn("strong-audit-model", executed_models)

    def test_successful_run_tracks_artifacts(self):
        runner = LoopRunner(config=default_config())
        result = runner.run("implement a small budget ledger improvement", task_id="task_art")

        kinds = {artifact["kind"] for artifact in result.artifacts}
        self.assertEqual(kinds, {"edit", "validation", "audit", "report"})
        self.assertEqual(len(result.changed_artifacts), 1)
        self.assertEqual(result.changed_artifacts[0]["kind"], "edit")
        execute_events = [event for event in result.events if event["state"] == "execute"]
        self.assertTrue(execute_events[0]["output_refs"])


if __name__ == "__main__":
    unittest.main()
