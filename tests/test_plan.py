import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from orchestrator.plan import plan_from_provider_text


class PlanTests(unittest.TestCase):
    def test_plan_from_provider_text_splits_lines(self):
        spec = plan_from_provider_text("goal", "model-x", "step one\n\nstep two\n")

        self.assertEqual(spec.steps, ["step one", "step two"])
        self.assertEqual(spec.produced_by, "model-x")

    def test_plan_from_empty_text_produces_placeholder(self):
        spec = plan_from_provider_text("goal", "model-x", "")

        self.assertEqual(spec.steps, ["no plan produced"])


if __name__ == "__main__":
    unittest.main()
