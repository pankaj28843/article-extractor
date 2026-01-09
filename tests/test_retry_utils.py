"""Tests for retry_utils module."""

from article_extractor.retry_utils import exponential_backoff_delay


class TestExponentialBackoffDelay:
    def test_first_attempt_returns_base_delay(self):
        delay = exponential_backoff_delay(1)
        assert abs(delay - 0.3) < 1e-9

    def test_multiple_attempts_increase_linearly(self):
        assert abs(exponential_backoff_delay(1) - 0.3) < 1e-9
        assert abs(exponential_backoff_delay(2) - 0.6) < 1e-9
        assert abs(exponential_backoff_delay(3) - 0.9) < 1e-9
        assert abs(exponential_backoff_delay(4) - 1.2) < 1e-9

    def test_caps_at_max_delay(self):
        assert abs(exponential_backoff_delay(5) - 1.5) < 1e-9
        assert abs(exponential_backoff_delay(6) - 1.5) < 1e-9
        assert abs(exponential_backoff_delay(10) - 1.5) < 1e-9
        assert abs(exponential_backoff_delay(100) - 1.5) < 1e-9

    def test_custom_base_delay(self):
        delay = exponential_backoff_delay(1, base_delay=0.5)
        assert abs(delay - 0.5) < 1e-9

    def test_custom_max_delay(self):
        delay = exponential_backoff_delay(10, max_delay=2.0)
        assert abs(delay - 2.0) < 1e-9

    def test_custom_base_and_max(self):
        assert (
            abs(exponential_backoff_delay(1, base_delay=1.0, max_delay=3.0) - 1.0)
            < 1e-9
        )
        assert (
            abs(exponential_backoff_delay(2, base_delay=1.0, max_delay=3.0) - 2.0)
            < 1e-9
        )
        assert (
            abs(exponential_backoff_delay(3, base_delay=1.0, max_delay=3.0) - 3.0)
            < 1e-9
        )
        assert (
            abs(exponential_backoff_delay(4, base_delay=1.0, max_delay=3.0) - 3.0)
            < 1e-9
        )

    def test_zero_attempt(self):
        delay = exponential_backoff_delay(0)
        assert abs(delay) < 1e-9

    def test_negative_attempt(self):
        # Negative attempts return negative delays - callers should validate
        delay = exponential_backoff_delay(-1)
        assert abs(delay - (-0.3)) < 1e-9

    def test_fractional_attempts(self):
        # In case attempt is calculated as a float
        delay = exponential_backoff_delay(2.5, base_delay=0.3)
        assert abs(delay - 0.75) < 1e-9

    def test_very_large_attempt(self):
        delay = exponential_backoff_delay(10000)
        assert abs(delay - 1.5) < 1e-9  # Should cap at max_delay
