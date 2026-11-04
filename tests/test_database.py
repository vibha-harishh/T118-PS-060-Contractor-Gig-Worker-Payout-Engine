"""
Step 0 Foundation Tests: Configuration & SQLite Database Layer
Verifies:
- Decimal arithmetic and integer paise financial standards.
- Indian Standard Time (Asia/Kolkata) timezone utilities.
- Surge resolution rules: slot (1.3x), rain (1.5x), higher multiplier when both apply (1.5x, not multiplied).
- SQLite schema tables and foreign key enforcement on every connection.
- Strict CHECK constraint on surge_multiplier (strictly 1.0, 1.3, or 1.5; rejects 1.8, 2.0, etc.).
- PAN consistency constraints (MISSING allows NULL; VALID/INVALID require supplied PAN).
- Non-negative distance, duration, and bag balance constraints.
- Rating constraints (1.0 to 5.0 or NULL).
- Task event type validation with CHECK constraints and single canonical field.
- Unverified bank details and missing PAN registration compatibility.
"""

from datetime import datetime
from decimal import Decimal
import sqlite3
import unittest
from pathlib import Path

import config
from database.db import (
    DatabaseError,
    db_session,
    get_db_connection,
    init_db,
    reset_db,
)


class TestConfigRules(unittest.TestCase):
    """Verifies that all PS-060 official constants, Decimal precision, and timezone helpers are accurate."""

    def test_timezone_is_ist(self):
        """Verify timezone is configured as Indian Standard Time (Asia/Kolkata)."""
        self.assertEqual(config.TIMEZONE_NAME, "Asia/Kolkata")
        self.assertEqual(config.IST.key, "Asia/Kolkata")

        # Test IST datetime conversions
        dt_utc = datetime(2026, 11, 2, 15, 0, 0, tzinfo=config.zoneinfo.ZoneInfo("UTC"))
        dt_ist = config.to_ist(dt_utc)
        self.assertEqual(dt_ist.hour, 20)
        self.assertEqual(dt_ist.minute, 30)
        self.assertEqual(config.get_week_identifier(dt_ist), "2026-W45")

    def test_currency_conversion_helpers_with_decimal(self):
        """Verify rupees_to_paise and paise_to_rupees use Decimal with exact rounding."""
        self.assertEqual(config.rupees_to_paise(Decimal("25.00")), 2500)
        self.assertEqual(config.rupees_to_paise(Decimal("6.00")), 600)
        self.assertEqual(config.rupees_to_paise("1.50"), 150)
        self.assertEqual(config.rupees_to_paise(0), 0)

        self.assertEqual(config.paise_to_rupees(2500), Decimal("25.00"))
        self.assertEqual(config.paise_to_rupees(600), Decimal("6.00"))
        self.assertEqual(config.paise_to_rupees(150), Decimal("1.50"))
        self.assertEqual(config.paise_to_rupees(0), Decimal("0.00"))

    def test_partner_enums(self):
        self.assertIn("INDIVIDUAL", config.PARTNER_TYPES)
        self.assertIn("FIRM", config.PARTNER_TYPES)
        self.assertIn("VALID", config.PAN_STATUSES)
        self.assertIn("INVALID", config.PAN_STATUSES)
        self.assertIn("MISSING", config.PAN_STATUSES)
        self.assertIn("DELIVERY", config.CATEGORIES)
        self.assertIn("SERVICE_PROFESSIONAL", config.CATEGORIES)

    def test_task_event_types(self):
        self.assertIn("TASK_COMPLETED", config.EVENT_TYPES)
        self.assertIn("CUSTOMER_CANCELLED_POST_PICKUP", config.EVENT_TYPES)
        self.assertIn("CUSTOMER_CANCELLED_PRE_PICKUP", config.EVENT_TYPES)
        self.assertIn("PARTNER_CANCELLED", config.EVENT_TYPES)

    def test_base_pay_constants(self):
        # Decimal Rupees
        self.assertEqual(config.BASE_PAY_FLAT_RUPEES, Decimal("25.00"))
        self.assertEqual(config.BASE_PAY_THRESHOLD_KM, Decimal("3.0"))
        self.assertEqual(config.BASE_PAY_RATE_PER_EXTRA_KM_RUPEES, Decimal("6.00"))
        self.assertEqual(config.CUSTOMER_CANCELLATION_POST_PICKUP_RUPEES, Decimal("20.00"))
        # Paise
        self.assertEqual(config.BASE_PAY_FLAT_PAISE, 2500)
        self.assertEqual(config.BASE_PAY_RATE_PER_EXTRA_KM_PAISE, 600)
        self.assertEqual(config.CUSTOMER_CANCELLATION_POST_PICKUP_PAISE, 2000)
        self.assertEqual(config.CUSTOMER_CANCELLATION_PRE_PICKUP_PAISE, 0)
        self.assertEqual(config.PARTNER_CANCELLATION_PAISE, 0)

    def test_surge_constants_and_resolution(self):
        """Verify surge multipliers and that higher multiplier (1.5x) is chosen when both apply."""
        self.assertEqual(config.SLOT_SURGE_MULTIPLIER, Decimal("1.3"))
        self.assertEqual(config.RAIN_SURGE_MULTIPLIER, Decimal("1.5"))
        self.assertEqual(config.NO_SURGE_MULTIPLIER, Decimal("1.0"))

        # Case 1: Neither applies
        self.assertEqual(config.resolve_surge_multiplier(False, False), Decimal("1.0"))
        # Case 2: Slot surge only
        self.assertEqual(config.resolve_surge_multiplier(True, False), Decimal("1.3"))
        # Case 3: Rain surge only
        self.assertEqual(config.resolve_surge_multiplier(False, True), Decimal("1.5"))
        # Case 4: Both apply -> MUST BE 1.5, NOT 1.3 * 1.5 = 1.95
        self.assertEqual(config.resolve_surge_multiplier(True, True), Decimal("1.5"))
        self.assertNotEqual(config.resolve_surge_multiplier(True, True), Decimal("1.95"))

    def test_incentive_constants(self):
        self.assertEqual(
            config.INCENTIVE_TIERS_PAISE,
            [(120, 200000), (90, 120000), (60, 60000)]
        )
        self.assertEqual(config.INCENTIVE_MAX_CANCELLATION_RATE, Decimal("0.08"))
        self.assertEqual(config.INCENTIVE_MIN_RATING, Decimal("4.2"))

    def test_penalty_constants(self):
        self.assertEqual(config.PENALTY_FREE_PARTNER_CANCELLATIONS, 3)
        self.assertEqual(config.PENALTY_PER_EXCESS_PARTNER_CANCELLATION_RUPEES, Decimal("50.00"))
        self.assertEqual(config.PENALTY_PER_EXCESS_PARTNER_CANCELLATION_PAISE, 5000)
        self.assertEqual(config.PENALTY_PER_VERIFIED_COMPLAINT_RUPEES, Decimal("200.00"))
        self.assertEqual(config.PENALTY_PER_VERIFIED_COMPLAINT_PAISE, 20000)
        self.assertEqual(config.PENALTY_CAP_GROSS_PERCENTAGE, Decimal("0.20"))

    def test_equipment_constants(self):
        self.assertEqual(config.BAG_TOTAL_AMOUNT_RUPEES, Decimal("1800.00"))
        self.assertEqual(config.BAG_TOTAL_AMOUNT_PAISE, 180000)
        self.assertEqual(config.BAG_WEEKLY_DEDUCTION_RUPEES, Decimal("150.00"))
        self.assertEqual(config.BAG_WEEKLY_DEDUCTION_PAISE, 15000)
        self.assertEqual(config.BAG_DEDUCTION_NET_PAYABLE_THRESHOLD_RUPEES, Decimal("1000.00"))
        self.assertEqual(config.BAG_DEDUCTION_NET_PAYABLE_THRESHOLD_PAISE, 100000)


class TestDatabaseFoundation(unittest.TestCase):
    """Tests SQLite connection, schema creation, constraints, and sessions."""

    def setUp(self):
        self.test_db_path = config.BASE_DIR / "test_payout_temp.db"
        if self.test_db_path.exists():
            self.test_db_path.unlink()
        init_db(self.test_db_path)

    def tearDown(self):
        if self.test_db_path.exists():
            self.test_db_path.unlink()

    def test_schema_tables_exist(self):
        """Verify all 4 required tables exist in the initialized schema."""
        conn = get_db_connection(self.test_db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row["name"] for row in cursor.fetchall()]
        conn.close()

        self.assertIn("partners", tables)
        self.assertIn("tasks", tables)
        self.assertIn("complaints", tables)
        self.assertIn("weekly_earnings", tables)

    def test_foreign_keys_enabled_on_connection(self):
        """Verify that every connection explicitly has foreign keys turned on."""
        conn = get_db_connection(self.test_db_path)
        fk_status = conn.execute("PRAGMA foreign_keys;").fetchone()[0]
        conn.close()
        self.assertEqual(fk_status, 1, "Foreign keys must be actively enabled")

    def test_partner_schema_supports_all_required_fields_and_paise(self):
        """Verify partners table contains all required columns with bag balance in paise."""
        conn = get_db_connection(self.test_db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(partners);")
        columns = {row["name"]: row for row in cursor.fetchall()}
        conn.close()

        expected_cols = [
            "partner_id",
            "partner_name",
            "partner_type",
            "pan",
            "pan_status",
            "category",
            "phone",
            "bank_account_number",
            "ifsc_code",
            "bank_verification_status",
            "city",
            "rating",
            "status",
            "bag_deduction_balance_paise",
            "onboarding_date",
            "created_at",
        ]
        for col in expected_cols:
            self.assertIn(col, columns, f"Column '{col}' is missing in partners table")

        # Verify PAN is nullable
        self.assertEqual(columns["pan"]["notnull"], 0, "PAN must allow NULL values")

    def test_partner_pan_consistency_constraints(self):
        """
        Verify PAN consistency rules:
        - pan_status='MISSING' requires pan IS NULL.
        - pan_status='VALID' or 'INVALID' requires pan IS NOT NULL.
        - Multiple partners with NULL PAN are allowed.
        """
        with db_session(self.test_db_path) as conn:
            # 1. Valid registration with MISSING PAN (pan must be NULL)
            conn.execute(
                """
                INSERT INTO partners (
                    partner_id, partner_name, partner_type, pan, pan_status, category, onboarding_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                ("P101", "Ramesh Kumar", "INDIVIDUAL", None, "MISSING", "DELIVERY", "2026-11-01")
            )
            # 2. Second partner with MISSING PAN (verifies partial index doesn't block duplicate NULLs)
            conn.execute(
                """
                INSERT INTO partners (
                    partner_id, partner_name, partner_type, pan, pan_status, category, onboarding_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                ("P102", "Quick Logix Logistics", "FIRM", None, "MISSING", "DELIVERY", "2026-11-02")
            )
            # 3. Valid registration with VALID PAN
            conn.execute(
                """
                INSERT INTO partners (
                    partner_id, partner_name, partner_type, pan, pan_status, category, onboarding_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                ("P103", "Priya Sharma", "INDIVIDUAL", "ABCDE1234F", "VALID", "DELIVERY", "2026-11-03")
            )
            # 4. Valid registration with INVALID PAN (supplied string, marked INVALID)
            conn.execute(
                """
                INSERT INTO partners (
                    partner_id, partner_name, partner_type, pan, pan_status, category, onboarding_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                ("P104", "Vikram Singh", "INDIVIDUAL", "INV12345", "INVALID", "DELIVERY", "2026-11-03")
            )

        # 5. INCONSISTENT: MISSING status but PAN supplied -> must fail
        with self.assertRaises((DatabaseError, sqlite3.IntegrityError)):
            with db_session(self.test_db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO partners (
                        partner_id, partner_name, partner_type, pan, pan_status, category, onboarding_date
                    ) VALUES (?, ?, ?, ?, ?, ?, ?);
                    """,
                    ("P105", "Faulty Partner 1", "INDIVIDUAL", "ABCDE1234F", "MISSING", "DELIVERY", "2026-11-04")
                )

        # 6. INCONSISTENT: VALID status but PAN is NULL -> must fail
        with self.assertRaises((DatabaseError, sqlite3.IntegrityError)):
            with db_session(self.test_db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO partners (
                        partner_id, partner_name, partner_type, pan, pan_status, category, onboarding_date
                    ) VALUES (?, ?, ?, ?, ?, ?, ?);
                    """,
                    ("P106", "Faulty Partner 2", "INDIVIDUAL", None, "VALID", "DELIVERY", "2026-11-04")
                )

    def test_partner_negative_bag_balance_fails(self):
        """Verify bag_deduction_balance_paise >= 0 constraint."""
        with self.assertRaises((DatabaseError, sqlite3.IntegrityError)):
            with db_session(self.test_db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO partners (
                        partner_id, partner_name, partner_type, category,
                        bag_deduction_balance_paise, onboarding_date
                    ) VALUES (?, ?, ?, ?, ?, ?);
                    """,
                    ("P107", "Negative Bag Partner", "INDIVIDUAL", "DELIVERY", -500, "2026-11-01")
                )

    def test_partner_rating_range_constraint(self):
        """Verify partner rating must be between 1.0 and 5.0 when provided."""
        # Invalid rating: 6.0
        with self.assertRaises((DatabaseError, sqlite3.IntegrityError)):
            with db_session(self.test_db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO partners (
                        partner_id, partner_name, partner_type, category, rating, onboarding_date
                    ) VALUES (?, ?, ?, ?, ?, ?);
                    """,
                    ("P108", "High Rating Partner", "INDIVIDUAL", "DELIVERY", 6.0, "2026-11-01")
                )

        # Invalid rating: 0.5
        with self.assertRaises((DatabaseError, sqlite3.IntegrityError)):
            with db_session(self.test_db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO partners (
                        partner_id, partner_name, partner_type, category, rating, onboarding_date
                    ) VALUES (?, ?, ?, ?, ?, ?);
                    """,
                    ("P109", "Low Rating Partner", "INDIVIDUAL", "DELIVERY", 0.5, "2026-11-01")
                )

    def test_tasks_table_event_types_and_paise(self):
        """Verify tasks table event_type constraint and integer paise columns."""
        with db_session(self.test_db_path) as conn:
            conn.execute(
                """
                INSERT INTO partners (
                    partner_id, partner_name, partner_type, category, onboarding_date
                ) VALUES (?, ?, ?, ?, ?);
                """,
                ("P201", "Delivery Pro", "INDIVIDUAL", "DELIVERY", "2026-11-01")
            )
            # Insert valid completed task with paise
            conn.execute(
                """
                INSERT INTO tasks (
                    task_id, partner_id, task_type, event_type, distance_km,
                    slot_type, is_slot_surge, is_rain_surge, rating,
                    base_pay_paise, surge_multiplier, final_task_pay_paise,
                    task_timestamp, task_date, week_identifier
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    "T001", "P201", "DELIVERY", "TASK_COMPLETED", 5.5,
                    "DINNER_PEAK", 1, 0, 4.8,
                    4000, 1.3, 5200, "2026-11-02 20:30:00+05:30", "2026-11-02", "2026-W45"
                )
            )

        conn = get_db_connection(self.test_db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tasks WHERE task_id = 'T001';")
        row = cursor.fetchone()
        conn.close()

        self.assertIsNotNone(row)
        self.assertEqual(row["event_type"], "TASK_COMPLETED")
        self.assertEqual(row["base_pay_paise"], 4000)        # ₹40.00
        self.assertEqual(row["final_task_pay_paise"], 5200)  # ₹52.00
        self.assertEqual(row["rating"], 4.8)
        self.assertEqual(row["week_identifier"], "2026-W45")

    def test_surge_multiplier_allowed_values(self):
        """Verify tasks table accepts exactly 1.0, 1.3, and 1.5 as surge_multiplier."""
        with db_session(self.test_db_path) as conn:
            conn.execute(
                """
                INSERT INTO partners (
                    partner_id, partner_name, partner_type, category, onboarding_date
                ) VALUES (?, ?, ?, ?, ?);
                """,
                ("P202", "Surge Tester", "INDIVIDUAL", "DELIVERY", "2026-11-01")
            )
            # 1.0 multiplier succeeds
            conn.execute(
                """
                INSERT INTO tasks (
                    task_id, partner_id, event_type, distance_km, surge_multiplier,
                    task_timestamp, task_date, week_identifier
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                ("T101", "P202", "TASK_COMPLETED", 2.0, 1.0, "2026-11-02 10:00:00+05:30", "2026-11-02", "2026-W45")
            )
            # 1.3 multiplier succeeds
            conn.execute(
                """
                INSERT INTO tasks (
                    task_id, partner_id, event_type, distance_km, surge_multiplier,
                    task_timestamp, task_date, week_identifier
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                ("T102", "P202", "TASK_COMPLETED", 2.0, 1.3, "2026-11-02 13:00:00+05:30", "2026-11-02", "2026-W45")
            )
            # 1.5 multiplier succeeds
            conn.execute(
                """
                INSERT INTO tasks (
                    task_id, partner_id, event_type, distance_km, surge_multiplier,
                    task_timestamp, task_date, week_identifier
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                ("T103", "P202", "TASK_COMPLETED", 2.0, 1.5, "2026-11-02 18:00:00+05:30", "2026-11-02", "2026-W45")
            )

        # Verification of inserted values
        conn = get_db_connection(self.test_db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT task_id, surge_multiplier FROM tasks WHERE partner_id = 'P202' ORDER BY task_id;")
        rows = cursor.fetchall()
        conn.close()

        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["surge_multiplier"], 1.0)
        self.assertEqual(rows[1]["surge_multiplier"], 1.3)
        self.assertEqual(rows[2]["surge_multiplier"], 1.5)

    def test_surge_multiplier_rejection_of_invalid_values(self):
        """Verify CHECK constraint rejects unpermitted surge multipliers (e.g. 1.8, 2.0, 0.8)."""
        with db_session(self.test_db_path) as conn:
            conn.execute(
                """
                INSERT INTO partners (
                    partner_id, partner_name, partner_type, category, onboarding_date
                ) VALUES (?, ?, ?, ?, ?);
                """,
                ("P203", "Invalid Surge Tester", "INDIVIDUAL", "DELIVERY", "2026-11-01")
            )

        # Rejection of 1.8
        with self.assertRaises((DatabaseError, sqlite3.IntegrityError)):
            with db_session(self.test_db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO tasks (
                        task_id, partner_id, event_type, distance_km, surge_multiplier,
                        task_timestamp, task_date, week_identifier
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    ("T104", "P203", "TASK_COMPLETED", 2.0, 1.8, "2026-11-02 10:00:00+05:30", "2026-11-02", "2026-W45")
                )

        # Rejection of 2.0
        with self.assertRaises((DatabaseError, sqlite3.IntegrityError)):
            with db_session(self.test_db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO tasks (
                        task_id, partner_id, event_type, distance_km, surge_multiplier,
                        task_timestamp, task_date, week_identifier
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    ("T105", "P203", "TASK_COMPLETED", 2.0, 2.0, "2026-11-02 10:00:00+05:30", "2026-11-02", "2026-W45")
                )

        # Rejection of 0.8
        with self.assertRaises((DatabaseError, sqlite3.IntegrityError)):
            with db_session(self.test_db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO tasks (
                        task_id, partner_id, event_type, distance_km, surge_multiplier,
                        task_timestamp, task_date, week_identifier
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    ("T106", "P203", "TASK_COMPLETED", 2.0, 0.8, "2026-11-02 10:00:00+05:30", "2026-11-02", "2026-W45")
                )

    def test_tasks_negative_distance_fails(self):
        """Verify distance_km >= 0.0 constraint."""
        with db_session(self.test_db_path) as conn:
            conn.execute(
                """
                INSERT INTO partners (
                    partner_id, partner_name, partner_type, category, onboarding_date
                ) VALUES (?, ?, ?, ?, ?);
                """,
                ("P204", "Driver Negative", "INDIVIDUAL", "DELIVERY", "2026-11-01")
            )

        with self.assertRaises((DatabaseError, sqlite3.IntegrityError)):
            with db_session(self.test_db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO tasks (
                        task_id, partner_id, event_type, distance_km,
                        task_timestamp, task_date, week_identifier
                    ) VALUES (?, ?, ?, ?, ?, ?, ?);
                    """,
                    ("T998", "P204", "TASK_COMPLETED", -2.5, "2026-11-02 12:00:00+05:30", "2026-11-02", "2026-W45")
                )

    def test_tasks_invalid_event_type_fails(self):
        """Verify check constraint rejects unknown or unapproved event types."""
        with db_session(self.test_db_path) as conn:
            conn.execute(
                """
                INSERT INTO partners (
                    partner_id, partner_name, partner_type, category, onboarding_date
                ) VALUES (?, ?, ?, ?, ?);
                """,
                ("P301", "Delivery Partner", "INDIVIDUAL", "DELIVERY", "2026-11-01")
            )

        with self.assertRaises((DatabaseError, sqlite3.IntegrityError)):
            with db_session(self.test_db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO tasks (
                        task_id, partner_id, event_type, distance_km,
                        task_timestamp, task_date, week_identifier
                    ) VALUES (?, ?, ?, ?, ?, ?, ?);
                    """,
                    ("T999", "P301", "RANDOM_INVALID_EVENT", 3.0, "2026-11-02 12:00:00+05:30", "2026-11-02", "2026-W45")
                )

    def test_foreign_key_enforcement(self):
        """Verify foreign key constraint blocks task insertion for non-existent partner."""
        conn = get_db_connection(self.test_db_path)
        cursor = conn.cursor()

        with self.assertRaises(sqlite3.IntegrityError):
            cursor.execute(
                """
                INSERT INTO tasks (
                    task_id, partner_id, event_type, distance_km,
                    task_timestamp, task_date, week_identifier
                ) VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                ("T999", "NON_EXISTENT_P999", "TASK_COMPLETED", 5.0, "2026-11-02 12:00:00+05:30", "2026-11-02", "2026-W45")
            )
            conn.commit()

        conn.close()

    def test_transaction_rollback_on_error(self):
        """Verify that db_session rolls back partial changes if an error occurs."""
        try:
            with db_session(self.test_db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO partners (
                        partner_id, partner_name, partner_type, category, onboarding_date
                    ) VALUES (?, ?, ?, ?, ?);
                    """,
                    ("P401", "Anil Rao", "INDIVIDUAL", "DELIVERY", "2026-11-01")
                )
                # Intentionally cause duplicate primary key error
                conn.execute(
                    """
                    INSERT INTO partners (
                        partner_id, partner_name, partner_type, category, onboarding_date
                    ) VALUES (?, ?, ?, ?, ?);
                    """,
                    ("P401", "Duplicate Anil", "INDIVIDUAL", "DELIVERY", "2026-11-01")
                )
        except DatabaseError:
            pass  # Expected rollback

        conn = get_db_connection(self.test_db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM partners WHERE partner_id = 'P401';")
        row = cursor.fetchone()
        conn.close()

        self.assertIsNone(row)


if __name__ == "__main__":
    unittest.main()
