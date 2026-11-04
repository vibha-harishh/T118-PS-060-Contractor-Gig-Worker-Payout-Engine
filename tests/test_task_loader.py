"""
Verify importing all 4 approved event types and storing raw task data.
Payout fields remain at their initial defaults until later calculation steps.
"""

from decimal import Decimal
import io
import unittest
from pathlib import Path

import config
from database.db import get_db_connection, init_db
from src.ingestion.task_loader import (
    TaskImportRowError,
    TaskImportSummary,
    import_tasks_from_csv,
)

from src.models.partner import register_partner

from src.models.task import (
    TaskNotFoundError,
    TaskValidationError,
    get_task,
    list_tasks,
    update_task_payout,
)


class TestTaskEventCSVLoader(unittest.TestCase):
    """Test suite for Task Event CSV Ingestion."""

    def setUp(self):
        """Set up an isolated test database and pre-register test partners."""
        self.test_db_path = config.BASE_DIR / "test_task_loader_temp.db"
        if self.test_db_path.exists():
            self.test_db_path.unlink()
        init_db(self.test_db_path)

        # Pre-seed active test partners
        register_partner(
            partner_id="P101",
            partner_name="Ramesh Kumar",
            partner_type="INDIVIDUAL",
            category="DELIVERY",
            onboarding_date="2026-11-01",
            pan="ABCDE1111A",
            db_path=self.test_db_path,
        )
        register_partner(
            partner_id="P102",
            partner_name="Express Deliveries LLP",
            partner_type="FIRM",
            category="DELIVERY",
            onboarding_date="2026-11-01",
            pan="AAACE2222K",
            db_path=self.test_db_path,
        )

    def tearDown(self):
        """Clean up test database."""
        if self.test_db_path.exists():
            self.test_db_path.unlink()

    def test_valid_task_csv_import_all_event_types(self):
        """
        Verify importing all 4 approved event types and storing raw task data.
        Payout fields remain at their initial defaults until later calculation steps.
        """
        csv_data = """task_id,partner_id,task_type,event_type,distance_km,duration_minutes,slot_type,is_slot_surge,is_rain_surge,rating,cancellation_reason,task_timestamp
T001,P101,DELIVERY,TASK_COMPLETED,5.0,20.0,DINNER_PEAK,1,0,4.8,,2026-11-02 20:30:00
T002,P101,DELIVERY,CUSTOMER_CANCELLED_POST_PICKUP,2.0,10.0,REGULAR,0,0,,,2026-11-02 12:00:00
T003,P101,DELIVERY,CUSTOMER_CANCELLED_PRE_PICKUP,0.0,2.0,REGULAR,0,0,,Changed mind,2026-11-02 13:00:00
T004,P101,DELIVERY,PARTNER_CANCELLED,0.0,5.0,REGULAR,0,0,,Flat tire,2026-11-02 14:00:00
"""
        stream = io.StringIO(csv_data)
        summary = import_tasks_from_csv(stream, db_path=self.test_db_path)

        self.assertEqual(summary.total_rows_processed, 4)
        self.assertEqual(summary.successful_imports, 4)
        self.assertEqual(summary.failed_rows, 0)
        self.assertEqual(len(summary.errors), 0)

        # Check T001: Completed 5.0 km, slot surge flag is 1
        t1 = get_task("T001", db_path=self.test_db_path)
        self.assertIsNotNone(t1)
        self.assertEqual(t1.event_type, "TASK_COMPLETED")
        self.assertEqual(t1.distance_km, 5.0)
        self.assertEqual(t1.is_slot_surge, 1)
        self.assertEqual(t1.is_rain_surge, 0)
        self.assertEqual(t1.slot_type, "DINNER_PEAK")       
        self.assertEqual(t1.base_pay_paise, 0)
        self.assertEqual(t1.surge_multiplier, 1.0)
        self.assertEqual(t1.final_task_pay_paise, 0)
        self.assertEqual(t1.rating, 4.8)
        self.assertEqual(t1.task_date, "2026-11-02")
        self.assertEqual(t1.week_identifier, "2026-W45")

        # Check T002: Customer cancelled post pickup
        t2 = get_task("T002", db_path=self.test_db_path)
        self.assertIsNotNone(t2)
        self.assertEqual(t2.event_type, "CUSTOMER_CANCELLED_POST_PICKUP")
        self.assertEqual(t2.base_pay_paise, 0)
        self.assertEqual(t2.surge_multiplier, 1.0)
        self.assertEqual(t2.final_task_pay_paise, 0)

        # Check T003: Customer cancelled pre pickup
        t3 = get_task("T003", db_path=self.test_db_path)
        self.assertEqual(t3.event_type, "CUSTOMER_CANCELLED_PRE_PICKUP")
        self.assertEqual(t3.base_pay_paise, 0)
        self.assertEqual(t3.surge_multiplier, 1.0)
        self.assertEqual(t3.final_task_pay_paise, 0)

        # Check T004: Partner cancelled
        t4 = get_task("T004", db_path=self.test_db_path)
        self.assertEqual(t4.event_type, "PARTNER_CANCELLED")
        self.assertEqual(t4.base_pay_paise, 0)
        self.assertEqual(t4.surge_multiplier, 1.0)
        self.assertEqual(t4.final_task_pay_paise, 0)
        self.assertEqual(t4.cancellation_reason, "Flat tire")

    def test_raw_surge_flags_recorded_accurately(self):
        """Verify that when both slot surge and rain surge flags are present in CSV, they are accurately stored."""
        csv_data = """task_id,partner_id,task_type,event_type,distance_km,duration_minutes,slot_type,is_slot_surge,is_rain_surge,rating,cancellation_reason,task_timestamp
T010,P101,DELIVERY,TASK_COMPLETED,3.0,15.0,DINNER_PEAK,1,1,5.0,,2026-11-02 21:00:00
"""
        stream = io.StringIO(csv_data)
        summary = import_tasks_from_csv(stream, db_path=self.test_db_path)

        self.assertEqual(summary.successful_imports, 1)
        task = get_task("T010", db_path=self.test_db_path)
        self.assertIsNotNone(task)
        self.assertEqual(task.is_slot_surge, 1)
        self.assertEqual(task.is_rain_surge, 1)
        self.assertEqual(task.slot_type, "DINNER_PEAK")
        # Raw ingestion defaults before Step 4/5 calculations:
        self.assertEqual(task.surge_multiplier, 1.0)
        self.assertEqual(task.base_pay_paise, 0)
        self.assertEqual(task.final_task_pay_paise, 0)

    def test_update_task_payout_success_and_validation(self):
        """Verify update_task_payout persists verified payouts and enforces validation."""
        csv_data = """task_id,partner_id,task_type,event_type,distance_km,task_timestamp
T090,P101,DELIVERY,TASK_COMPLETED,5.0,2026-11-02 10:00:00
"""
        import_tasks_from_csv(io.StringIO(csv_data), db_path=self.test_db_path)

        initial_task = get_task("T090", db_path=self.test_db_path)
        self.assertEqual(initial_task.base_pay_paise, 0)
        self.assertEqual(initial_task.surge_multiplier, 1.0)
        self.assertEqual(initial_task.final_task_pay_paise, 0)

        # Update payout with valid values (e.g. calculated in Step 4/5)
        updated = update_task_payout(
            task_id="T090",
            base_pay_paise=3700,
            surge_multiplier=1.3,
            final_task_pay_paise=4800,
            db_path=self.test_db_path,
        )
        self.assertEqual(updated.base_pay_paise, 3700)
        self.assertEqual(updated.surge_multiplier, 1.3)
        self.assertEqual(updated.final_task_pay_paise, 4800)

        # Verify negative base pay is rejected
        with self.assertRaises(TaskValidationError):
            update_task_payout("T090", base_pay_paise=-100, surge_multiplier=1.0, final_task_pay_paise=0, db_path=self.test_db_path)

        # Verify invalid surge multiplier (e.g., 1.8) is rejected
        with self.assertRaises(TaskValidationError):
            update_task_payout("T090", base_pay_paise=2500, surge_multiplier=1.8, final_task_pay_paise=2500, db_path=self.test_db_path)

        # Verify non-existent task ID raises TaskNotFoundError
        with self.assertRaises(TaskNotFoundError):
            update_task_payout("NON_EXISTENT", base_pay_paise=2500, surge_multiplier=1.0, final_task_pay_paise=2500, db_path=self.test_db_path)

    def test_timestamp_ist_conversion_and_week_identifier(self):
        """Verify that UTC timestamps are converted to IST and assigned the correct ISO week."""
        # UTC 2026-11-02 18:30:00Z -> IST is 2026-11-03 00:00:00 (Tuesday, Week 45)
        csv_data = """task_id,partner_id,task_type,event_type,distance_km,task_timestamp
T020,P101,DELIVERY,TASK_COMPLETED,2.0,2026-11-02T18:30:00Z
"""
        stream = io.StringIO(csv_data)
        summary = import_tasks_from_csv(stream, db_path=self.test_db_path)

        self.assertEqual(summary.successful_imports, 1)
        task = get_task("T020", db_path=self.test_db_path)
        self.assertEqual(task.task_date, "2026-11-03")
        self.assertEqual(task.week_identifier, "2026-W45")

    def test_partner_not_found_rejection(self):
        """Verify that a task event for an unregistered partner fails with PARTNER_NOT_FOUND."""
        csv_data = """task_id,partner_id,task_type,event_type,distance_km,task_timestamp
T030,NON_EXISTENT_P999,DELIVERY,TASK_COMPLETED,4.0,2026-11-02 10:00:00
"""
        stream = io.StringIO(csv_data)
        summary = import_tasks_from_csv(stream, db_path=self.test_db_path)

        self.assertEqual(summary.total_rows_processed, 1)
        self.assertEqual(summary.successful_imports, 0)
        self.assertEqual(summary.failed_rows, 1)
        self.assertEqual(summary.partner_not_found_errors, 1)

        err = summary.errors[0]
        self.assertEqual(err.row_number, 2)
        self.assertEqual(err.error_type, "PARTNER_NOT_FOUND")
        self.assertIn("NON_EXISTENT_P999", err.message)

    def test_duplicate_task_id_in_csv_batch(self):
        """Verify duplicate task ID in the same CSV batch is flagged on the correct line."""
        csv_data = """task_id,partner_id,task_type,event_type,distance_km,task_timestamp
T040,P101,DELIVERY,TASK_COMPLETED,3.0,2026-11-02 10:00:00
T040,P101,DELIVERY,TASK_COMPLETED,4.0,2026-11-02 11:00:00
"""
        stream = io.StringIO(csv_data)
        summary = import_tasks_from_csv(stream, db_path=self.test_db_path)

        self.assertEqual(summary.total_rows_processed, 2)
        self.assertEqual(summary.successful_imports, 1)
        self.assertEqual(summary.failed_rows, 1)
        self.assertEqual(summary.duplicate_records, 1)

        err = summary.errors[0]
        self.assertEqual(err.row_number, 3)
        self.assertEqual(err.task_id, "T040")
        self.assertEqual(err.error_type, "DUPLICATE_TASK_ID")

    def test_duplicate_task_id_against_existing_db(self):
        """Verify task ID matching an already persisted task is rejected."""
        # Import T050 first
        csv_initial = """task_id,partner_id,task_type,event_type,distance_km,task_timestamp
T050,P101,DELIVERY,TASK_COMPLETED,3.0,2026-11-02 10:00:00
"""
        import_tasks_from_csv(io.StringIO(csv_initial), db_path=self.test_db_path)

        # Attempt to re-import T050
        csv_repeat = """task_id,partner_id,task_type,event_type,distance_km,task_timestamp
T050,P102,DELIVERY,TASK_COMPLETED,5.0,2026-11-02 11:00:00
"""
        summary = import_tasks_from_csv(io.StringIO(csv_repeat), db_path=self.test_db_path)
        self.assertEqual(summary.successful_imports, 0)
        self.assertEqual(summary.failed_rows, 1)
        self.assertEqual(summary.duplicate_records, 1)
        self.assertEqual(summary.errors[0].error_type, "DUPLICATE_TASK_ID")

    def test_negative_distance_rejected(self):
        """Verify distance < 0 is rejected with VALIDATION_ERROR."""
        csv_data = """task_id,partner_id,task_type,event_type,distance_km,task_timestamp
T060,P101,DELIVERY,TASK_COMPLETED,-5.0,2026-11-02 10:00:00
"""
        stream = io.StringIO(csv_data)
        summary = import_tasks_from_csv(stream, db_path=self.test_db_path)

        self.assertEqual(summary.successful_imports, 0)
        self.assertEqual(summary.failed_rows, 1)
        self.assertEqual(summary.validation_errors, 1)
        self.assertEqual(summary.errors[0].error_type, "VALIDATION_ERROR")
        self.assertIn("non-negative", summary.errors[0].message)

    def test_invalid_rating_rejected(self):
        """Verify rating > 5.0 or < 1.0 is rejected with VALIDATION_ERROR."""
        csv_data = """task_id,partner_id,task_type,event_type,distance_km,rating,task_timestamp
T070,P101,DELIVERY,TASK_COMPLETED,2.0,6.0,2026-11-02 10:00:00
"""
        stream = io.StringIO(csv_data)
        summary = import_tasks_from_csv(stream, db_path=self.test_db_path)

        self.assertEqual(summary.successful_imports, 0)
        self.assertEqual(summary.failed_rows, 1)
        self.assertEqual(summary.validation_errors, 1)
        self.assertIn("rating must be between 1.0 and 5.0", summary.errors[0].message)

    def test_invalid_event_type_rejected(self):
        """Verify unsupported event types are rejected."""
        csv_data = """task_id,partner_id,task_type,event_type,distance_km,task_timestamp
T080,P101,DELIVERY,ORDER_DELIVERED,2.0,2026-11-02 10:00:00
"""
        stream = io.StringIO(csv_data)
        summary = import_tasks_from_csv(stream, db_path=self.test_db_path)

        self.assertEqual(summary.successful_imports, 0)
        self.assertEqual(summary.failed_rows, 1)
        self.assertEqual(summary.validation_errors, 1)
        self.assertIn("Invalid event_type", summary.errors[0].message)

    def test_malformed_csv_missing_and_extra_columns(self):
        """
        Verify that:
        - Row with missing columns fails.
        - Row with extra columns fails.
        - Valid rows continue to import safely.
        """
        csv_data = """task_id,partner_id,task_type,event_type,distance_km,task_timestamp
T101,P101,DELIVERY,TASK_COMPLETED,2.0,2026-11-02 10:00:00
T102,Missing Columns
T103,P101,DELIVERY,TASK_COMPLETED,3.0,2026-11-02 11:00:00
T104,P101,DELIVERY,TASK_COMPLETED,4.0,2026-11-02 12:00:00,EXTRA_VAL_1,EXTRA_VAL_2
T105,P102,DELIVERY,TASK_COMPLETED,5.0,2026-11-02 13:00:00
"""
        stream = io.StringIO(csv_data)
        summary = import_tasks_from_csv(stream, db_path=self.test_db_path)

        self.assertEqual(summary.total_rows_processed, 5)
        self.assertEqual(summary.successful_imports, 3)  # T101, T103, T105
        self.assertEqual(summary.failed_rows, 2)         # T102, T104
        self.assertEqual(summary.validation_errors, 2)

        # Line 3 failed (missing columns)
        self.assertEqual(summary.errors[0].row_number, 3)
        self.assertEqual(summary.errors[0].error_type, "VALIDATION_ERROR")

        # Line 5 failed (extra columns)
        self.assertEqual(summary.errors[1].row_number, 5)
        self.assertEqual(summary.errors[1].error_type, "VALIDATION_ERROR")
        self.assertIn("extra unexpected columns", summary.errors[1].message)

        # Verify persisted valid tasks
        self.assertIsNotNone(get_task("T101", db_path=self.test_db_path))
        self.assertIsNotNone(get_task("T103", db_path=self.test_db_path))
        self.assertIsNotNone(get_task("T105", db_path=self.test_db_path))

        # Verify failed tasks not in DB
        self.assertIsNone(get_task("T102", db_path=self.test_db_path))
        self.assertIsNone(get_task("T104", db_path=self.test_db_path))

    def test_empty_and_missing_header_csv(self):
        """Verify handling of empty CSV or missing required headers."""
        # Empty stream
        summary_empty = import_tasks_from_csv(io.StringIO(""), db_path=self.test_db_path)
        self.assertEqual(summary_empty.total_rows_processed, 0)
        self.assertEqual(summary_empty.errors[0].error_type, "CSV_FORMAT_ERROR")

        # Missing header column (missing distance_km)
        bad_header_csv = """task_id,partner_id,event_type,task_timestamp
T200,P101,TASK_COMPLETED,2026-11-02 10:00:00
"""
        summary_bad_header = import_tasks_from_csv(io.StringIO(bad_header_csv), db_path=self.test_db_path)
        self.assertEqual(summary_bad_header.successful_imports, 0)
        self.assertEqual(summary_bad_header.errors[0].error_type, "CSV_FORMAT_ERROR")
        self.assertIn("missing mandatory columns", summary_bad_header.errors[0].message)

    def test_sample_tasks_csv_file_on_disk(self):
        """Verify importing from the physical data/sample_tasks.csv file."""
        sample_tasks_path = config.BASE_DIR / "data" / "sample_tasks.csv"
        self.assertTrue(sample_tasks_path.exists())

        # Pre-seed sample partners needed by sample_tasks.csv (P1001, P1002)
        register_partner(
            partner_id="P1001",
            partner_name="Sample Partner 1",
            partner_type="INDIVIDUAL",
            category="DELIVERY",
            onboarding_date="2026-11-01",
            pan="ABCDE9001A",
            db_path=self.test_db_path,
        )
        register_partner(
            partner_id="P1002",
            partner_name="Sample Partner 2",
            partner_type="FIRM",
            category="DELIVERY",
            onboarding_date="2026-11-01",
            pan="AAACE9002K",
            db_path=self.test_db_path,
        )

        summary = import_tasks_from_csv(sample_tasks_path, db_path=self.test_db_path)
        self.assertEqual(summary.total_rows_processed, 7)
        self.assertEqual(summary.successful_imports, 7)
        self.assertEqual(summary.failed_rows, 0)

        # Check report format
        report = summary.report()
        self.assertIn("TASK CSV IMPORT SUMMARY REPORT", report)
        self.assertIn("Successfully Imported    : 7", report)

        # Verify task list retrieval helper
        tasks_p1001 = list_tasks(partner_id="P1001", db_path=self.test_db_path)
        self.assertEqual(len(tasks_p1001), 5)


if __name__ == "__main__":
    unittest.main()
