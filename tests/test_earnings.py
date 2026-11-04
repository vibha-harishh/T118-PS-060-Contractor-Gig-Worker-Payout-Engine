
"""
Tests for base task pay calculations.
"""

import unittest

from src.calculations.earnings import calculate_base_task_pay


class TestBaseTaskPay(unittest.TestCase):

    def test_completed_task_up_to_3_km(self):
        self.assertEqual(
            calculate_base_task_pay("TASK_COMPLETED", 2),
            2500
        )

    def test_completed_task_exactly_3_km(self):
        self.assertEqual(
            calculate_base_task_pay("TASK_COMPLETED", 3),
            2500
        )

    def test_completed_task_beyond_3_km(self):
        self.assertEqual(
            calculate_base_task_pay("TASK_COMPLETED", 5),
            3700
        )

    def test_completed_task_decimal_distance(self):
        self.assertEqual(
            calculate_base_task_pay("TASK_COMPLETED", 3.5),
            2800
        )

    def test_completed_task_rounds_half_up(self):
        self.assertEqual(
            calculate_base_task_pay("TASK_COMPLETED", 3.25),
            2700
        )

    def test_customer_cancelled_after_pickup(self):
        self.assertEqual(
            calculate_base_task_pay(
                "CUSTOMER_CANCELLED_POST_PICKUP", 5
            ),
            2000
        )

    def test_customer_cancelled_before_pickup(self):
        self.assertEqual(
            calculate_base_task_pay(
                "CUSTOMER_CANCELLED_PRE_PICKUP", 5
            ),
            0
        )

    def test_partner_cancelled(self):
        self.assertEqual(
            calculate_base_task_pay("PARTNER_CANCELLED", 5),
            0
        )

    def test_negative_distance_rejected(self):
        with self.assertRaises(ValueError):
            calculate_base_task_pay("TASK_COMPLETED", -2)

    def test_invalid_distance_rejected(self):
        with self.assertRaises(ValueError):
            calculate_base_task_pay("TASK_COMPLETED", "abc")

    def test_infinite_distance_rejected(self):
        with self.assertRaises(ValueError):
            calculate_base_task_pay("TASK_COMPLETED", float("inf"))

    def test_unsupported_event_type_rejected(self):
        with self.assertRaises(ValueError):
            calculate_base_task_pay("UNKNOWN_EVENT", 5)


if __name__ == "__main__":
    unittest.main()
