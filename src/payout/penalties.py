
"""Cancellation and complaint penalty calculations for T118-PS-060."""

from decimal import Decimal, ROUND_DOWN

import config


def calculate_weekly_penalty(
    partner_cancellations: int,
    verified_complaints: int,
    weekly_gross_paise: int
) -> int:
    """
    Calculate weekly penalties in integer paise.

    Rules:
    - First 3 partner cancellations are free.
    - ₹50 for each additional partner cancellation.
    - ₹200 for each verified customer complaint.
    - Total penalties cannot exceed 20% of weekly gross.

    Returns:
        Total penalty in integer paise.
    """

    values = (
        partner_cancellations,
        verified_complaints,
        weekly_gross_paise
    )

    if any(
        not isinstance(value, int) or isinstance(value, bool)
        for value in values
    ):
        raise ValueError("All inputs must be integers.")

    if any(value < 0 for value in values):
        raise ValueError("Inputs cannot be negative.")

    excess_cancellations = max(
        0,
        partner_cancellations
        - config.PENALTY_FREE_PARTNER_CANCELLATIONS
    )

    cancellation_penalty = (
        excess_cancellations
        * config.PENALTY_PER_EXCESS_PARTNER_CANCELLATION_PAISE
    )

    complaint_penalty = (
        verified_complaints
        * config.PENALTY_PER_VERIFIED_COMPLAINT_PAISE
    )

    total_penalty = cancellation_penalty + complaint_penalty

    penalty_cap = (
        Decimal(weekly_gross_paise)
        * config.PENALTY_CAP_GROSS_PERCENTAGE
    ).quantize(Decimal("1"), rounding=ROUND_DOWN)

    return min(total_penalty, int(penalty_cap))
