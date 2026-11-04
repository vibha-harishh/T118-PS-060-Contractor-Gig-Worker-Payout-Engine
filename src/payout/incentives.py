
"""Weekly incentive calculations for T118-PS-060."""

from decimal import Decimal, InvalidOperation

import config


def calculate_weekly_incentive(
    completed_tasks: int,
    total_tasks: int,
    average_rating
) -> int:
    """
    Calculate weekly incentive in integer paise.

    Rules:
    - 60+ tasks: ₹600
    - 90+ tasks: ₹1,200
    - 120+ tasks: ₹2,000
    - Only highest eligible tier is awarded.
    - Forfeit if cancellation rate > 8%.
    - Forfeit if average rating < 4.2.

    Returns:
        Incentive amount in integer paise.
    """

    # Validate task counts
    if (
        not isinstance(completed_tasks, int)
        or isinstance(completed_tasks, bool)
    ):
        raise ValueError("Completed tasks must be an integer.")

    if (
        not isinstance(total_tasks, int)
        or isinstance(total_tasks, bool)
    ):
        raise ValueError("Total tasks must be an integer.")

    if completed_tasks < 0 or total_tasks < 0:
        raise ValueError("Task counts cannot be negative.")

    if completed_tasks > total_tasks:
        raise ValueError("Completed tasks cannot exceed total tasks.")

    # No tasks means no incentive
    if total_tasks == 0:
        return 0

    # Validate average rating
    try:
        rating = Decimal(str(average_rating))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("Average rating must be a valid number.")

    if not rating.is_finite() or not Decimal("1") <= rating <= Decimal("5"):
        raise ValueError("Average rating must be between 1 and 5.")

    # Calculate cancellation rate using Decimal
    cancellation_rate = (
        Decimal(total_tasks - completed_tasks)
        / Decimal(total_tasks)
    )

    # Check incentive forfeiture conditions
    if cancellation_rate > config.INCENTIVE_MAX_CANCELLATION_RATE:
        return 0

    if rating < config.INCENTIVE_MIN_RATING:
        return 0

    # Award highest eligible incentive tier only
    for task_threshold, incentive_paise in config.INCENTIVE_TIERS_PAISE:
        if completed_tasks >= task_threshold:
            return incentive_paise

    return 0
