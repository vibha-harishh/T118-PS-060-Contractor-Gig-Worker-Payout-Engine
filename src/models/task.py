"""
Task Event Model, Validation, and Persistence Service
Project: T118-PS-060
Member 1: Payout and Earnings Module

This module implements:
- Task entity data structure with strict typing.
- Input validation conforming to PS-060 specifications.
- Support for approved event types:
  * TASK_COMPLETED
  * CUSTOMER_CANCELLED_POST_PICKUP
  * CUSTOMER_CANCELLED_PRE_PICKUP
  * PARTNER_CANCELLED
- Foreign key validation against registered partners.
- Distance, duration, slot/rain surge flag, and customer rating validation.
- Timestamp parsing and conversion to Indian Standard Time (Asia/Kolkata).
- Automatic ISO week identifier calculation in IST.
- Raw task event persistence with default payout values.
- Payout field updates through a separate persistence function.
- Prevention of duplicate task IDs.
"""

from dataclasses import asdict, dataclass
from datetime import datetime
import math
from decimal import Decimal, InvalidOperation
import sqlite3
from typing import Any, Dict, List, Optional, Union

import config
from database.db import DatabaseError, db_session, get_db_connection
from src.models.partner import PartnerNotFoundError


# ==============================================================================
# Domain Exceptions
# ==============================================================================
class TaskValidationError(ValueError):
    """Raised when task input data violates domain or schema validation rules."""
    pass


class DuplicateTaskError(Exception):
    """Raised when an attempt is made to insert an already existing task ID."""
    pass


class TaskNotFoundError(Exception):
    """Raised when a requested task ID is not found in the database."""
    pass


# ==============================================================================
# Task Data Class
# ==============================================================================
@dataclass
class Task:
    """Represents a gig delivery or service task event."""

    task_id: str
    partner_id: str
    event_type: str                     # TASK_COMPLETED, CUSTOMER_CANCELLED_POST_PICKUP, etc.
    distance_km: float                  # Non-negative distance
    duration_minutes: float = 0.0       # Non-negative duration
    task_type: str = "DELIVERY"         # DELIVERY or SERVICE
    slot_type: str = "REGULAR"          # REGULAR, LUNCH_PEAK, DINNER_PEAK, etc.
    is_slot_surge: int = 0              # 1 if slot surge applies, else 0
    is_rain_surge: int = 0              # 1 if rain surge applies, else 0
    rating: Optional[float] = None      # Customer rating 1.0 to 5.0 (optional)
    cancellation_reason: Optional[str] = None
    base_pay_paise: int = 0             # Base pay in paise (₹25 + ₹6/km > 3km or cancellation flat)
    surge_multiplier: float = 1.0       # 1.0, 1.3, or 1.5
    final_task_pay_paise: int = 0       # Base pay * surge multiplier in paise
    task_timestamp: str = ""            # ISO timestamp formatted in IST
    task_date: str = ""                 # YYYY-MM-DD in IST
    week_identifier: str = ""           # e.g., '2026-W45' in IST
    created_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the Task object into a dictionary."""
        return asdict(self)

    @property
    def base_pay_rupees(self) -> Decimal:
        """Returns the base pay in Decimal Rupees."""
        return config.paise_to_rupees(self.base_pay_paise)

    @property
    def final_task_pay_rupees(self) -> Decimal:
        """Returns the final pay in Decimal Rupees."""
        return config.paise_to_rupees(self.final_task_pay_paise)

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Task":
        """Constructs a Task instance from an SQLite database row."""
        return cls(
            task_id=row["task_id"],
            partner_id=row["partner_id"],
            task_type=row["task_type"],
            event_type=row["event_type"],
            distance_km=float(row["distance_km"]),
            duration_minutes=float(row["duration_minutes"]),
            slot_type=row["slot_type"] or "REGULAR",
            is_slot_surge=int(row["is_slot_surge"]),
            is_rain_surge=int(row["is_rain_surge"]),
            rating=float(row["rating"]) if row["rating"] is not None else None,
            cancellation_reason=row["cancellation_reason"],
            base_pay_paise=int(row["base_pay_paise"]),
            surge_multiplier=float(row["surge_multiplier"]),
            final_task_pay_paise=int(row["final_task_pay_paise"]),
            task_timestamp=str(row["task_timestamp"]),
            task_date=str(row["task_date"]),
            week_identifier=str(row["week_identifier"]),
            created_at=str(row["created_at"]) if row["created_at"] else None,
        )


# ==============================================================================
# Helper Parsing Functions
# ==============================================================================
def parse_task_timestamp(ts_val: Union[datetime, str]) -> datetime:
    """
    Parses a timestamp string or datetime, converts it to IST, and verifies validity.
    Supports standard ISO formats, UTC, naive strings, and space-separated date-time strings.
    """
    if isinstance(ts_val, datetime):
        return config.to_ist(ts_val)

    if not ts_val or not str(ts_val).strip():
        raise TaskValidationError("task_timestamp cannot be empty.")

    clean_str = str(ts_val).strip()
    if clean_str.endswith("Z"):
        clean_str = clean_str[:-1] + "+00:00"

    formats = (
        None,  # fromisoformat
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    )
    for fmt in formats:
        try:
            if fmt is None:
                dt = datetime.fromisoformat(clean_str)
            else:
                dt = datetime.strptime(clean_str, fmt)
            return config.to_ist(dt)
        except (ValueError, TypeError):
            continue

    raise TaskValidationError(
        f"Invalid task_timestamp '{ts_val}'. Expected format: YYYY-MM-DD HH:MM:SS."
    )


def parse_bool_flag(val: Any, default: int = 0) -> int:
    """Parses boolean / integer representations (0, 1, true, false, yes, no)."""
    if val is None or str(val).strip() == "":
        return default

    if isinstance(val, bool):
        return 1 if val else 0

    if isinstance(val, (int, float)):
        if not math.isfinite(float(val)) or val not in (0, 1):
            raise TaskValidationError(
                f"Invalid boolean surge flag: '{val}'. Expected 0 or 1."
            )
        return int(val)

    s = str(val).strip().lower()

    if s in ("1", "true", "t", "yes", "y"):
        return 1

    if s in ("0", "false", "f", "no", "n"):
        return 0

    raise TaskValidationError(
        f"Invalid boolean surge flag: '{val}'. Expected 0, 1, true, or false."
    )

# ==============================================================================
# Validation Function
# ==============================================================================
def validate_task_data(
    task_id: str,
    partner_id: str,
    event_type: str,
    distance_km: Union[float, int, str],
    task_timestamp: Union[datetime, str],
    duration_minutes: Union[float, int, str] = 0.0,
    task_type: str = "DELIVERY",
    slot_type: Optional[str] = "REGULAR",
    is_slot_surge: Any = 0,
    is_rain_surge: Any = 0,
    rating: Optional[Union[float, int, str]] = None,
    cancellation_reason: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Validates and normalizes all fields for task registration and calculations.

    Enforces:
    - task_id: non-empty string.
    - partner_id: non-empty string.
    - task_type: 'DELIVERY' or 'SERVICE'.
    - event_type: in config.EVENT_TYPES.
    - distance_km: non-negative float.
    - duration_minutes: non-negative float.
    - is_slot_surge, is_rain_surge: 0 or 1.
    - rating: optional float between 1.0 and 5.0 (or None).
    - task_timestamp: parsed and converted to IST.
    - task_date and week_identifier: accurately resolved in IST.

    :return: Normalized dictionary of validated task attributes.
    :raises TaskValidationError: If validation fails.
    """
    # 1. Task ID
    if not task_id or not str(task_id).strip():
        raise TaskValidationError("task_id cannot be empty.")
    norm_task_id = str(task_id).strip()

    # 2. Partner ID
    if not partner_id or not str(partner_id).strip():
        raise TaskValidationError("partner_id cannot be empty.")
    norm_partner_id = str(partner_id).strip()

    # 3. Task Type
    norm_task_type = str(task_type).strip().upper() if task_type else "DELIVERY"
    if norm_task_type not in ("DELIVERY", "SERVICE"):
        raise TaskValidationError(f"Invalid task_type '{task_type}'. Allowed values: ('DELIVERY', 'SERVICE').")

    # 4. Event Type
    if not event_type or not str(event_type).strip():
        raise TaskValidationError("event_type cannot be empty.")
    norm_event_type = str(event_type).strip().upper()
    if norm_event_type not in config.EVENT_TYPES:
        raise TaskValidationError(
            f"Invalid event_type '{event_type}'. Allowed values: {config.EVENT_TYPES}"
        )

    # 5. Distance (km)
    try:
        norm_distance = float(distance_km)
    except (ValueError, TypeError):
        raise TaskValidationError(f"distance_km must be a valid numeric value, got: {distance_km}")
    if not math.isfinite(norm_distance) or norm_distance < 0.0:
        raise TaskValidationError(
            f"distance_km must be a finite, non-negative number, got: {distance_km}")
    
    # 6. Duration (minutes)
    try:
        norm_duration = float(duration_minutes) if duration_minutes is not None else 0.0
    except (ValueError, TypeError):
        raise TaskValidationError(f"duration_minutes must be a valid numeric value, got: {duration_minutes}")

    if not math.isfinite(norm_duration) or norm_duration < 0.0:
        raise TaskValidationError(
            f"duration_minutes must be a finite, non-negative number, got: {duration_minutes}"
        )
    # 7. Slot & Rain Surges
    norm_slot_surge = parse_bool_flag(is_slot_surge, default=0)
    norm_rain_surge = parse_bool_flag(is_rain_surge, default=0)
    norm_slot_type = str(slot_type).strip() if slot_type and str(slot_type).strip() else "REGULAR"

    # 8. Rating
    norm_rating: Optional[float] = None
    if rating is not None and str(rating).strip():
        try:
            norm_rating = float(rating)
        except (ValueError, TypeError):
            raise TaskValidationError(f"rating must be a numeric value between 1.0 and 5.0, got: {rating}")
        if not math.isfinite(norm_rating) or norm_rating < 1.0 or norm_rating > 5.0:
            raise TaskValidationError(f"rating must be between 1.0 and 5.0, got: {rating}")

    # 9. Cancellation reason
    norm_cancellation_reason = str(cancellation_reason).strip() if cancellation_reason and str(cancellation_reason).strip() else None

    # 10. Timestamp & IST resolution
    dt_ist = parse_task_timestamp(task_timestamp)
    norm_timestamp_str = dt_ist.strftime("%Y-%m-%d %H:%M:%S%z")
    norm_task_date = dt_ist.strftime("%Y-%m-%d")
    norm_week_id = config.get_week_identifier(dt_ist)

    return {
        "task_id": norm_task_id,
        "partner_id": norm_partner_id,
        "task_type": norm_task_type,
        "event_type": norm_event_type,
        "distance_km": norm_distance,
        "duration_minutes": norm_duration,
        "slot_type": norm_slot_type,
        "is_slot_surge": norm_slot_surge,
        "is_rain_surge": norm_rain_surge,
        "rating": norm_rating,
        "cancellation_reason": norm_cancellation_reason,
        "base_pay_paise": 0,
        "surge_multiplier": 1.0,
        "final_task_pay_paise": 0,
        "task_timestamp": norm_timestamp_str,
        "task_date": norm_task_date,
        "week_identifier": norm_week_id,
    }

    

# ==============================================================================
# Task Registration & Query Functions
# ==============================================================================
def record_task(
    task_id: str,
    partner_id: str,
    event_type: str,
    distance_km: Union[float, int, str],
    task_timestamp: Union[datetime, str],
    duration_minutes: Union[float, int, str] = 0.0,
    task_type: str = "DELIVERY",
    slot_type: Optional[str] = "REGULAR",
    is_slot_surge: Any = 0,
    is_rain_surge: Any = 0,
    rating: Optional[Union[float, int, str]] = None,
    cancellation_reason: Optional[str] = None,
    db_path: Optional[Union[str, Any]] = None,
) -> Task:
    """
    Validates and persists a task event into the SQLite database.

    Verifications:
    1. Validates all task fields.
    2. Verifies that the partner exists in the database.
    3. Checks for duplicate task_id.
    4. Inserts the record into the tasks table inside an atomic transaction.

    :raises PartnerNotFoundError: If partner_id does not exist in the database.
    :raises DuplicateTaskError: If task_id is already registered.
    :raises TaskValidationError: If data fails domain validation.
    """
    validated = validate_task_data(
        task_id=task_id,
        partner_id=partner_id,
        event_type=event_type,
        distance_km=distance_km,
        task_timestamp=task_timestamp,
        duration_minutes=duration_minutes,
        task_type=task_type,
        slot_type=slot_type,
        is_slot_surge=is_slot_surge,
        is_rain_surge=is_rain_surge,
        rating=rating,
        cancellation_reason=cancellation_reason,
    )

    with db_session(db_path) as conn:
        cursor = conn.cursor()

        # 1. Verify partner exists
        cursor.execute("SELECT 1 FROM partners WHERE partner_id = ?;", (validated["partner_id"],))
        if not cursor.fetchone():
            raise PartnerNotFoundError(
                f"Partner with ID '{validated['partner_id']}' does not exist in the database."
            )

        # 2. Verify duplicate task_id
        cursor.execute("SELECT 1 FROM tasks WHERE task_id = ?;", (validated["task_id"],))
        if cursor.fetchone():
            raise DuplicateTaskError(
                f"Task with ID '{validated['task_id']}' is already registered."
            )

        # 3. Insert record
        insert_sql = """
        INSERT INTO tasks (
            task_id, partner_id, task_type, event_type, distance_km, duration_minutes,
            slot_type, is_slot_surge, is_rain_surge, rating, cancellation_reason,
            base_pay_paise, surge_multiplier, final_task_pay_paise,
            task_timestamp, task_date, week_identifier
        ) VALUES (
            :task_id, :partner_id, :task_type, :event_type, :distance_km, :duration_minutes,
            :slot_type, :is_slot_surge, :is_rain_surge, :rating, :cancellation_reason,
            :base_pay_paise, :surge_multiplier, :final_task_pay_paise,
            :task_timestamp, :task_date, :week_identifier
        );
        """
        cursor.execute(insert_sql, validated)

    task = get_task(validated["task_id"], db_path=db_path)
    if not task:
        raise DatabaseError(f"Failed to retrieve task '{validated['task_id']}' after registration.")
    return task


def update_task_payout(
    task_id: str,
    base_pay_paise: int,
    surge_multiplier: Union[float, Decimal],
    final_task_pay_paise: int,
    db_path: Optional[Union[str, Any]] = None,
) -> Task:
    """
    Updates the payout fields for an existing task in the database.
    Does NOT calculate payments itself; only persists verified payout fields.

    :param task_id: Identifier of the task to update.
    :param base_pay_paise: Base payment amount in integer paise (>= 0).
    :param surge_multiplier: Surge multiplier (must be in config.ALLOWED_SURGE_MULTIPLIERS).
    :param final_task_pay_paise: Final task payment amount in integer paise (>= 0).
    :param db_path: Optional SQLite database path.
    :return: Updated Task object.
    :raises TaskNotFoundError: If task_id does not exist.
    :raises TaskValidationError: If payout values violate constraints.
    """
    if not task_id or not str(task_id).strip():
        raise TaskValidationError("task_id cannot be empty.")
    clean_task_id = str(task_id).strip()

    # Validate base_pay_paise
    if isinstance(base_pay_paise, bool):
        raise TaskValidationError("base_pay_paise must be a whole number.")

    try:
        base_decimal = Decimal(str(base_pay_paise))
    except (ValueError, TypeError, InvalidOperation):
        raise TaskValidationError(
            f"base_pay_paise must be a valid integer, got: {base_pay_paise}"
         )
    if (
        not base_decimal.is_finite()
        or base_decimal != base_decimal.to_integral_value()
    ):
        raise TaskValidationError(
            f"base_pay_paise must be a whole number, got: {base_pay_paise}"
        )

    norm_base_pay = int(base_decimal)

    if norm_base_pay < 0:
        raise TaskValidationError(
            f"base_pay_paise cannot be negative, got: {base_pay_paise}"
        )   
    # Validate surge_multiplier
    try:
        norm_surge_dec = Decimal(str(surge_multiplier))
    except (ValueError, TypeError, InvalidOperation):
        raise TaskValidationError(
            f"Invalid surge_multiplier format: {surge_multiplier}"
        )

    if (
        not norm_surge_dec.is_finite()
        or norm_surge_dec not in config.ALLOWED_SURGE_MULTIPLIERS
    ):
        raise TaskValidationError(
            f"Invalid surge_multiplier {surge_multiplier}. "
            f"Allowed values: {config.ALLOWED_SURGE_MULTIPLIERS}"
        )

    norm_surge_float = float(norm_surge_dec)

    # Validate final_task_pay_paise
    if isinstance(final_task_pay_paise, bool):
        raise TaskValidationError(
            "final_task_pay_paise must be a whole number."
        )

    try:
        final_decimal = Decimal(str(final_task_pay_paise))
    except (ValueError, TypeError, InvalidOperation):
        raise TaskValidationError(
            f"final_task_pay_paise must be a valid integer, got: {final_task_pay_paise}"
        )

    if (
        not final_decimal.is_finite()
        or final_decimal != final_decimal.to_integral_value()
    ):
        raise TaskValidationError(
            f"final_task_pay_paise must be a whole number, got: {final_task_pay_paise}"
        )

    norm_final_pay = int(final_decimal)

    if norm_final_pay < 0:
        raise TaskValidationError(
            f"final_task_pay_paise cannot be negative, got: {final_task_pay_paise}"
        )
    # Update payout fields in the database
    with db_session(db_path) as conn:
        cursor = conn.cursor()

        cursor.execute(
            "SELECT 1 FROM tasks WHERE task_id = ?;",
            (clean_task_id,)
        )

        if not cursor.fetchone():
            raise TaskNotFoundError(
                f"Task with ID '{clean_task_id}' does not exist."
            )

        cursor.execute(
            """
            UPDATE tasks
            SET base_pay_paise = ?,
                surge_multiplier = ?,
                final_task_pay_paise = ?
            WHERE task_id = ?;
            """,
            (
                norm_base_pay,
                norm_surge_float,
                norm_final_pay,
                clean_task_id
            ),
        )

    updated_task = get_task(clean_task_id, db_path=db_path)
    if not updated_task:
        raise DatabaseError(
            f"Failed to fetch task '{clean_task_id}' after payout update."
        )

    return updated_task
def get_task(task_id: str, db_path=None):
    """Retrieve a task using its ID. Return None if not found."""
    clean_task_id = str(task_id).strip()

    if not clean_task_id:
        raise TaskValidationError("task_id cannot be empty.")

    with db_session(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM tasks WHERE task_id = ?;",
            (clean_task_id,)
        ).fetchone()

    if row is None:
        return None

    return Task.from_row(row)
def list_tasks(
    partner_id: Optional[str] = None,
    db_path: Optional[Union[str, Any]] = None,
) -> List[Task]:
    """Retrieve all tasks, optionally filtered by partner ID."""
    with db_session(db_path) as conn:
        if partner_id is not None:
            clean_partner_id = str(partner_id).strip()
            if not clean_partner_id:
                raise TaskValidationError("partner_id cannot be empty.")

            rows = conn.execute(
                """
                SELECT * FROM tasks
                WHERE partner_id = ?
                ORDER BY task_timestamp, task_id;
                """,
                (clean_partner_id,)
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM tasks
                ORDER BY task_timestamp, task_id;
                """
            ).fetchall()

    return [Task.from_row(row) for row in rows]