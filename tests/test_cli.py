import io
import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from orchestrator.cli import main


class CliTests(unittest.TestCase):
    def test_summary_run_succeeds(self):
        stdout = io.StringIO()
        stderr = io.StringIO()

        code = main(["implement a tiny prompt builder improvement"], stdout=stdout, stderr=stderr)

        self.assertEqual(code, 0)
        self.assertIn("status: succeeded", stdout.getvalue())
        self.assertEqual("", stderr.getvalue())

    def test_json_run_is_machine_readable(self):
        stdout = io.StringIO()
        stderr = io.StringIO()

        code = main(["--json", "explain the project architecture"], stdout=stdout, stderr=stderr)
        payload = json.loads(stdout.getvalue())

        self.assertEqual(code, 0)
        self.assertEqual(payload["status"], "succeeded")
        self.assertEqual(payload["routing"]["intent"], "explain")
        self.assertTrue(payload["events"])

    def test_simulated_failure_returns_blocked_and_writes_events(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory(dir="/private/tmp") as tmpdir:
            events_path = str(pathlib.Path(tmpdir) / "events.json")
            code = main(
                [
                    "--max-repair-attempts",
                    "1",
                    "--fail-fingerprint",
                    "validate:test:logic",
                    "--events-out",
                    events_path,
                    "implement a feature with a repeated validation failure",
                ],
                stdout=stdout,
                stderr=stderr,
            )
            events = json.loads(pathlib.Path(events_path).read_text())

        self.assertEqual(code, 2)
        self.assertIn("status: blocked", stdout.getvalue())
        self.assertIn("loop status: blocked", stderr.getvalue())
        self.assertEqual(events[-1]["state"], "report")

    def test_config_file_budget_blocks_run(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory(dir="/private/tmp") as tmpdir:
            config_path = pathlib.Path(tmpdir) / "config.json"
            config_path.write_text(
                json.dumps({"budget": {"max_usd": 0.0000001, "reserved_final_report_usd": 0.0}})
            )
            code = main(
                ["--config", str(config_path), "implement a tiny improvement"],
                stdout=stdout,
                stderr=stderr,
            )

        self.assertEqual(code, 2)
        self.assertIn("status: blocked", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
