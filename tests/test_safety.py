import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from orchestrator.safety import SafetyPolicy, SafetyViolation


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


if __name__ == "__main__":
    unittest.main()
