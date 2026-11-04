"""Unit tests for surge pay calculations."""

import unittest
from decimal import Decimal

from src.calculations.surge import calculate_surge_pay


class TestSurgePay(unittest.TestCase):

    def test_no_surge(self):
        self.assertEqual(
            calculate_surge_pay(2500, Decimal("1.0")), 2500
        )

    def test_slot_surge(self):
        self.assertEqual(
            calculate_surge_pay(2500, Decimal("1.3")), 3250
        )

    def test_rain_surge(self):
        self.assertEqual(
            calculate_surge_pay(2500, Decimal("1.5")), 3750
        )

    def test_rounding_half_up(self):
        self.assertEqual(
            calculate_surge_pay(1, Decimal("1.5")), 2
        )

    def test_zero_base_pay(self):
        self.assertEqual(
            calculate_surge_pay(0, Decimal("1.5")), 0
        )

    def test_negative_base_pay_rejected(self):
        with self.assertRaises(ValueError):
            calculate_surge_pay(-100, Decimal("1.3"))

    def test_invalid_surge_multiplier_rejected(self):
        with self.assertRaises(ValueError):
            calculate_surge_pay(2500, Decimal("1.8"))


if __name__ == "__main__":
    unittest.main()