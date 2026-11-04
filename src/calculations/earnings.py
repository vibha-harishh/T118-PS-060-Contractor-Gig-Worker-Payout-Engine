
"""
Base earnings calculations for T118-PS-060.
Member 1: Payout and Earnings Module.
"""

from decimal import Decimal, ROUND_HALF_UP

import config


def calculate_base_task_pay(event_type: str, distance_km) -> int:
    """
    Calculate base task pay and return the amount in integer paise.

    Rules:
    - Completed task: ₹25 + ₹6 per km beyond 3 km.
    - Customer cancelled after pickup: ₹20.
    - Customer cancelled before pickup: ₹0.
    - Partner cancelled: ₹0.

    The completed-task amount is rounded to the nearest rupee.
    """

    # Validate distance
    try:
        distance = Decimal(str(distance_km))
    except Exception:
        raise ValueError("Distance must be a valid number.")

    if not distance.is_finite() or distance < 0:
        raise ValueError("Distance must be finite and non-negative.")

    # Calculate pay based on event type
    if event_type == "TASK_COMPLETED":

        extra_distance = max(
            Decimal("0"),
            distance - config.BASE_PAY_THRESHOLD_KM
        )

        total_pay = (
            config.BASE_PAY_FLAT_RUPEES
            + extra_distance * config.BASE_PAY_RATE_PER_EXTRA_KM_RUPEES
        )

        # Round to the nearest rupee
        rounded_pay = total_pay.quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP
        )

        return config.rupees_to_paise(rounded_pay)

    elif event_type == "CUSTOMER_CANCELLED_POST_PICKUP":
        return config.CUSTOMER_CANCELLATION_POST_PICKUP_PAISE

    elif event_type == "CUSTOMER_CANCELLED_PRE_PICKUP":
        return config.CUSTOMER_CANCELLATION_PRE_PICKUP_PAISE

    elif event_type == "PARTNER_CANCELLED":
        return config.PARTNER_CANCELLATION_PAISE

    else:
        raise ValueError(f"Unsupported event type: {event_type}")
