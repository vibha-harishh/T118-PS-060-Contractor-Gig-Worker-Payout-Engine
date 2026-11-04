
"""
TDS Calculation Module
Project: T118-PS-060
Member 2: TDS and Settlement

All monetary amounts are INTEGER PAISE.
Thresholds and rates follow the supplied PS-060 assignment rules.
"""

from decimal import Decimal, ROUND_HALF_UP


# All thresholds are stored in paise.
SECTION_194C_SINGLE_PAYMENT_THRESHOLD = 3_000_000       # ₹30,000
SECTION_194C_ANNUAL_THRESHOLD = 10_000_000              # ₹1,00,000
SECTION_194J_ANNUAL_THRESHOLD = 3_000_000               # ₹30,000
SECTION_194O_ANNUAL_THRESHOLD = 50_000_000              # ₹5,00,000

PAN_DEFAULT_RATE = Decimal("0.20")


def _validate_amount(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer in paise.")

    if value < 0:
        raise ValueError(f"{field_name} cannot be negative.")


def calculate_tds(
    partner_type: str,
    category: str,
    pan_status: str,
    payment_paise: int,
    cumulative_fy_before_paise: int,
    marketplace_mode: bool = False,
) -> dict:
    """
    Calculate TDS for one weekly payment.

    Args:
        partner_type:
            INDIVIDUAL or FIRM

        category:
            DELIVERY or SERVICE_PROFESSIONAL

        pan_status:
            VALID, INVALID or MISSING

        payment_paise:
            Current payment amount, including applicable adjustments,
            before TDS.

        cumulative_fy_before_paise:
            Previous financial-year payments before this payment.

        marketplace_mode:
            True selects Section 194-O instead of 194-C / 194-J.

    Returns:
        Dictionary containing section, rate, threshold status,
        taxable amount and TDS amount.
    """

    if partner_type not in ("INDIVIDUAL", "FIRM"):
        raise ValueError("Invalid partner type.")

    if category not in ("DELIVERY", "SERVICE_PROFESSIONAL"):
        raise ValueError("Invalid partner category.")

    if pan_status not in ("VALID", "INVALID", "MISSING"):
        raise ValueError("Invalid PAN status.")

    if not isinstance(marketplace_mode, bool):
        raise TypeError("marketplace_mode must be True or False.")

    _validate_amount(payment_paise, "payment_paise")
    _validate_amount(
        cumulative_fy_before_paise,
        "cumulative_fy_before_paise"
    )

    cumulative_after_paise = (
        cumulative_fy_before_paise + payment_paise
    )

    # --------------------------------------------------
    # Select applicable TDS section
    # --------------------------------------------------

    if marketplace_mode:
        section = "194-O"
        normal_rate = Decimal("0.01")

        if partner_type == "INDIVIDUAL":
            threshold_crossed = (
                cumulative_after_paise
                > SECTION_194O_ANNUAL_THRESHOLD
            )
        else:
            # Assignment specifies the ₹5 lakh threshold
            # for individuals only.
            threshold_crossed = True

    elif category == "DELIVERY":
        section = "194-C"

        normal_rate = (
            Decimal("0.01")
            if partner_type == "INDIVIDUAL"
            else Decimal("0.02")
        )

        single_payment_exceeded = (
            payment_paise
            > SECTION_194C_SINGLE_PAYMENT_THRESHOLD
        )

        annual_threshold_exceeded = (
            cumulative_after_paise
            > SECTION_194C_ANNUAL_THRESHOLD
        )

        threshold_crossed = (
            single_payment_exceeded
            or annual_threshold_exceeded
        )

    else:
        section = "194-J"
        normal_rate = Decimal("0.10")

        threshold_crossed = (
            cumulative_after_paise
            > SECTION_194J_ANNUAL_THRESHOLD
        )

    # --------------------------------------------------
    # Apply PAN rate
    # --------------------------------------------------

    if pan_status in ("INVALID", "MISSING"):
        applicable_rate = PAN_DEFAULT_RATE
    else:
        applicable_rate = normal_rate

    # --------------------------------------------------
    # Calculate TDS
    # --------------------------------------------------

    if threshold_crossed:
        taxable = True

        tds_decimal = (
            Decimal(payment_paise) * applicable_rate
        )

        tds_paise = int(
            tds_decimal.quantize(
                Decimal("1"),
                rounding=ROUND_HALF_UP
            )
        )
    else:
        taxable = False
        tds_paise = 0

    return {
        "section": section,
        "normal_rate": normal_rate,
        "applicable_rate": applicable_rate,
        "threshold_crossed": threshold_crossed,
        "taxable": taxable,
        "payment_paise": payment_paise,
        "cumulative_fy_before_paise": cumulative_fy_before_paise,
        "cumulative_fy_after_paise": cumulative_after_paise,
        "tds_paise": tds_paise,
    }
