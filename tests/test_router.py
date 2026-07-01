import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from orchestrator.router import Router


class RouterTests(unittest.TestCase):
    def test_routes_representative_task_types(self):
        router = Router()
        examples = {
            "explain the current architecture": ("explain", "low"),
            "implement budget ledger tests": ("edit", "medium"),
            "run validation tests for the package": ("test", "medium"),
            "audit the repair loop for safety regressions": ("audit", "high"),
            "deploy and push the release to production": ("release", "high"),
        }

        for task, (intent, tier) in examples.items():
            with self.subTest(task=task):
                decision = router.route_task(task)
                self.assertEqual(decision.intent, intent)
                self.assertEqual(decision.tier, tier)
                self.assertTrue(decision.reason)

    def test_high_risk_requires_approval(self):
        decision = Router().route_task("push credentials to production")

        self.assertEqual(decision.risk, "high")
        self.assertTrue(decision.requires_approval)


if __name__ == "__main__":
    unittest.main()
