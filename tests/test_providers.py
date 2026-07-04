import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from orchestrator.providers import (
    ProviderAuthError,
    ProviderMalformedOutputError,
    ProviderRateLimitError,
    ProviderRefusalError,
    ProviderTimeoutError,
    RetryPolicy,
)


class ProviderErrorTests(unittest.TestCase):
    def test_error_taxonomy_declares_retry_and_repair_semantics(self):
        cases = [
            (ProviderTimeoutError("timeout", "m"), "timeout", True, False),
            (ProviderRateLimitError("rate", "m"), "rate_limit", True, False),
            (ProviderAuthError("auth", "m"), "auth", False, False),
            (ProviderRefusalError("refusal", "m"), "refusal", False, True),
            (ProviderMalformedOutputError("bad json", "m"), "malformed_output", True, True),
        ]

        for error, kind, retryable, consumes in cases:
            with self.subTest(kind=kind):
                self.assertEqual(error.kind, kind)
                self.assertEqual(error.retryable, retryable)
                self.assertEqual(error.consumes_repair_attempt, consumes)
                self.assertEqual(error.failure_fingerprint, "provider:%s:m" % kind)

    def test_retry_policy_uses_retryable_flag_and_backoff(self):
        policy = RetryPolicy(max_attempts=3, base_delay_seconds=2.0, max_delay_seconds=5.0)
        timeout = ProviderTimeoutError("timeout", "m")
        auth = ProviderAuthError("auth", "m")

        self.assertTrue(policy.can_retry(timeout, attempt=1))
        self.assertTrue(policy.can_retry(timeout, attempt=2))
        self.assertFalse(policy.can_retry(timeout, attempt=3))
        self.assertFalse(policy.can_retry(auth, attempt=1))
        self.assertEqual(policy.delay_for(timeout, attempt=1), 2.0)
        self.assertEqual(policy.delay_for(timeout, attempt=3), 5.0)

    def test_rate_limit_retry_after_is_capped(self):
        policy = RetryPolicy(max_attempts=3, max_delay_seconds=10.0)
        error = ProviderRateLimitError("rate", "m", retry_after_seconds=30.0)

        self.assertEqual(policy.delay_for(error, attempt=1), 10.0)


if __name__ == "__main__":
    unittest.main()
