"""
Unit Tests for Step 1: Partner Registration and Validation (PS-060)
Tests:
- Valid partner registration for INDIVIDUAL and FIRM.
- Handling of VALID, INVALID, and MISSING PAN statuses.
- Optional PAN onboarding compatibility.
- Categories: DELIVERY and SERVICE_PROFESSIONAL.
- Bank details and bank verification statuses (VERIFIED, UNVERIFIED, FAILED, PENDING).
- Unverified bank details compatibility.
- Duplicate partner ID rejection (DuplicatePartnerError).
- Duplicate non-null PAN rejection (DuplicatePANError).
- Inconsistent PAN status rejection.
- Invalid partner_type, category, phone, and IFSC rejection.
- Partner retrieval and list helpers.
"""

from datetime import date
from decimal import Decimal
import unittest
from pathlib import Path

import config
from database.db import get_db_connection, init_db
from src.models.partner import (
    DuplicatePANError,
    DuplicatePartnerError,
    Partner,
    PartnerNotFoundError,
    PartnerValidationError,
    get_partner,
    list_partners,
    register_partner,
    validate_partner_data,
)


class TestPartnerRegistration(unittest.TestCase):
    """Unit tests for Module 1 - Partner Registration and Validation."""

    def setUp(self):
        """Set up an isolated SQLite test database for each test case."""
        self.test_db_path = config.BASE_DIR / "test_partner_reg_temp.db"
        if self.test_db_path.exists():
            self.test_db_path.unlink()
        init_db(self.test_db_path)

    def tearDown(self):
        """Clean up the test database after each test."""
        if self.test_db_path.exists():
            self.test_db_path.unlink()

    def test_valid_individual_delivery_registration(self):
        """Verify successful registration of an INDIVIDUAL DELIVERY partner with valid PAN."""
        partner = register_partner(
            partner_id="P101",
            partner_name="Aarav Sharma",
            partner_type="INDIVIDUAL",
            category="DELIVERY",
            onboarding_date="2026-11-01",
            pan="ABCDE1234F",
            phone="9876543210",
            bank_account_number="123456789012",
            ifsc_code="HDFC0001234",
            bank_verification_status="VERIFIED",
            city="Bangalore",
            db_path=self.test_db_path,
        )

        self.assertIsInstance(partner, Partner)
        self.assertEqual(partner.partner_id, "P101")
        self.assertEqual(partner.partner_name, "Aarav Sharma")
        self.assertEqual(partner.partner_type, "INDIVIDUAL")
        self.assertEqual(partner.category, "DELIVERY")
        self.assertEqual(partner.pan, "ABCDE1234F")
        self.assertEqual(partner.pan_status, "VALID")
        self.assertEqual(partner.phone, "9876543210")
        self.assertEqual(partner.bank_account_number, "123456789012")
        self.assertEqual(partner.ifsc_code, "HDFC0001234")
        self.assertEqual(partner.bank_verification_status, "VERIFIED")
        self.assertEqual(partner.bag_deduction_balance_paise, 180000)
        self.assertEqual(partner.bag_deduction_balance_rupees, Decimal("1800.00"))

        # Verify persisted row in SQLite
        persisted = get_partner("P101", db_path=self.test_db_path)
        self.assertIsNotNone(persisted)
        self.assertEqual(persisted.partner_name, "Aarav Sharma")

    def test_valid_firm_service_professional_registration(self):
        """Verify successful registration of a FIRM SERVICE_PROFESSIONAL partner."""
        partner = register_partner(
            partner_id="F201",
            partner_name="Urban Clean Experts LLP",
            partner_type="FIRM",
            category="SERVICE_PROFESSIONAL",
            onboarding_date=date(2026, 11, 2),
            pan="AAACU1234K",
            bank_verification_status="PENDING",
            city="Hyderabad",
            db_path=self.test_db_path,
        )

        self.assertEqual(partner.partner_id, "F201")
        self.assertEqual(partner.partner_type, "FIRM")
        self.assertEqual(partner.category, "SERVICE_PROFESSIONAL")
        self.assertEqual(partner.pan_status, "VALID")
        self.assertEqual(partner.city, "Hyderabad")

    def test_missing_pan_registration(self):
        """Verify partners can register without a PAN (pan=None), resulting in pan_status='MISSING'."""
        partner = register_partner(
            partner_id="P102",
            partner_name="Sanjay Verma",
            partner_type="INDIVIDUAL",
            category="DELIVERY",
            onboarding_date="2026-11-01",
            pan=None,
            db_path=self.test_db_path,
        )

        self.assertIsNone(partner.pan)
        self.assertEqual(partner.pan_status, "MISSING")

    def test_multiple_partners_with_missing_pan_allowed(self):
        """Verify multiple partners can register with missing PAN without unique constraint collision."""
        p1 = register_partner(
            partner_id="P103",
            partner_name="Partner One",
            partner_type="INDIVIDUAL",
            category="DELIVERY",
            onboarding_date="2026-11-01",
            pan=None,
            db_path=self.test_db_path,
        )
        p2 = register_partner(
            partner_id="P104",
            partner_name="Partner Two",
            partner_type="INDIVIDUAL",
            category="DELIVERY",
            onboarding_date="2026-11-02",
            pan=None,
            db_path=self.test_db_path,
        )

        self.assertIsNone(p1.pan)
        self.assertIsNone(p2.pan)
        self.assertEqual(p1.pan_status, "MISSING")
        self.assertEqual(p2.pan_status, "MISSING")

    def test_invalid_pan_format_registration(self):
        """Verify registration with malformed PAN succeeds but sets pan_status='INVALID'."""
        partner = register_partner(
            partner_id="P105",
            partner_name="Deepak Joshi",
            partner_type="INDIVIDUAL",
            category="DELIVERY",
            onboarding_date="2026-11-01",
            pan="INVALID_PAN_123",
            db_path=self.test_db_path,
        )

        self.assertEqual(partner.pan, "INVALID_PAN_123")
        self.assertEqual(partner.pan_status, "INVALID")

    def test_duplicate_partner_id_raises_error(self):
        """Verify attempting to register a duplicate partner ID raises DuplicatePartnerError."""
        register_partner(
            partner_id="P106",
            partner_name="First Registration",
            partner_type="INDIVIDUAL",
            category="DELIVERY",
            onboarding_date="2026-11-01",
            db_path=self.test_db_path,
        )

        with self.assertRaises(DuplicatePartnerError) as ctx:
            register_partner(
                partner_id="P106",
                partner_name="Duplicate Attempt",
                partner_type="INDIVIDUAL",
                category="DELIVERY",
                onboarding_date="2026-11-02",
                db_path=self.test_db_path,
            )
        self.assertIn("already registered", str(ctx.exception))

    def test_duplicate_non_null_pan_raises_error(self):
        """Verify attempting to register an existing non-null PAN raises DuplicatePANError."""
        register_partner(
            partner_id="P107",
            partner_name="Original PAN Holder",
            partner_type="INDIVIDUAL",
            category="DELIVERY",
            onboarding_date="2026-11-01",
            pan="ABCDE1234F",
            db_path=self.test_db_path,
        )

        with self.assertRaises(DuplicatePANError) as ctx:
            register_partner(
                partner_id="P108",
                partner_name="Duplicate PAN Attempt",
                partner_type="INDIVIDUAL",
                category="DELIVERY",
                onboarding_date="2026-11-02",
                pan="ABCDE1234F",
                db_path=self.test_db_path,
            )
        self.assertIn("already registered", str(ctx.exception))

    def test_invalid_partner_type_rejected(self):
        """Verify partner_type outside ('INDIVIDUAL', 'FIRM') is rejected with PartnerValidationError."""
        with self.assertRaises(PartnerValidationError) as ctx:
            register_partner(
                partner_id="P109",
                partner_name="Invalid Type Partner",
                partner_type="ENTERPRISE",
                category="DELIVERY",
                onboarding_date="2026-11-01",
                db_path=self.test_db_path,
            )
        self.assertIn("Invalid partner_type", str(ctx.exception))

    def test_invalid_category_rejected(self):
        """Verify category outside ('DELIVERY', 'SERVICE_PROFESSIONAL') is rejected."""
        with self.assertRaises(PartnerValidationError) as ctx:
            register_partner(
                partner_id="P110",
                partner_name="Invalid Category Partner",
                partner_type="INDIVIDUAL",
                category="RIDESHARE",
                onboarding_date="2026-11-01",
                db_path=self.test_db_path,
            )
        self.assertIn("Invalid category", str(ctx.exception))

    def test_bank_verification_statuses(self):
        """Verify allowed bank verification statuses and rejection of invalid ones."""
        for status in ("VERIFIED", "UNVERIFIED", "FAILED", "PENDING"):
            p = register_partner(
                partner_id=f"P_{status}",
                partner_name=f"Partner {status}",
                partner_type="INDIVIDUAL",
                category="DELIVERY",
                onboarding_date="2026-11-01",
                bank_verification_status=status,
                db_path=self.test_db_path,
            )
            self.assertEqual(p.bank_verification_status, status)

        with self.assertRaises(PartnerValidationError) as ctx:
            register_partner(
                partner_id="P_INVALID_BANK",
                partner_name="Invalid Bank Status Partner",
                partner_type="INDIVIDUAL",
                category="DELIVERY",
                onboarding_date="2026-11-01",
                bank_verification_status="AUTHORIZED",
                db_path=self.test_db_path,
            )
        self.assertIn("Invalid bank_verification_status", str(ctx.exception))

    def test_unverified_missing_bank_details_compatible(self):
        """Verify partners can be registered with unverified or missing bank details."""
        partner = register_partner(
            partner_id="P111",
            partner_name="Kiran Patel",
            partner_type="INDIVIDUAL",
            category="DELIVERY",
            onboarding_date="2026-11-01",
            bank_account_number=None,
            ifsc_code=None,
            bank_verification_status="PENDING",
            db_path=self.test_db_path,
        )
        self.assertIsNone(partner.bank_account_number)
        self.assertIsNone(partner.ifsc_code)
        self.assertEqual(partner.bank_verification_status, "PENDING")

    def test_inconsistent_pan_status_rejected(self):
        """Verify inconsistent combinations of PAN and pan_status are rejected."""
        # 1. pan_status='MISSING' but PAN is supplied
        with self.assertRaises(PartnerValidationError):
            validate_partner_data(
                partner_id="P112",
                partner_name="Inconsistent 1",
                partner_type="INDIVIDUAL",
                category="DELIVERY",
                onboarding_date="2026-11-01",
                pan="ABCDE1234F",
                pan_status="MISSING",
            )

        # 2. pan_status='VALID' but PAN is None
        with self.assertRaises(PartnerValidationError):
            validate_partner_data(
                partner_id="P113",
                partner_name="Inconsistent 2",
                partner_type="INDIVIDUAL",
                category="DELIVERY",
                onboarding_date="2026-11-01",
                pan=None,
                pan_status="VALID",
            )

        # 3. pan_status='VALID' but PAN format is invalid
        with self.assertRaises(PartnerValidationError):
            validate_partner_data(
                partner_id="P114",
                partner_name="Inconsistent 3",
                partner_type="INDIVIDUAL",
                category="DELIVERY",
                onboarding_date="2026-11-01",
                pan="BAD_PAN",
                pan_status="VALID",
            )

    def test_phone_and_ifsc_format_validation(self):
        """Verify invalid phone and IFSC formats are caught by validation."""
        # Invalid phone: not 10 digits
        with self.assertRaises(PartnerValidationError) as ctx:
            validate_partner_data(
                partner_id="P115",
                partner_name="Bad Phone",
                partner_type="INDIVIDUAL",
                category="DELIVERY",
                onboarding_date="2026-11-01",
                phone="12345",
            )
        self.assertIn("Invalid phone number", str(ctx.exception))

        # Invalid IFSC: wrong format
        with self.assertRaises(PartnerValidationError) as ctx:
            validate_partner_data(
                partner_id="P116",
                partner_name="Bad IFSC",
                partner_type="INDIVIDUAL",
                category="DELIVERY",
                onboarding_date="2026-11-01",
                ifsc_code="NOT_AN_IFSC",
            )
        self.assertIn("Invalid IFSC code", str(ctx.exception))

    def test_rating_and_bag_balance_validation(self):
        """Verify rating bounds and bag deduction balance non-negativity."""
        with self.assertRaises(PartnerValidationError):
            validate_partner_data(
                partner_id="P117",
                partner_name="Bad Rating",
                partner_type="INDIVIDUAL",
                category="DELIVERY",
                onboarding_date="2026-11-01",
                rating=5.5,
            )

        with self.assertRaises(PartnerValidationError):
            validate_partner_data(
                partner_id="P118",
                partner_name="Negative Bag Balance",
                partner_type="INDIVIDUAL",
                category="DELIVERY",
                onboarding_date="2026-11-01",
                bag_deduction_balance_paise=-1000,
            )

    def test_list_partners_helper(self):
        """Verify list_partners retrieves all registered partners."""
        register_partner(
            partner_id="P201",
            partner_name="Partner Alpha",
            partner_type="INDIVIDUAL",
            category="DELIVERY",
            onboarding_date="2026-11-01",
            db_path=self.test_db_path,
        )
        register_partner(
            partner_id="P202",
            partner_name="Partner Beta",
            partner_type="FIRM",
            category="SERVICE_PROFESSIONAL",
            onboarding_date="2026-11-02",
            db_path=self.test_db_path,
        )

        all_partners = list_partners(db_path=self.test_db_path)
        self.assertEqual(len(all_partners), 2)
        ids = [p.partner_id for p in all_partners]
        self.assertIn("P201", ids)
        self.assertIn("P202", ids)


if __name__ == "__main__":
    unittest.main()
