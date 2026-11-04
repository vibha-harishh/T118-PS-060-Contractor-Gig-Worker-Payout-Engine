
import unittest
from decimal import Decimal

from src.settlement.tds import calculate_tds


class TestTDS(unittest.TestCase):

    def test_194c_individual_rate(self):
        result = calculate_tds(
            "INDIVIDUAL", "DELIVERY", "VALID",
            4_000_000, 0
        )

        self.assertEqual(result["section"], "194-C")
        self.assertEqual(result["tds_paise"], 40_000)

    def test_194c_firm_rate(self):
        result = calculate_tds(
            "FIRM", "DELIVERY", "VALID",
            4_000_000, 0
        )

        self.assertEqual(result["tds_paise"], 80_000)

    def test_194j_rate(self):
        result = calculate_tds(
            "INDIVIDUAL", "SERVICE_PROFESSIONAL", "VALID",
            4_000_000, 0
        )

        self.assertEqual(result["section"], "194-J")
        self.assertEqual(result["tds_paise"], 400_000)

    def test_194o_rate(self):
        result = calculate_tds(
            "INDIVIDUAL", "DELIVERY", "VALID",
            50_000_100, 0,
            marketplace_mode=True
        )

        self.assertEqual(result["section"], "194-O")
        self.assertEqual(result["tds_paise"], 500_001)
    def test_194c_exactly_30000_not_taxed(self):
        result = calculate_tds(
            "INDIVIDUAL", "DELIVERY", "VALID",
            3_000_000, 0
        )

        self.assertFalse(result["taxable"])
        self.assertEqual(result["tds_paise"], 0)

    def test_194c_30001_is_taxed(self):
        result = calculate_tds(
            "INDIVIDUAL", "DELIVERY", "VALID",
            3_000_100, 0
        )

        self.assertTrue(result["taxable"])
        self.assertEqual(result["tds_paise"], 30_001)

    def test_194c_cumulative_threshold_crossing(self):
        result = calculate_tds(
            "INDIVIDUAL", "DELIVERY", "VALID",
            50_000, 9_990_000
        )

        self.assertTrue(result["threshold_crossed"])
        self.assertEqual(result["tds_paise"], 500)

    def test_invalid_pan_uses_20_percent(self):
        result = calculate_tds(
            "INDIVIDUAL", "DELIVERY", "INVALID",
            4_000_000, 0
        )

        self.assertEqual(
            result["applicable_rate"], Decimal("0.20")
        )
        self.assertEqual(result["tds_paise"], 800_000)

    def test_missing_pan_uses_20_percent(self):
        result = calculate_tds(
            "FIRM", "DELIVERY", "MISSING",
            4_000_000, 0
        )

        self.assertEqual(result["tds_paise"], 800_000)

    def test_194j_threshold_crossing(self):
        result = calculate_tds(
            "INDIVIDUAL", "SERVICE_PROFESSIONAL", "VALID",
            500, 2_999_900
        )

        self.assertTrue(result["taxable"])
        self.assertEqual(result["tds_paise"], 50)

    def test_194o_individual_threshold_not_crossed(self):
        result = calculate_tds(
            "INDIVIDUAL", "DELIVERY", "VALID",
            1_000_000, 49_000_000,
            marketplace_mode=True
        )

        self.assertFalse(result["taxable"])
        self.assertEqual(result["tds_paise"], 0)

    def test_194o_firm_no_individual_threshold(self):
        result = calculate_tds(
            "FIRM", "DELIVERY", "VALID",
            1_000_000, 0,
            marketplace_mode=True
        )

        self.assertTrue(result["taxable"])
        self.assertEqual(result["tds_paise"], 10_000)

    def test_invalid_amount(self):
        with self.assertRaises(ValueError):
            calculate_tds(
                "INDIVIDUAL", "DELIVERY", "VALID",
                -100, 0
            )

    def test_invalid_partner_type(self):
        with self.assertRaises(ValueError):
            calculate_tds(
                "OTHER", "DELIVERY", "VALID",
                4_000_000, 0
            )


if __name__ == "__main__":
    unittest.main()
