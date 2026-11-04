"""
Central Configuration for T118-PS-060
Contractor and Gig-Worker Payout Engine with TDS and Weekly Settlement
Member 1: Payout and Earnings Module

Financial Standard:
- All monetary constants and calculations in Python use `decimal.Decimal`
  to guarantee absolute precision and eliminate floating-point drift.
- All database monetary amounts are stored as INTEGER PAISE (₹1 = 100 Paise).

Timezone Standard:
- All operational event timestamps and weekly cycles are evaluated in
  Indian Standard Time (Asia/Kolkata).
"""

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Union
import zoneinfo

# ==============================================================================
# Timezone Configuration (Indian Standard Time - Asia/Kolkata)
# ==============================================================================
TIMEZONE_NAME = "Asia/Kolkata"
IST = zoneinfo.ZoneInfo(TIMEZONE_NAME)


def now_ist() -> datetime:
    """Returns the current datetime in Asia/Kolkata (IST)."""
    return datetime.now(IST)


def to_ist(dt: datetime) -> datetime:
    """Converts a naive or timezone-aware datetime to Asia/Kolkata (IST)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=IST)
    return dt.astimezone(IST)


def get_week_identifier(dt: datetime) -> str:
    """
    Returns the ISO-8601 week identifier formatted as 'YYYY-Www' in IST.
    Example: 2026-11-02 -> '2026-W45'.
    """
    dt_ist = to_ist(dt)
    year, week, _ = dt_ist.isocalendar()
    return f"{year}-W{week:02d}"


# ==============================================================================
# Currency Conversion Helpers (Decimal <-> Integer Paise)
# ==============================================================================
def rupees_to_paise(rupees: Union[Decimal, float, str, int]) -> int:
    """
    Converts a Rupee amount to Integer Paise using exact Decimal arithmetic.
    Example: Decimal('25.00') -> 2500, '1.50' -> 150.
    """
    d = Decimal(str(rupees))
    return int((d * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def paise_to_rupees(paise: int) -> Decimal:
    """
    Converts an Integer Paise amount back to a Decimal Rupee amount.
    Example: 2500 -> Decimal('25.00'), 150 -> Decimal('1.50').
    """
    return (Decimal(paise) / Decimal("100")).quantize(Decimal("0.01"))


# ==============================================================================
# Database Configuration
# ==============================================================================
BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "payout_engine.db"
SCHEMA_PATH = BASE_DIR / "database" / "schema.sql"

# ==============================================================================
# Partner Domain Enums & Allowed Values
# ==============================================================================
PARTNER_TYPES = ("INDIVIDUAL", "FIRM")
PAN_STATUSES = ("VALID", "INVALID", "MISSING")
CATEGORIES = ("DELIVERY", "SERVICE_PROFESSIONAL")
BANK_VERIFICATION_STATUSES = ("VERIFIED", "UNVERIFIED", "FAILED", "PENDING")
PARTNER_STATUSES = ("ACTIVE", "INACTIVE", "SUSPENDED")

# ==============================================================================
# Task Event Types (Single canonical field representing delivery event state)
# ==============================================================================
EVENT_TYPES = (
    "TASK_COMPLETED",                  # Task delivered successfully
    "CUSTOMER_CANCELLED_POST_PICKUP",  # Customer cancelled after pickup: ₹20 flat (2,000 paise)
    "CUSTOMER_CANCELLED_PRE_PICKUP",   # Customer cancelled before pickup: ₹0 pay
    "PARTNER_CANCELLED",               # Partner cancelled: ₹0 pay, penalty counter incremented
)

# ==============================================================================
# 1. Base Task Payment Rules (PS-060)
# ==============================================================================
# Base pay: ₹25 + ₹6 per km beyond 3 km, rounded to the nearest rupee.
BASE_PAY_FLAT_RUPEES = Decimal("25.00")
BASE_PAY_FLAT_PAISE = rupees_to_paise(BASE_PAY_FLAT_RUPEES)                  # 2,500 paise

BASE_PAY_THRESHOLD_KM = Decimal("3.0")

BASE_PAY_RATE_PER_EXTRA_KM_RUPEES = Decimal("6.00")
BASE_PAY_RATE_PER_EXTRA_KM_PAISE = rupees_to_paise(BASE_PAY_RATE_PER_EXTRA_KM_RUPEES) # 600 paise

# Cancellation task pay rules
CUSTOMER_CANCELLATION_POST_PICKUP_RUPEES = Decimal("20.00")
CUSTOMER_CANCELLATION_POST_PICKUP_PAISE = rupees_to_paise(CUSTOMER_CANCELLATION_POST_PICKUP_RUPEES) # 2,000 paise
CUSTOMER_CANCELLATION_PRE_PICKUP_PAISE = 0                                  # 0 paise (₹0)
PARTNER_CANCELLATION_PAISE = 0                                              # 0 paise (₹0)

# Backwards-compatible aliases
BASE_PAY_FLAT = float(BASE_PAY_FLAT_RUPEES)
BASE_PAY_RATE_PER_EXTRA_KM = float(BASE_PAY_RATE_PER_EXTRA_KM_RUPEES)
CUSTOMER_CANCELLATION_POST_PICKUP_PAY = float(CUSTOMER_CANCELLATION_POST_PICKUP_RUPEES)
PARTNER_CANCELLATION_PAY = 0.0

# ==============================================================================
# 2. Surge Pricing Rules (PS-060)
# ==============================================================================
SLOT_SURGE_MULTIPLIER = Decimal("1.3")        # Slot surge = 1.3x
RAIN_SURGE_MULTIPLIER = Decimal("1.5")        # Rain surge = 1.5x
NO_SURGE_MULTIPLIER = Decimal("1.0")          # Default = 1.0x

# Exactly permitted surge multipliers
ALLOWED_SURGE_MULTIPLIERS = (
    Decimal("1.0"),
    Decimal("1.3"),
    Decimal("1.5"),
)


def resolve_surge_multiplier(is_slot_surge: bool, is_rain_surge: bool) -> Decimal:
    """
    Resolves the applicable surge multiplier according to PS-060 business rules:
    - Slot surge: 1.3x.
    - Rain surge: 1.5x.
    - If both surges apply, select ONLY the higher multiplier (1.5x), NOT multiplied.
    - If neither applies, default to 1.0x.
    """
    if is_slot_surge and is_rain_surge:
        return max(SLOT_SURGE_MULTIPLIER, RAIN_SURGE_MULTIPLIER)  # 1.5 (higher multiplier only)
    elif is_rain_surge:
        return RAIN_SURGE_MULTIPLIER                              # 1.5
    elif is_slot_surge:
        return SLOT_SURGE_MULTIPLIER                              # 1.3
    return NO_SURGE_MULTIPLIER                                    # 1.0


# ==============================================================================
# 3. Weekly Incentive Rules (PS-060)
# ==============================================================================
# Tiers: 60+ tasks = ₹600, 90+ tasks = ₹1200, 120+ tasks = ₹2000 (highest tier only).
INCENTIVE_TIERS_PAISE = [
    (120, rupees_to_paise(Decimal("2000.00"))),  # 200,000 paise (₹2,000)
    (90, rupees_to_paise(Decimal("1200.00"))),   # 120,000 paise (₹1,200)
    (60, rupees_to_paise(Decimal("600.00"))),    # 60,000 paise (₹600)
]

INCENTIVE_TIERS = [
    (120, 2000.0),
    (90, 1200.0),
    (60, 600.0),
]

# Forfeit conditions:
# Forfeit incentive if cancellation rate is greater than 8% OR average rating is below 4.2
INCENTIVE_MAX_CANCELLATION_RATE = Decimal("0.08")  # 8%
INCENTIVE_MIN_RATING = Decimal("4.2")              # Minimum average customer rating

# ==============================================================================
# 4. Cancellation & Complaint Penalties (PS-060)
# ==============================================================================
# ₹50 for each partner cancellation beyond 3
PENALTY_FREE_PARTNER_CANCELLATIONS = 3
PENALTY_PER_EXCESS_PARTNER_CANCELLATION_RUPEES = Decimal("50.00")
PENALTY_PER_EXCESS_PARTNER_CANCELLATION_PAISE = rupees_to_paise(PENALTY_PER_EXCESS_PARTNER_CANCELLATION_RUPEES)  # 5,000 paise
PENALTY_PER_EXCESS_PARTNER_CANCELLATION = 50.0

# ₹200 for each verified customer complaint
PENALTY_PER_VERIFIED_COMPLAINT_RUPEES = Decimal("200.00")
PENALTY_PER_VERIFIED_COMPLAINT_PAISE = rupees_to_paise(PENALTY_PER_VERIFIED_COMPLAINT_RUPEES)              # 20,000 paise
PENALTY_PER_VERIFIED_COMPLAINT = 200.0

# Penalty Cap: Total penalties capped at 20% of weekly gross
PENALTY_CAP_GROSS_PERCENTAGE = Decimal("0.20")      # 20%

# ==============================================================================
# 5. Equipment / Bag Deduction Rules (PS-060)
# ==============================================================================
# ₹150 per week until ₹1,800 is recovered
BAG_TOTAL_AMOUNT_RUPEES = Decimal("1800.00")
BAG_TOTAL_AMOUNT_PAISE = rupees_to_paise(BAG_TOTAL_AMOUNT_RUPEES)           # 180,000 paise
BAG_TOTAL_AMOUNT = 1800.0

BAG_WEEKLY_DEDUCTION_RUPEES = Decimal("150.00")
BAG_WEEKLY_DEDUCTION_PAISE = rupees_to_paise(BAG_WEEKLY_DEDUCTION_RUPEES)   # 15,000 paise
BAG_WEEKLY_DEDUCTION = 150.0

# Pause deduction if net payable before TDS is below ₹1,000
BAG_DEDUCTION_NET_PAYABLE_THRESHOLD_RUPEES = Decimal("1000.00")
BAG_DEDUCTION_NET_PAYABLE_THRESHOLD_PAISE = rupees_to_paise(BAG_DEDUCTION_NET_PAYABLE_THRESHOLD_RUPEES) # 100,000 paise
BAG_DEDUCTION_NET_PAYABLE_THRESHOLD = 1000.0
