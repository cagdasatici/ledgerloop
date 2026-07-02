import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from orchestrator.config import config_from_dict, default_config, load_config


class ConfigLoadingTests(unittest.TestCase):
    def test_config_from_dict_layers_onto_defaults(self):
        config = config_from_dict(
            {
                "project_id": "custom-project",
                "budget": {"max_usd": 0.25, "max_repair_attempts": 2},
                "safety": {"allow_global_dependency_changes": True},
            }
        )

        self.assertEqual(config.project_id, "custom-project")
        self.assertEqual(config.budget.max_usd, 0.25)
        self.assertEqual(config.budget.max_repair_attempts, 2)
        # Untouched fields keep their defaults.
        self.assertEqual(config.budget.max_iterations, default_config().budget.max_iterations)
        self.assertTrue(config.safety.allow_global_dependency_changes)
        self.assertEqual(set(config.providers), set(default_config().providers))

    def test_config_from_dict_replaces_providers(self):
        config = config_from_dict(
            {
                "providers": {
                    "my-model": {
                        "provider": "anthropic",
                        "pricing": {"input_per_million": 3.0, "output_per_million": 15.0},
                        "supports_cache": True,
                    }
                }
            }
        )

        self.assertEqual(list(config.providers), ["my-model"])
        provider = config.providers["my-model"]
        self.assertEqual(provider.provider, "anthropic")
        self.assertEqual(provider.pricing.input_per_million, 3.0)
        self.assertTrue(provider.supports_cache)

    def test_load_config_reads_json_file(self):
        with tempfile.TemporaryDirectory(dir="/private/tmp") as tmpdir:
            path = pathlib.Path(tmpdir) / "config.json"
            path.write_text(json.dumps({"budget": {"max_usd": 0.5}}))

            config = load_config(str(path))

        self.assertEqual(config.budget.max_usd, 0.5)

    def test_unknown_keys_are_ignored(self):
        config = config_from_dict({"budget": {"max_usd": 0.5, "not_a_field": 1}})

        self.assertEqual(config.budget.max_usd, 0.5)

    def test_pricing_cost_for_is_single_source_of_truth(self):
        pricing = default_config().providers["balanced-code-model"].pricing

        cost = pricing.cost_for(1_000_000, 1_000_000)

        self.assertAlmostEqual(cost, 0.25 + 0.75)


if __name__ == "__main__":
    unittest.main()
