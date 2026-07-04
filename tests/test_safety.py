import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from orchestrator.safety import ProposedAction, SafetyPolicy, SafetyViolation


class SafetyPolicyTests(unittest.TestCase):
    def test_dependency_install_requires_isolated_environment(self):
        policy = SafetyPolicy(project_root="/tmp/project")

        with self.assertRaises(SafetyViolation):
            policy.assert_dependency_change_allowed(env={})

    def test_project_local_virtualenv_allows_dependency_change(self):
        policy = SafetyPolicy(project_root="/tmp/project")
        decision = policy.verify_dependency_environment(env={"VIRTUAL_ENV": "/tmp/project/.venv"})

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.risk, "medium")

    def test_evaluate_task_blocks_dependency_task_without_isolation(self):
        policy = SafetyPolicy(project_root="/tmp/project")
        decision = policy.evaluate_task("install the requests dependency", env={})

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.action, "dependency_change")
        self.assertEqual(decision.risk, "high")

    def test_evaluate_task_allows_dependency_task_inside_project_env(self):
        policy = SafetyPolicy(project_root="/tmp/project")
        decision = policy.evaluate_task(
            "install the requests dependency",
            env={"VIRTUAL_ENV": "/tmp/project/.venv"},
        )

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.action, "dependency_change")

    def test_evaluate_task_allows_non_dependency_task(self):
        policy = SafetyPolicy(project_root="/tmp/project")
        decision = policy.evaluate_task("implement a prompt hashing improvement", env={})

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.action, "execute")

    def test_evaluate_action_blocks_dependency_action_without_isolation(self):
        policy = SafetyPolicy(project_root="/tmp/project")
        action = ProposedAction(
            action_id="act_1",
            kind="command",
            description="Install requests",
            command="pip install requests",
        )

        decision = policy.evaluate_action(action, env={})

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.action_id, "act_1")
        self.assertEqual(decision.risk, "high")

    def test_evaluate_action_blocks_high_risk_push(self):
        policy = SafetyPolicy(project_root="/tmp/project")
        action = ProposedAction(
            action_id="act_push",
            kind="command",
            description="Push to remote",
            command="git push origin main",
        )

        decision = policy.evaluate_action(action, env={})

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "High-risk action requires explicit approval before execution.")

    def test_evaluate_action_allows_low_risk_file_read(self):
        policy = SafetyPolicy(project_root="/tmp/project")
        action = ProposedAction(
            action_id="act_read",
            kind="read",
            description="Inspect README",
            command="",
        )

        decision = policy.evaluate_action(action, env={})

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.risk, "low")


if __name__ == "__main__":
    unittest.main()
