"""
Surge pay calculations for T118-PS-060.
Member 1: Payout and Earnings Module.
"""

from decimal import Decimal, ROUND_HALF_UP

import config


def calculate_surge_pay(base_pay_paise: int, surge_multiplier) -> int:
    """
    Apply the surge multiplier to base pay.

    Input: Base pay in paise and surge multiplier.
    Output: Final task pay in integer paise.
    """

    # Validate base pay
    if isinstance(base_pay_paise, bool) or not isinstance(base_pay_paise, int):
        raise ValueError("Base pay must be an integer amount in paise.")

    if base_pay_paise < 0:
        raise ValueError("Base pay cannot be negative.")

    # Validate surge multiplier
    try:
        multiplier = Decimal(str(surge_multiplier))
    except Exception:
        raise ValueError("Invalid surge multiplier.")

    if not multiplier.is_finite():
        raise ValueError("Surge multiplier must be finite.")

    if multiplier not in config.ALLOWED_SURGE_MULTIPLIERS:
        raise ValueError("Surge multiplier must be 1.0, 1.3, or 1.5.")

    # Calculate final pay
    final_pay = (
        Decimal(base_pay_paise) * multiplier
    ).quantize(Decimal("1"), rounding=ROUND_HALF_UP)

    return int(final_pay)