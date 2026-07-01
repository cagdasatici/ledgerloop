import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from orchestrator.budget import BudgetExceeded, BudgetLedger, UsageMetadata
from orchestrator.config import BudgetConfig, ModelPricing, ProviderModelConfig


class BudgetLedgerTests(unittest.TestCase):
    def test_hard_budget_blocks_expensive_call(self):
        providers = {
            "expensive": ProviderModelConfig(
                provider="fake",
                model_id="expensive",
                pricing=ModelPricing(input_per_million=10.0, output_per_million=20.0),
            )
        }
        ledger = BudgetLedger(BudgetConfig(max_usd=0.001), providers)

        with self.assertRaises(BudgetExceeded):
            ledger.assert_can_spend(
                "expensive",
                UsageMetadata(input_tokens=1000, output_tokens=1000),
                "test",
            )

    def test_actual_usage_is_recorded(self):
        providers = {
            "cheap": ProviderModelConfig(
                provider="fake",
                model_id="cheap",
                pricing=ModelPricing(input_per_million=1.0, output_per_million=1.0),
            )
        }
        ledger = BudgetLedger(BudgetConfig(max_usd=1.0), providers)
        usage = UsageMetadata(input_tokens=100, output_tokens=50)
        estimate = ledger.assert_can_spend("cheap", usage)
        ledger.record_actual("cheap", usage, estimated_usd=estimate)

        self.assertEqual(ledger.summary()["records"], 1)
        self.assertEqual(ledger.summary()["input_tokens"], 100)
        self.assertEqual(ledger.summary()["output_tokens"], 50)


if __name__ == "__main__":
    unittest.main()
