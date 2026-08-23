import unittest

from retry import retry_delays


class RetryDelayTests(unittest.TestCase):
    def test_one_attempt_has_no_delay(self) -> None:
        self.assertEqual(retry_delays(1), [])

    def test_delays_exist_between_attempts(self) -> None:
        self.assertEqual(retry_delays(4), [1, 2, 4])

    def test_custom_base(self) -> None:
        self.assertEqual(retry_delays(3, base_seconds=5), [5, 10])

    def test_rejects_invalid_values(self) -> None:
        with self.assertRaises(ValueError):
            retry_delays(0)
        with self.assertRaises(ValueError):
            retry_delays(2, base_seconds=0)


if __name__ == "__main__":
    unittest.main()
