
"""
Equipment / Bag Deduction Module
Project: T118-PS-060

Calculates weekly bag deductions using integer paise.
"""

from config import (
    BAG_TOTAL_AMOUNT_PAISE,
    BAG_WEEKLY_DEDUCTION_PAISE,
    BAG_DEDUCTION_NET_PAYABLE_THRESHOLD_PAISE,
)


def calculate_bag_deduction(
    remaining_balance_paise: int,
    net_payable_before_tds_paise: int,
) -> int:
    """
    Calculate the weekly bag deduction.

    Rules:
    - Deduct ₹150 per week.
    - Maximum total recovery is ₹1,800.
    - Pause deduction if net payable before TDS is below ₹1,000.
    - Never deduct more than the remaining bag balance.

    Returns:
        Deduction amount in integer paise.
    """

    # Validate inputs
    if (
        isinstance(remaining_balance_paise, bool)
        or not isinstance(remaining_balance_paise, int)
        or remaining_balance_paise < 0
    ):
        raise ValueError("Remaining balance must be a non-negative integer.")

    if (
        isinstance(net_payable_before_tds_paise, bool)
        or not isinstance(net_payable_before_tds_paise, int)
        or net_payable_before_tds_paise < 0
    ):
        raise ValueError("Net payable must be a non-negative integer.")

    # No deduction if the bag amount is fully recovered
    if remaining_balance_paise == 0:
        return 0

    # Pause deduction if net payable is below ₹1,000
    if (
        net_payable_before_tds_paise
        < BAG_DEDUCTION_NET_PAYABLE_THRESHOLD_PAISE
    ):
        return 0

    # Deduct the smaller of weekly deduction and remaining balance
    deduction = min(
        BAG_WEEKLY_DEDUCTION_PAISE,
        remaining_balance_paise,
        BAG_TOTAL_AMOUNT_PAISE,
    )

    return deduction
