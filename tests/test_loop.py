import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from orchestrator.config import BudgetConfig, OrchestratorConfig, default_config
from orchestrator.loop import LoopRunner, ValidationResult
from orchestrator.providers import (
    FakeProviderAdapter,
    ProviderAuthError,
    ProviderMalformedOutputError,
    ProviderTimeoutError,
    RetryPolicy,
)
from orchestrator.safety import ProposedAction, SafetyPolicy


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

    def test_loop_binds_phases_to_capable_providers(self):
        runner = LoopRunner(config=default_config())
        result = runner.run("implement a small budget ledger improvement", task_id="task_phase")

        self.assertEqual(result.status, "succeeded")
        plan_events = [e for e in result.events if e["state"] == "plan"]
        audit_events = [e for e in result.events if e["state"] == "audit"]
        execute_events = [e for e in result.events if e["state"] == "execute"]
        self.assertEqual(plan_events[0]["provider"], "balanced-code-model")
        self.assertEqual(audit_events[0]["provider"], "balanced-code-model")
        self.assertEqual(execute_events[0]["provider"], "balanced-code-model")

    def test_provider_timeout_retries_before_success(self):
        config = default_config()
        providers = {
            model_id: FakeProviderAdapter(model_id=model_id)
            for model_id in config.providers
        }
        providers["balanced-code-model"] = FakeProviderAdapter(
            model_id="balanced-code-model",
            failures=[ProviderTimeoutError("temporary timeout", "balanced-code-model")],
        )
        runner = LoopRunner(
            config=config,
            providers=providers,
            retry_policy=RetryPolicy(max_attempts=2),
        )

        result = runner.run("implement retry handling", task_id="task_retry")

        self.assertEqual(result.status, "succeeded")
        states = [event["state"] for event in result.events]
        self.assertIn("provider_error", states)
        self.assertIn("provider_retry", states)

    def test_provider_auth_failure_blocks_without_repair_attempt(self):
        config = default_config()
        providers = {
            model_id: FakeProviderAdapter(model_id=model_id)
            for model_id in config.providers
        }
        providers["balanced-code-model"] = FakeProviderAdapter(
            model_id="balanced-code-model",
            failures=[ProviderAuthError("bad credentials", "balanced-code-model")],
        )
        runner = LoopRunner(config=config, providers=providers)

        result = runner.run("implement auth failure handling", task_id="task_auth")

        self.assertEqual(result.status, "blocked")
        self.assertIn("Provider auth failure", result.message)
        self.assertFalse([event for event in result.events if event["state"] == "repair"])

    def test_malformed_provider_output_consumes_repair_and_escalates(self):
        base = default_config()
        config = OrchestratorConfig(
            project_id=base.project_id,
            budget=BudgetConfig(max_repair_attempts=0, max_iterations=3),
            safety=base.safety,
            providers=base.providers,
        )
        providers = {
            model_id: FakeProviderAdapter(model_id=model_id)
            for model_id in config.providers
        }
        providers["balanced-code-model"] = FakeProviderAdapter(
            model_id="balanced-code-model",
            failures=[
                ProviderMalformedOutputError(
                    "provider returned invalid schema", "balanced-code-model"
                )
            ],
        )
        runner = LoopRunner(
            config=config,
            providers=providers,
            retry_policy=RetryPolicy(max_attempts=1),
        )

        result = runner.run("implement malformed output handling", task_id="task_malformed")

        self.assertEqual(result.status, "succeeded")
        repair_events = [event for event in result.events if event["state"] == "repair"]
        self.assertEqual(repair_events[0]["status"], "escalated")
        self.assertEqual(repair_events[0]["failure_fingerprint"], "provider:malformed_output:balanced-code-model")

    def test_action_time_safety_blocks_builder_proposed_dependency_install(self):
        config = default_config()
        providers = {
            model_id: FakeProviderAdapter(model_id=model_id)
            for model_id in config.providers
        }
        providers["balanced-code-model"] = FakeProviderAdapter(
            model_id="balanced-code-model",
            actions=[
                ProposedAction(
                    action_id="act_install",
                    kind="command",
                    description="Install a dependency",
                    command="pip install requests",
                )
            ],
        )
        runner = LoopRunner(config=config, providers=providers, safety=SafetyPolicy(project_root="/tmp/project"))

        result = runner.run("implement parser support", task_id="task_action_safety")

        self.assertEqual(result.status, "blocked")
        provider_call_events = [event for event in result.events if event["state"] == "provider_call"]
        self.assertEqual(len(provider_call_events), 1)
        self.assertTrue(provider_call_events[0]["cost"])
        gate_events = [event for event in result.events if event["state"] == "action_safety_gate"]
        self.assertEqual(gate_events[0]["status"], "blocked")
        self.assertEqual(gate_events[0]["input_refs"], ["act_install"])

    def test_action_time_safety_blocks_unknown_builder_command(self):
        config = default_config()
        providers = {
            model_id: FakeProviderAdapter(model_id=model_id)
            for model_id in config.providers
        }
        providers["balanced-code-model"] = FakeProviderAdapter(
            model_id="balanced-code-model",
            actions=[
                ProposedAction(
                    action_id="act_custom",
                    kind="command",
                    description="Run custom helper",
                    command="./scripts/do-work",
                )
            ],
        )
        runner = LoopRunner(config=config, providers=providers, safety=SafetyPolicy(project_root="/tmp/project"))

        result = runner.run("implement custom helper support", task_id="task_unknown_command")

        self.assertEqual(result.status, "blocked")
        gate_events = [event for event in result.events if event["state"] == "action_safety_gate"]
        self.assertEqual(gate_events[0]["status"], "blocked")
        self.assertIn("Unrecognized command action", gate_events[0]["message"])

    def test_action_time_safety_allows_low_risk_builder_action(self):
        config = default_config()
        providers = {
            model_id: FakeProviderAdapter(model_id=model_id)
            for model_id in config.providers
        }
        providers["balanced-code-model"] = FakeProviderAdapter(
            model_id="balanced-code-model",
            actions=[
                ProposedAction(
                    action_id="act_read",
                    kind="read",
                    description="Inspect README",
                )
            ],
        )
        runner = LoopRunner(config=config, providers=providers)

        result = runner.run("implement a safe inspection", task_id="task_safe_action")

        self.assertEqual(result.status, "succeeded")
        gate_events = [event for event in result.events if event["state"] == "action_safety_gate"]
        self.assertEqual(gate_events[0]["status"], "succeeded")


if __name__ == "__main__":
    unittest.main()
