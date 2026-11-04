"""
Tests for weekly payout integration.
"""

import io
import unittest

import config
from database.db import init_db, get_db_connection
from src.models.partner import register_partner
from src.ingestion.task_loader import import_tasks_from_csv
from src.payout.weekly_payout import calculate_weekly_payout


class TestWeeklyPayout(unittest.TestCase):

    def setUp(self):
        self.test_db_path = config.BASE_DIR / "test_weekly_payout_temp.db"

        if self.test_db_path.exists():
            self.test_db_path.unlink()

        init_db(self.test_db_path)

        register_partner(
            partner_id="P101",
            partner_name="Test Partner",
            partner_type="INDIVIDUAL",
            category="DELIVERY",
            onboarding_date="2026-11-01",
            pan="ABCDE1234F",
            db_path=self.test_db_path,
        )

    def tearDown(self):
        if self.test_db_path.exists():
            self.test_db_path.unlink()

    def import_tasks(self, csv_data):
        return import_tasks_from_csv(
            io.StringIO(csv_data),
            db_path=self.test_db_path,
        )

    def test_weekly_payout_calculations(self):
        """Test task pay, surge, penalties and bag deduction."""

        csv_data = """task_id,partner_id,task_type,event_type,distance_km,is_slot_surge,is_rain_surge,rating,task_timestamp
T001,P101,DELIVERY,TASK_COMPLETED,200,1,1,4.8,2026-11-02 10:00:00
T002,P101,DELIVERY,PARTNER_CANCELLED,0,0,0,,2026-11-02 11:00:00
T003,P101,DELIVERY,PARTNER_CANCELLED,0,0,0,,2026-11-02 12:00:00
T004,P101,DELIVERY,PARTNER_CANCELLED,0,0,0,,2026-11-02 13:00:00
T005,P101,DELIVERY,PARTNER_CANCELLED,0,0,0,,2026-11-02 14:00:00
"""

        summary = self.import_tasks(csv_data)
        self.assertEqual(summary.successful_imports, 5)

        # Add one verified complaint.
        conn = get_db_connection(self.test_db_path)
        try:
            conn.execute(
                """
                INSERT INTO complaints (
                    complaint_id,
                    partner_id,
                    week_identifier,
                    is_verified
                )
                VALUES (?, ?, ?, ?);
                """,
                ("C001", "P101", "2026-W45", 1),
            )
            conn.commit()
        finally:
            conn.close()

        result = calculate_weekly_payout(
            "P101",
            "2026-W45",
            db_path=self.test_db_path,
        )

        # 200 km: ₹25 + (197 × ₹6) = ₹1207.
        # Both surges apply, so only 1.5x is used.
        self.assertEqual(result["gross_task_pay_paise"], 181050)

        self.assertEqual(result["total_tasks_assigned"], 5)
        self.assertEqual(result["completed_tasks"], 1)
        self.assertEqual(result["partner_cancellations"], 4)

        # 4 cancellations beyond the first 3 = ₹50.
        # 1 verified complaint = ₹200.
        self.assertEqual(
            result["raw_cancellation_penalty_paise"],
            5000,
        )
        self.assertEqual(
            result["raw_complaint_penalty_paise"],
            20000,
        )
        self.assertEqual(
            result["raw_total_penalties_paise"],
            25000,
        )

        self.assertEqual(
            result["capped_total_penalties_paise"],
            25000,
        )

        # ₹1810.50 - ₹250 = ₹1560.50.
        self.assertEqual(
            result["net_before_bag_deduction_paise"],
            156050,
        )

        # ₹150 bag deduction.
        self.assertEqual(
            result["bag_deduction_applied_paise"],
            15000,
        )

        self.assertEqual(
            result["remaining_bag_balance_paise"],
            165000,
        )

        self.assertEqual(
            result["net_payable_before_tds_paise"],
            141050,
        )

    def test_duplicate_weekly_payout_does_not_deduct_twice(self):
        """Running the same weekly payout twice must not deduct the bag twice."""

        csv_data = """task_id,partner_id,task_type,event_type,distance_km,is_slot_surge,is_rain_surge,rating,task_timestamp
T010,P101,DELIVERY,TASK_COMPLETED,200,0,0,4.8,2026-11-02 10:00:00
"""

        self.import_tasks(csv_data)

        first_result = calculate_weekly_payout(
            "P101",
            "2026-W45",
            db_path=self.test_db_path,
        )

        second_result = calculate_weekly_payout(
            "P101",
            "2026-W45",
            db_path=self.test_db_path,
        )

        self.assertEqual(
            first_result["bag_deduction_applied_paise"],
            15000,
        )

        self.assertEqual(
            second_result["bag_deduction_applied_paise"],
            15000,
        )

        conn = get_db_connection(self.test_db_path)
        try:
            row = conn.execute(
                """
                SELECT bag_deduction_balance_paise
                FROM partners
                WHERE partner_id = ?;
                """,
                ("P101",),
            ).fetchone()
        finally:
            conn.close()

        self.assertEqual(row["bag_deduction_balance_paise"], 165000)

    def test_missing_partner_rejected(self):
        with self.assertRaises(ValueError):
            calculate_weekly_payout(
                "UNKNOWN",
                "2026-W45",
                db_path=self.test_db_path,
            )

    def test_no_tasks_rejected(self):
        with self.assertRaises(ValueError):
            calculate_weekly_payout(
                "P101",
                "2026-W45",
                db_path=self.test_db_path,
            )


if __name__ == "__main__":
    unittest.main()
