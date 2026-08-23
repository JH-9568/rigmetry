import unittest

from cart import discounted_total


class DiscountedTotalTests(unittest.TestCase):
    def test_ten_percent(self) -> None:
        self.assertEqual(discounted_total(2500, 10), 2250)

    def test_floor_arithmetic(self) -> None:
        self.assertEqual(discounted_total(999, 15), 850)

    def test_zero_and_full_discount(self) -> None:
        self.assertEqual(discounted_total(500, 0), 500)
        self.assertEqual(discounted_total(500, 100), 0)

    def test_rejects_invalid_values(self) -> None:
        with self.assertRaises(ValueError):
            discounted_total(-1, 10)
        with self.assertRaises(ValueError):
            discounted_total(100, 101)


if __name__ == "__main__":
    unittest.main()
