"""
Unit Tests for Step 2: Partner CSV File Processing (PS-060)
Tests:
- Valid CSV import with multiple records.
- Missing PAN handling (pan=None, pan_status='MISSING').
- Invalid PAN format handling (pan string preserved, pan_status='INVALID').
- Duplicate partner ID rejection (within CSV batch and against DB).
- Duplicate non-null PAN rejection (within CSV batch and against DB).
- Missing/unverified bank details support without crashing.
- Invalid partner_type or category rejection.
- Empty CSV file handling.
- Malformed CSV (missing mandatory columns in header).
- Mixed valid and invalid rows batch processing (valid rows succeed, invalid rows logged).
- Detailed summary statistics and row-level diagnostic reports.
"""

import io
import unittest
from pathlib import Path

import config
from database.db import get_db_connection, init_db
from src.ingestion.partner_loader import (
    PartnerImportSummary,
    import_partners_from_csv,
)
from src.models.partner import get_partner, list_partners, register_partner


class TestPartnerCSVLoader(unittest.TestCase):
    """Test suite for Partner CSV import engine."""

    def setUp(self):
        """Set up an isolated SQLite test database for each test case."""
        self.test_db_path = config.BASE_DIR / "test_partner_loader_temp.db"
        if self.test_db_path.exists():
            self.test_db_path.unlink()
        init_db(self.test_db_path)

    def tearDown(self):
        """Clean up the test database."""
        if self.test_db_path.exists():
            self.test_db_path.unlink()

    def test_valid_csv_import(self):
        """Verify successful batch import of valid partners from CSV."""
        csv_data = """partner_id,partner_name,partner_type,category,onboarding_date,pan,phone,bank_account_number,ifsc_code,bank_verification_status,city
P501,Aditi Rao,INDIVIDUAL,DELIVERY,2026-11-01,ABCDE1111A,9876543210,12345678901,HDFC0001234,VERIFIED,Bangalore
P502,Quick Movers LLP,FIRM,DELIVERY,2026-11-01,AAACQ2222B,9876543211,12345678902,SBIN0001234,VERIFIED,Delhi
P503,Vikramaditya,INDIVIDUAL,SERVICE_PROFESSIONAL,2026-11-02,ABCDE3333C,9876543212,12345678903,ICIC0001234,PENDING,Mumbai
"""
        stream = io.StringIO(csv_data)
        summary = import_partners_from_csv(stream, db_path=self.test_db_path)

        self.assertEqual(summary.total_rows_processed, 3)
        self.assertEqual(summary.successful_imports, 3)
        self.assertEqual(summary.failed_rows, 0)
        self.assertEqual(summary.duplicate_records, 0)
        self.assertEqual(summary.validation_errors, 0)
        self.assertEqual(len(summary.errors), 0)

        # Verify persisted in database
        partners = list_partners(db_path=self.test_db_path)
        self.assertEqual(len(partners), 3)
        p501 = get_partner("P501", db_path=self.test_db_path)
        self.assertIsNotNone(p501)
        self.assertEqual(p501.pan_status, "VALID")
        self.assertEqual(p501.partner_type, "INDIVIDUAL")

    def test_missing_pan_handling(self):
        """Verify partners without PAN in CSV are imported with pan_status='MISSING' and pan=None."""
        csv_data = """partner_id,partner_name,partner_type,category,onboarding_date,pan
P601,Sunil Kumar,INDIVIDUAL,DELIVERY,2026-11-01,
P602,Geeta Sharma,INDIVIDUAL,DELIVERY,2026-11-02,
"""
        stream = io.StringIO(csv_data)
        summary = import_partners_from_csv(stream, db_path=self.test_db_path)

        self.assertEqual(summary.total_rows_processed, 2)
        self.assertEqual(summary.successful_imports, 2)
        self.assertEqual(summary.failed_rows, 0)

        p1 = get_partner("P601", db_path=self.test_db_path)
        p2 = get_partner("P602", db_path=self.test_db_path)
        self.assertIsNone(p1.pan)
        self.assertEqual(p1.pan_status, "MISSING")
        self.assertIsNone(p2.pan)
        self.assertEqual(p2.pan_status, "MISSING")

    def test_invalid_pan_format_handling(self):
        """Verify partners with malformed PAN are imported with pan_status='INVALID' without crashing."""
        csv_data = """partner_id,partner_name,partner_type,category,onboarding_date,pan
P701,Rohan Mehta,INDIVIDUAL,DELIVERY,2026-11-01,NOT_A_VALID_PAN_123
"""
        stream = io.StringIO(csv_data)
        summary = import_partners_from_csv(stream, db_path=self.test_db_path)

        self.assertEqual(summary.successful_imports, 1)
        partner = get_partner("P701", db_path=self.test_db_path)
        self.assertEqual(partner.pan, "NOT_A_VALID_PAN_123")
        self.assertEqual(partner.pan_status, "INVALID")

    def test_duplicate_partner_id_in_csv_batch(self):
        """Verify duplicate partner ID within the same CSV batch is flagged."""
        csv_data = """partner_id,partner_name,partner_type,category,onboarding_date
P801,First Entry,INDIVIDUAL,DELIVERY,2026-11-01
P801,Duplicate Entry,INDIVIDUAL,DELIVERY,2026-11-02
"""
        stream = io.StringIO(csv_data)
        summary = import_partners_from_csv(stream, db_path=self.test_db_path)

        self.assertEqual(summary.total_rows_processed, 2)
        self.assertEqual(summary.successful_imports, 1)
        self.assertEqual(summary.failed_rows, 1)
        self.assertEqual(summary.duplicate_records, 1)

        err = summary.errors[0]
        self.assertEqual(err.row_number, 3)  # Line 3 of CSV
        self.assertEqual(err.partner_id, "P801")
        self.assertEqual(err.error_type, "DUPLICATE_PARTNER_ID")

    def test_duplicate_partner_id_against_existing_db(self):
        """Verify CSV partner ID matching an already existing database partner is flagged."""
        # Pre-seed DB
        register_partner(
            partner_id="P802",
            partner_name="Pre-existing Partner",
            partner_type="INDIVIDUAL",
            category="DELIVERY",
            onboarding_date="2026-11-01",
            db_path=self.test_db_path,
        )

        csv_data = """partner_id,partner_name,partner_type,category,onboarding_date
P802,Attempted Duplicate,INDIVIDUAL,DELIVERY,2026-11-02
"""
        stream = io.StringIO(csv_data)
        summary = import_partners_from_csv(stream, db_path=self.test_db_path)

        self.assertEqual(summary.total_rows_processed, 1)
        self.assertEqual(summary.successful_imports, 0)
        self.assertEqual(summary.failed_rows, 1)
        self.assertEqual(summary.duplicate_records, 1)
        self.assertEqual(summary.errors[0].error_type, "DUPLICATE_PARTNER_ID")

    def test_duplicate_pan_in_csv_batch(self):
        """Verify duplicate non-null PAN within the same CSV batch is flagged."""
        csv_data = """partner_id,partner_name,partner_type,category,onboarding_date,pan
P901,User One,INDIVIDUAL,DELIVERY,2026-11-01,ABCDE9999Z
P902,User Two,INDIVIDUAL,DELIVERY,2026-11-02,ABCDE9999Z
"""
        stream = io.StringIO(csv_data)
        summary = import_partners_from_csv(stream, db_path=self.test_db_path)

        self.assertEqual(summary.total_rows_processed, 2)
        self.assertEqual(summary.successful_imports, 1)
        self.assertEqual(summary.failed_rows, 1)
        self.assertEqual(summary.duplicate_records, 1)
        self.assertEqual(summary.errors[0].error_type, "DUPLICATE_PAN")
        self.assertEqual(summary.errors[0].partner_id, "P902")

    def test_missing_bank_details_compatible(self):
        """Verify partner rows with blank bank details import successfully with PENDING status."""
        csv_data = """partner_id,partner_name,partner_type,category,onboarding_date,bank_account_number,ifsc_code
P950,No Bank Partner,INDIVIDUAL,DELIVERY,2026-11-01,,
"""
        stream = io.StringIO(csv_data)
        summary = import_partners_from_csv(stream, db_path=self.test_db_path)

        self.assertEqual(summary.successful_imports, 1)
        partner = get_partner("P950", db_path=self.test_db_path)
        self.assertIsNone(partner.bank_account_number)
        self.assertIsNone(partner.ifsc_code)
        self.assertEqual(partner.bank_verification_status, "PENDING")

    def test_invalid_category_or_partner_type_rejected(self):
        """Verify invalid category or partner_type in CSV is flagged with row number."""
        csv_data = """partner_id,partner_name,partner_type,category,onboarding_date
P960,Bad Type Partner,CORPORATION,DELIVERY,2026-11-01
P961,Bad Category Partner,INDIVIDUAL,CAR_RENTAL,2026-11-01
"""
        stream = io.StringIO(csv_data)
        summary = import_partners_from_csv(stream, db_path=self.test_db_path)

        self.assertEqual(summary.total_rows_processed, 2)
        self.assertEqual(summary.successful_imports, 0)
        self.assertEqual(summary.failed_rows, 2)
        self.assertEqual(summary.validation_errors, 2)

        self.assertEqual(summary.errors[0].row_number, 2)
        self.assertIn("Invalid partner_type", summary.errors[0].message)

        self.assertEqual(summary.errors[1].row_number, 3)
        self.assertIn("Invalid category", summary.errors[1].message)

    def test_empty_csv_handling(self):
        """Verify importing an empty CSV file returns 0 rows and logs CSV_FORMAT_ERROR."""
        stream = io.StringIO("")
        summary = import_partners_from_csv(stream, db_path=self.test_db_path)

        self.assertEqual(summary.total_rows_processed, 0)
        self.assertEqual(summary.successful_imports, 0)
        self.assertEqual(len(summary.errors), 1)
        self.assertEqual(summary.errors[0].error_type, "CSV_FORMAT_ERROR")

    def test_malformed_csv_missing_header_columns(self):
        """Verify CSV missing required header columns is rejected gracefully."""
        csv_data = """partner_id,partner_name,city
P970,Only Three Columns,Bangalore
"""
        stream = io.StringIO(csv_data)
        summary = import_partners_from_csv(stream, db_path=self.test_db_path)

        self.assertEqual(summary.total_rows_processed, 0)
        self.assertEqual(summary.successful_imports, 0)
        self.assertEqual(len(summary.errors), 1)
        self.assertEqual(summary.errors[0].error_type, "CSV_FORMAT_ERROR")
        self.assertIn("missing mandatory columns", summary.errors[0].message)

    def test_mixed_valid_and_invalid_rows_continues_import(self):
        """Verify that invalid rows do not stop valid rows from being committed."""
        csv_data = """partner_id,partner_name,partner_type,category,onboarding_date,pan
P981,Valid Partner 1,INDIVIDUAL,DELIVERY,2026-11-01,ABCDE1111A
P982,Invalid Category Partner,INDIVIDUAL,WRONG_CAT,2026-11-01,ABCDE2222B
P983,Valid Partner 2,FIRM,SERVICE_PROFESSIONAL,2026-11-02,ABCDE3333C
P984,Duplicate Partner 1,INDIVIDUAL,DELIVERY,2026-11-02,ABCDE1111A
P985,Valid Partner 3,INDIVIDUAL,DELIVERY,2026-11-03,
"""
        stream = io.StringIO(csv_data)
        summary = import_partners_from_csv(stream, db_path=self.test_db_path)

        self.assertEqual(summary.total_rows_processed, 5)
        self.assertEqual(summary.successful_imports, 3)  # P981, P983, P985
        self.assertEqual(summary.failed_rows, 2)         # P982 (invalid category), P984 (duplicate PAN)
        self.assertEqual(summary.validation_errors, 1)
        self.assertEqual(summary.duplicate_records, 1)

        # Confirm all 3 valid partners exist in the database
        self.assertIsNotNone(get_partner("P981", db_path=self.test_db_path))
        self.assertIsNotNone(get_partner("P983", db_path=self.test_db_path))
        self.assertIsNotNone(get_partner("P985", db_path=self.test_db_path))

        # Confirm invalid partners were NOT inserted
        self.assertIsNone(get_partner("P982", db_path=self.test_db_path))
        self.assertIsNone(get_partner("P984", db_path=self.test_db_path))

    def test_sample_csv_file_on_disk_import(self):
        """Verify importing from the actual data/sample_partners.csv on disk."""
        sample_file_path = config.BASE_DIR / "data" / "sample_partners.csv"
        self.assertTrue(sample_file_path.exists())

        summary = import_partners_from_csv(sample_file_path, db_path=self.test_db_path)
        self.assertEqual(summary.total_rows_processed, 5)
        self.assertEqual(summary.successful_imports, 5)
        self.assertEqual(summary.failed_rows, 0)

        # Check human-readable report formatting
        report_text = summary.report()
        self.assertIn("PARTNER CSV IMPORT SUMMARY REPORT", report_text)
        self.assertIn("Successfully Imported: 5", report_text)

    def test_duplicate_pan_against_existing_db(self):
        """
        Verify that a CSV row containing a PAN already registered in the DB
        is rejected as DUPLICATE_PAN with the correct CSV row number, while other rows import.
        """
        # Step 1: Pre-register a partner with a PAN directly in the database
        register_partner(
            partner_id="P_EXISTING",
            partner_name="Existing Partner",
            partner_type="INDIVIDUAL",
            category="DELIVERY",
            onboarding_date="2026-11-01",
            pan="ABCDE5555M",
            db_path=self.test_db_path,
        )

        # Step 2: Prepare CSV containing:
        # Line 2: Valid partner with unique PAN
        # Line 3: Partner with duplicate PAN matching P_EXISTING
        # Line 4: Another valid partner with unique PAN
        csv_data = """partner_id,partner_name,partner_type,category,onboarding_date,pan
P910,Valid Fresh Partner,INDIVIDUAL,DELIVERY,2026-11-02,ABCDE6666N
P911,Colliding PAN Partner,INDIVIDUAL,DELIVERY,2026-11-02,ABCDE5555M
P912,Another Fresh Partner,INDIVIDUAL,DELIVERY,2026-11-02,ABCDE7777P
"""
        stream = io.StringIO(csv_data)
        summary = import_partners_from_csv(stream, db_path=self.test_db_path)

        # Verify summary statistics
        self.assertEqual(summary.total_rows_processed, 3)
        self.assertEqual(summary.successful_imports, 2)
        self.assertEqual(summary.failed_rows, 1)
        self.assertEqual(summary.duplicate_records, 1)
        self.assertEqual(len(summary.errors), 1)

        # Verify failure diagnostics
        error = summary.errors[0]
        self.assertEqual(error.row_number, 3)  # Exact line number in CSV
        self.assertEqual(error.partner_id, "P911")
        self.assertEqual(error.error_type, "DUPLICATE_PAN")
        self.assertIn("ABCDE5555M", error.message)
        self.assertIn("already registered", error.message)

        # Confirm non-colliding partners imported successfully
        self.assertIsNotNone(get_partner("P910", db_path=self.test_db_path))
        self.assertIsNotNone(get_partner("P912", db_path=self.test_db_path))
        # Confirm colliding partner was NOT registered
        self.assertIsNone(get_partner("P911", db_path=self.test_db_path))

    def test_malformed_csv_row_missing_and_extra_columns(self):
        """
        Verify that:
        - A row with missing columns fails with VALIDATION_ERROR and correct row number.
        - A row with extra columns fails with VALIDATION_ERROR and correct row number.
        - Other valid rows in the same CSV continue to import successfully.
        """
        # Line 1: Header (5 columns)
        # Line 2: Valid partner
        # Line 3: Malformed row with missing columns (only 2 columns provided)
        # Line 4: Valid partner
        # Line 5: Malformed row with extra unexpected columns (7 columns provided)
        # Line 6: Valid partner
        csv_data = """partner_id,partner_name,partner_type,category,onboarding_date
P1001,Valid Alpha,INDIVIDUAL,DELIVERY,2026-11-01
P1002,Missing Columns
P1003,Valid Beta,FIRM,SERVICE_PROFESSIONAL,2026-11-02
P1004,Extra Columns,INDIVIDUAL,DELIVERY,2026-11-02,EXTRA_1,EXTRA_2
P1005,Valid Gamma,INDIVIDUAL,DELIVERY,2026-11-03
"""
        stream = io.StringIO(csv_data)
        summary = import_partners_from_csv(stream, db_path=self.test_db_path)

        # Total 5 rows processed
        self.assertEqual(summary.total_rows_processed, 5)
        # 3 valid rows imported
        self.assertEqual(summary.successful_imports, 3)
        # 2 malformed rows failed
        self.assertEqual(summary.failed_rows, 2)
        self.assertEqual(summary.validation_errors, 2)
        self.assertEqual(len(summary.errors), 2)

        # Diagnostic check for Line 3 (Missing columns)
        err_missing = summary.errors[0]
        self.assertEqual(err_missing.row_number, 3)
        self.assertEqual(err_missing.partner_id, "P1002")
        self.assertEqual(err_missing.error_type, "VALIDATION_ERROR")

        # Diagnostic check for Line 5 (Extra columns)
        err_extra = summary.errors[1]
        self.assertEqual(err_extra.row_number, 5)
        self.assertEqual(err_extra.partner_id, "P1004")
        self.assertEqual(err_extra.error_type, "VALIDATION_ERROR")
        self.assertIn("extra unexpected columns", err_extra.message)

        # Confirm all 3 valid partners are safely persisted
        self.assertIsNotNone(get_partner("P1001", db_path=self.test_db_path))
        self.assertIsNotNone(get_partner("P1003", db_path=self.test_db_path))
        self.assertIsNotNone(get_partner("P1005", db_path=self.test_db_path))

        # Confirm malformed rows were NOT registered
        self.assertIsNone(get_partner("P1002", db_path=self.test_db_path))
        self.assertIsNone(get_partner("P1004", db_path=self.test_db_path))


if __name__ == "__main__":
    unittest.main()

