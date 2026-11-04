
import unittest

from src.payout.bag_deduction import calculate_bag_deduction


class TestBagDeduction(unittest.TestCase):

    def test_normal_weekly_deduction(self):
        result = calculate_bag_deduction(180000, 500000)
        self.assertEqual(result, 15000)

    def test_deduction_when_balance_is_less_than_weekly_amount(self):
        result = calculate_bag_deduction(10000, 500000)
        self.assertEqual(result, 10000)

    def test_no_deduction_below_threshold(self):
        result = calculate_bag_deduction(180000, 99999)
        self.assertEqual(result, 0)

    def test_deduction_at_exact_threshold(self):
        result = calculate_bag_deduction(180000, 100000)
        self.assertEqual(result, 15000)

    def test_no_deduction_when_balance_is_zero(self):
        result = calculate_bag_deduction(0, 500000)
        self.assertEqual(result, 0)

    def test_no_deduction_when_payable_is_zero(self):
        result = calculate_bag_deduction(180000, 0)
        self.assertEqual(result, 0)

    def test_partial_remaining_balance(self):
        result = calculate_bag_deduction(5000, 200000)
        self.assertEqual(result, 5000)

    def test_negative_balance_rejected(self):
        with self.assertRaises(ValueError):
            calculate_bag_deduction(-100, 200000)

    def test_negative_payable_rejected(self):
        with self.assertRaises(ValueError):
            calculate_bag_deduction(180000, -100)

    def test_boolean_input_rejected(self):
        with self.assertRaises(ValueError):
            calculate_bag_deduction(True, 200000)


if __name__ == "__main__":
    unittest.main()

