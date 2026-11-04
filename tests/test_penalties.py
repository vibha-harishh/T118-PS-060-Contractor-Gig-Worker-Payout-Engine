
import unittest

from src.payout.penalties import calculate_weekly_penalty


class TestWeeklyPenalties(unittest.TestCase):

    def test_no_penalties(self):
        self.assertEqual(
            calculate_weekly_penalty(0, 0, 100000), 0
        )

    def test_first_three_cancellations_free(self):
        self.assertEqual(
            calculate_weekly_penalty(3, 0, 100000), 0
        )

    def test_one_excess_cancellation(self):
        self.assertEqual(
            calculate_weekly_penalty(4, 0, 100000), 5000
        )

    def test_multiple_excess_cancellations(self):
        self.assertEqual(
            calculate_weekly_penalty(6, 0, 100000), 15000
        )

    def test_one_verified_complaint(self):
        self.assertEqual(
            calculate_weekly_penalty(0, 1, 100000), 20000
        )

    def test_multiple_verified_complaints(self):
        self.assertEqual(
            calculate_weekly_penalty(0, 3, 100000), 20000
        )

    def test_combined_penalties(self):
        self.assertEqual(
            calculate_weekly_penalty(5, 2, 100000), 20000
        )

    def test_penalty_cap(self):
        self.assertEqual(
            calculate_weekly_penalty(10, 10, 100000), 20000
        )

    def test_zero_weekly_gross(self):
        self.assertEqual(
            calculate_weekly_penalty(5, 2, 0), 0
        )

    def test_negative_cancellations(self):
        with self.assertRaises(ValueError):
            calculate_weekly_penalty(-1, 0, 100000)

    def test_negative_complaints(self):
        with self.assertRaises(ValueError):
            calculate_weekly_penalty(0, -1, 100000)

    def test_negative_weekly_gross(self):
        with self.assertRaises(ValueError):
            calculate_weekly_penalty(0, 0, -100000)


if __name__ == "__main__":
    unittest.main()
