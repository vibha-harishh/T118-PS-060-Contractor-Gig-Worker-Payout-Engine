
import unittest

from src.payout.incentives import calculate_weekly_incentive


class TestWeeklyIncentives(unittest.TestCase):

    def test_below_60_tasks(self):
        self.assertEqual(calculate_weekly_incentive(50, 50, "4.5"), 0)

    def test_60_task_tier(self):
        self.assertEqual(calculate_weekly_incentive(60, 60, "4.5"), 60000)

    def test_90_task_tier(self):
        self.assertEqual(calculate_weekly_incentive(90, 90, "4.5"), 120000)

    def test_120_task_tier(self):
        self.assertEqual(calculate_weekly_incentive(120, 120, "4.5"), 200000)

    def test_highest_tier_only(self):
        self.assertEqual(calculate_weekly_incentive(125, 125, "4.5"), 200000)

    def test_cancellation_rate_above_8_percent(self):
        self.assertEqual(calculate_weekly_incentive(91, 100, "4.5"), 0)

    def test_cancellation_rate_exactly_8_percent(self):
        self.assertEqual(calculate_weekly_incentive(92, 100, "4.5"), 120000)

    def test_rating_below_minimum(self):
        self.assertEqual(calculate_weekly_incentive(90, 90, "4.1"), 0)

    def test_rating_exactly_minimum(self):
        self.assertEqual(calculate_weekly_incentive(90, 90, "4.2"), 120000)

    def test_negative_completed_tasks(self):
        with self.assertRaises(ValueError):
            calculate_weekly_incentive(-1, 90, "4.5")

    def test_completed_exceeds_total(self):
        with self.assertRaises(ValueError):
            calculate_weekly_incentive(100, 90, "4.5")

    def test_zero_total_tasks(self):
        self.assertEqual(calculate_weekly_incentive(0, 0, "4.5"), 0)
