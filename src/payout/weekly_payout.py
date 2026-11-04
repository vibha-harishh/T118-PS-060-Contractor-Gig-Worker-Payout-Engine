
"""
Weekly payout calculation and database integration.

Calculates:
- Base task earnings
- Slot and rain surge
- Weekly incentives
- Cancellation and complaint penalties
- Penalty cap
- Bag deduction
- Final payable amount before TDS
"""

from decimal import Decimal

import config

from database.db import db_session
from src.calculations.earnings import calculate_base_task_pay
from src.calculations.surge import calculate_surge_pay
from src.payout.incentives import calculate_weekly_incentive
from src.payout.penalties import calculate_weekly_penalty
from src.payout.bag_deduction import calculate_bag_deduction


def calculate_weekly_payout(
    partner_id: str,
    week_identifier: str,
    db_path=None,
) -> dict:
    """Calculate and store one partner's weekly payout."""

    if not isinstance(partner_id, str) or not partner_id.strip():
        raise ValueError("Partner ID is required.")

    if not isinstance(week_identifier, str) or not week_identifier.strip():
        raise ValueError("Week identifier is required.")

    with db_session(db_path) as conn:

        # 1. Check whether the partner exists.
        partner = conn.execute(
            """
            SELECT partner_id, rating, bag_deduction_balance_paise
            FROM partners
            WHERE partner_id = ?;
            """,
            (partner_id,),
        ).fetchone()

        if partner is None:
            raise ValueError(f"Partner '{partner_id}' does not exist.")

        # 2. Prevent duplicate deductions if payout was already calculated.
        existing = conn.execute(
            """
            SELECT *
            FROM weekly_earnings
            WHERE partner_id = ? AND week_identifier = ?;
            """,
            (partner_id, week_identifier),
        ).fetchone()

        if existing is not None:
            return dict(existing)

        # 3. Fetch all task events for this partner and week.
        tasks = conn.execute(
            """
            SELECT *
            FROM tasks
            WHERE partner_id = ? AND week_identifier = ?
            ORDER BY task_timestamp, task_id;
            """,
            (partner_id, week_identifier),
        ).fetchall()

        if not tasks:
            raise ValueError(
                f"No tasks found for partner '{partner_id}' "
                f"in week '{week_identifier}'."
            )

        total_tasks = len(tasks)
        completed_tasks = 0
        partner_cancellations = 0
        gross_task_pay_paise = 0
        ratings = []

        # 4. Calculate individual task payments.
        for task in tasks:

            event_type = task["event_type"]

            base_pay = calculate_base_task_pay(
                event_type,
                task["distance_km"],
            )

            if event_type == "TASK_COMPLETED":

                completed_tasks += 1

                multiplier = config.resolve_surge_multiplier(
                    bool(task["is_slot_surge"]),
                    bool(task["is_rain_surge"]),
                )

                if task["rating"] is not None:
                    ratings.append(Decimal(str(task["rating"])))

            else:
                # Cancellation payments are flat and do not receive surge.
                multiplier = config.NO_SURGE_MULTIPLIER

            if event_type == "PARTNER_CANCELLED":
                partner_cancellations += 1

            final_pay = calculate_surge_pay(
                base_pay,
                multiplier,
            )

            conn.execute(
                """
                UPDATE tasks
                SET base_pay_paise = ?,
                    surge_multiplier = ?,
                    final_task_pay_paise = ?
                WHERE task_id = ?;
                """,
                (
                    base_pay,
                    float(multiplier),
                    final_pay,
                    task["task_id"],
                ),
            )

            gross_task_pay_paise += final_pay

        # 5. Calculate cancellation rate.
        cancellation_rate = (
            (total_tasks - completed_tasks) / total_tasks
        )

        # 6. Calculate average rating.
        if ratings:
            average_rating = (
                sum(ratings) / Decimal(len(ratings))
            )
        elif partner["rating"] is not None:
            average_rating = Decimal(str(partner["rating"]))
        else:
            average_rating = Decimal("5.0")

        # Keep the value within the database CHECK constraint.
        average_rating = max(
            Decimal("1.0"),
            min(Decimal("5.0"), average_rating),
        )

        # 7. Count verified complaints.
        complaint_row = conn.execute(
            """
            SELECT COUNT(*) AS complaint_count
            FROM complaints
            WHERE partner_id = ?
              AND week_identifier = ?
              AND is_verified = 1;
            """,
            (partner_id, week_identifier),
        ).fetchone()

        verified_complaints = complaint_row["complaint_count"]

        # 8. Calculate weekly incentive.
        incentive_amount_paise = calculate_weekly_incentive(
            completed_tasks,
            total_tasks,
            average_rating,
        )

        incentive_forfeited = int(
            completed_tasks >= 60
            and (
                Decimal(str(cancellation_rate))
                > config.INCENTIVE_MAX_CANCELLATION_RATE
                or average_rating < config.INCENTIVE_MIN_RATING
            )
        )

        # 9. Calculate gross weekly earnings.
        gross_weekly_earnings_paise = (
            gross_task_pay_paise + incentive_amount_paise
        )

        # 10. Calculate raw penalties.
        excess_cancellations = max(
            0,
            partner_cancellations
            - config.PENALTY_FREE_PARTNER_CANCELLATIONS,
        )

        raw_cancellation_penalty_paise = (
            excess_cancellations
            * config.PENALTY_PER_EXCESS_PARTNER_CANCELLATION_PAISE
        )

        raw_complaint_penalty_paise = (
            verified_complaints
            * config.PENALTY_PER_VERIFIED_COMPLAINT_PAISE
        )

        raw_total_penalties_paise = (
            raw_cancellation_penalty_paise
            + raw_complaint_penalty_paise
        )

        # 11. Apply the 20% penalty cap.
        capped_total_penalties_paise = calculate_weekly_penalty(
            partner_cancellations,
            verified_complaints,
            gross_weekly_earnings_paise,
        )

        # 12. Calculate earnings after penalties.
        net_before_bag_deduction_paise = (
            gross_weekly_earnings_paise
            - capped_total_penalties_paise
        )

        # 13. Calculate bag deduction.
        old_bag_balance = partner["bag_deduction_balance_paise"]

        bag_deduction_applied_paise = calculate_bag_deduction(
            old_bag_balance,
            net_before_bag_deduction_paise,
        )

        remaining_bag_balance_paise = (
            old_bag_balance - bag_deduction_applied_paise
        )

        bag_deduction_paused = int(
            old_bag_balance > 0
            and net_before_bag_deduction_paise
            < config.BAG_DEDUCTION_NET_PAYABLE_THRESHOLD_PAISE
        )

        # 14. Final amount before Member 2's TDS calculation.
        net_payable_before_tds_paise = (
            net_before_bag_deduction_paise
            - bag_deduction_applied_paise
        )

        # 15. Update partner's remaining bag balance.
        conn.execute(
            """
            UPDATE partners
            SET bag_deduction_balance_paise = ?
            WHERE partner_id = ?;
            """,
            (remaining_bag_balance_paise, partner_id),
        )

        # 16. Store weekly earnings summary.
        conn.execute(
            """
            INSERT INTO weekly_earnings (
                partner_id,
                week_identifier,
                total_tasks_assigned,
                completed_tasks,
                partner_cancellations,
                cancellation_rate,
                average_rating,
                gross_task_pay_paise,
                incentive_amount_paise,
                incentive_forfeited,
                gross_weekly_earnings_paise,
                raw_cancellation_penalty_paise,
                raw_complaint_penalty_paise,
                raw_total_penalties_paise,
                capped_total_penalties_paise,
                net_before_bag_deduction_paise,
                bag_deduction_applied_paise,
                bag_deduction_paused,
                remaining_bag_balance_paise,
                net_payable_before_tds_paise
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            );
            """,
            (
                partner_id,
                week_identifier,
                total_tasks,
                completed_tasks,
                partner_cancellations,
                cancellation_rate,
                float(average_rating),
                gross_task_pay_paise,
                incentive_amount_paise,
                incentive_forfeited,
                gross_weekly_earnings_paise,
                raw_cancellation_penalty_paise,
                raw_complaint_penalty_paise,
                raw_total_penalties_paise,
                capped_total_penalties_paise,
                net_before_bag_deduction_paise,
                bag_deduction_applied_paise,
                bag_deduction_paused,
                remaining_bag_balance_paise,
                net_payable_before_tds_paise,
            ),
        )

        # 17. Return the saved weekly payout.
        result = conn.execute(
            """
            SELECT *
            FROM weekly_earnings
            WHERE partner_id = ? AND week_identifier = ?;
            """,
            (partner_id, week_identifier),
        ).fetchone()

        return dict(result)
