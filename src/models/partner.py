
"""
Partner Model, Validation, and Registration Service
Project: T118-PS-060
Member 1: Payout and Earnings Module

Implements:
- Partner entity data structure with strict typing.
- Input validation for PS-060 specifications.
- INDIVIDUAL and FIRM partner types.
- VALID, INVALID, and MISSING PAN statuses.
- DELIVERY and SERVICE_PROFESSIONAL categories.
- Bank details and verification statuses.
- Prevention of duplicate partner IDs and PAN values.
"""

from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal
import math
import re
import sqlite3
from typing import Any, Dict, List, Optional, Union

import config
from database.db import DatabaseError, db_session, get_db_connection


# Standard Indian PAN format
PAN_REGEX = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]{1}$")

# Standard Indian IFSC format
IFSC_REGEX = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")

# Standard 10-digit mobile number
PHONE_REGEX = re.compile(r"^[0-9]{10}$")


# ==============================================================================
# Domain Exceptions
# ==============================================================================

class PartnerValidationError(ValueError):
    """Raised when partner data violates validation rules."""
    pass


class DuplicatePartnerError(Exception):
    """Raised when a partner ID already exists."""
    pass


class DuplicatePANError(Exception):
    """Raised when a PAN is already assigned to another partner."""
    pass


class PartnerNotFoundError(Exception):
    """Raised when a requested partner cannot be found."""
    pass


# ==============================================================================
# Partner Data Class
# ==============================================================================

@dataclass
class Partner:
    """Represents a delivery or service professional."""

    partner_id: str
    partner_name: str
    partner_type: str
    category: str
    onboarding_date: str

    pan: Optional[str] = None
    pan_status: str = "MISSING"
    phone: Optional[str] = None
    bank_account_number: Optional[str] = None
    ifsc_code: Optional[str] = None
    bank_verification_status: str = "PENDING"

    city: str = "Bangalore"
    rating: float = 5.0
    status: str = "ACTIVE"

    bag_deduction_balance_paise: int = config.BAG_TOTAL_AMOUNT_PAISE
    created_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert Partner object into a dictionary."""
        return asdict(self)

    @property
    def bag_deduction_balance_rupees(self) -> Decimal:
        """Return bag balance in rupees."""
        return config.paise_to_rupees(
            self.bag_deduction_balance_paise
        )

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Partner":
        """Create Partner object from SQLite row."""

        return cls(
            partner_id=row["partner_id"],
            partner_name=row["partner_name"],
            partner_type=row["partner_type"],
            pan=row["pan"],
            pan_status=row["pan_status"],
            category=row["category"],
            phone=row["phone"],
            bank_account_number=row["bank_account_number"],
            ifsc_code=row["ifsc_code"],
            bank_verification_status=row["bank_verification_status"],
            city=row["city"] or "Bangalore",
            rating=float(row["rating"]) if row["rating"] is not None else 5.0,
            status=row["status"],
            bag_deduction_balance_paise=int(
                row["bag_deduction_balance_paise"]
            ),
            onboarding_date=str(row["onboarding_date"]),
            created_at=(
                str(row["created_at"])
                if row["created_at"]
                else None
            ),
        )


# ==============================================================================
# Partner Validation
# ==============================================================================

def validate_partner_data(
    partner_id: str,
    partner_name: str,
    partner_type: str,
    category: str,
    onboarding_date: Union[date, str],
    pan: Optional[str] = None,
    pan_status: Optional[str] = None,
    phone: Optional[str] = None,
    bank_account_number: Optional[str] = None,
    ifsc_code: Optional[str] = None,
    bank_verification_status: str = "PENDING",
    city: Optional[str] = "Bangalore",
    rating: float = 5.0,
    status: str = "ACTIVE",
    bag_deduction_balance_paise: int = config.BAG_TOTAL_AMOUNT_PAISE,
) -> Dict[str, Any]:
    """Validate and normalize partner registration data."""

    # 1. Partner ID
    if not isinstance(partner_id, str) or not partner_id.strip():
        raise PartnerValidationError("partner_id cannot be empty.")

    norm_partner_id = partner_id.strip()

    # 2. Partner Name
    if not isinstance(partner_name, str) or not partner_name.strip():
        raise PartnerValidationError("partner_name cannot be empty.")

    norm_partner_name = partner_name.strip()

    # 3. Partner Type
    norm_partner_type = str(partner_type).strip().upper()

    if norm_partner_type not in config.PARTNER_TYPES:
        raise PartnerValidationError(
            f"Invalid partner_type '{partner_type}'. "
            f"Allowed values: {config.PARTNER_TYPES}"
        )

    # 4. Category
    norm_category = str(category).strip().upper()

    if norm_category not in config.CATEGORIES:
        raise PartnerValidationError(
            f"Invalid category '{category}'. "
            f"Allowed values: {config.CATEGORIES}"
        )

    # 5. Onboarding Date
    if isinstance(onboarding_date, datetime):
        norm_onboarding_date = onboarding_date.date().isoformat()

    elif isinstance(onboarding_date, date):
        norm_onboarding_date = onboarding_date.isoformat()

    elif isinstance(onboarding_date, str) and onboarding_date.strip():
        date_str = onboarding_date.strip()

        try:
            parsed_date = datetime.strptime(
                date_str, "%Y-%m-%d"
            ).date()

            norm_onboarding_date = parsed_date.isoformat()

        except ValueError:
            raise PartnerValidationError(
                f"Invalid onboarding_date '{onboarding_date}'. "
                "Expected format: YYYY-MM-DD."
            )

    else:
        raise PartnerValidationError(
            "onboarding_date is required and must be in YYYY-MM-DD format."
        )

    # 6. PAN and PAN Status
    norm_pan = None

    if pan is not None and str(pan).strip():
        norm_pan = str(pan).strip().upper()

    if norm_pan is None:
        if (
            pan_status is not None
            and str(pan_status).strip().upper() != "MISSING"
        ):
            raise PartnerValidationError(
                f"pan_status cannot be '{pan_status}' when PAN is missing. "
                "Must be 'MISSING'."
            )

        norm_pan_status = "MISSING"

    else:
        is_format_valid = bool(PAN_REGEX.fullmatch(norm_pan))

        if pan_status is not None:
            explicit_status = str(pan_status).strip().upper()

            if explicit_status not in config.PAN_STATUSES:
                raise PartnerValidationError(
                    f"Invalid pan_status '{pan_status}'. "
                    f"Allowed values: {config.PAN_STATUSES}"
                )

            if explicit_status == "MISSING":
                raise PartnerValidationError(
                    "pan_status cannot be 'MISSING' when a PAN is provided."
                )

            if explicit_status == "VALID" and not is_format_valid:
                raise PartnerValidationError(
                    f"PAN '{norm_pan}' has invalid format and "
                    "cannot have pan_status 'VALID'."
                )

            norm_pan_status = explicit_status

        else:
            norm_pan_status = (
                "VALID" if is_format_valid else "INVALID"
            )

    # 7. Phone
    norm_phone = None

    if phone is not None and str(phone).strip():
        cleaned_phone = str(phone).strip()

        if not PHONE_REGEX.fullmatch(cleaned_phone):
            raise PartnerValidationError(
                f"Invalid phone number '{phone}'. "
                "Must be a 10-digit number."
            )

        norm_phone = cleaned_phone

    # 8. Bank Account Number
    norm_bank_account = None

    if bank_account_number is not None and str(bank_account_number).strip():
        norm_bank_account = str(bank_account_number).strip()

    # 9. IFSC Code
    norm_ifsc = None

    if ifsc_code is not None and str(ifsc_code).strip():
        cleaned_ifsc = str(ifsc_code).strip().upper()

        if not IFSC_REGEX.fullmatch(cleaned_ifsc):
            raise PartnerValidationError(
                f"Invalid IFSC code '{ifsc_code}'. "
                "Must match standard 11-char format "
                "(e.g. HDFC0001234)."
            )

        norm_ifsc = cleaned_ifsc

    # 10. Bank Verification Status
    norm_bank_status = (
        str(bank_verification_status).strip().upper()
        if bank_verification_status
        else "PENDING"
    )

    if norm_bank_status not in config.BANK_VERIFICATION_STATUSES:
        raise PartnerValidationError(
            f"Invalid bank_verification_status "
            f"'{bank_verification_status}'. "
            f"Allowed values: {config.BANK_VERIFICATION_STATUSES}"
        )

    # 11. City
    norm_city = (
        str(city).strip()
        if city and str(city).strip()
        else "Bangalore"
    )

    # 12. Rating
    try:
        norm_rating = float(rating)

        if (
            not math.isfinite(norm_rating)
            or not 1.0 <= norm_rating <= 5.0
        ):
            raise PartnerValidationError(
                f"Rating must be between 1.0 and 5.0, got: {rating}"
            )

    except (ValueError, TypeError):
        raise PartnerValidationError(
            f"Rating must be a numeric value between 1.0 and 5.0, "
            f"got: {rating}"
        )

    # 13. Partner Status
    norm_status = (
        str(status).strip().upper()
        if status
        else "ACTIVE"
    )

    if norm_status not in config.PARTNER_STATUSES:
        raise PartnerValidationError(
            f"Invalid status '{status}'. "
            f"Allowed values: {config.PARTNER_STATUSES}"
        )

    # 14. Bag Deduction Balance
    if (
        isinstance(bag_deduction_balance_paise, bool)
        or not isinstance(bag_deduction_balance_paise, int)
        or bag_deduction_balance_paise < 0
    ):
        raise PartnerValidationError(
            "bag_deduction_balance_paise must be a non-negative integer."
        )

    norm_bag_balance = bag_deduction_balance_paise

    return {
        "partner_id": norm_partner_id,
        "partner_name": norm_partner_name,
        "partner_type": norm_partner_type,
        "pan": norm_pan,
        "pan_status": norm_pan_status,
        "category": norm_category,
        "phone": norm_phone,
        "bank_account_number": norm_bank_account,
        "ifsc_code": norm_ifsc,
        "bank_verification_status": norm_bank_status,
        "city": norm_city,
        "rating": norm_rating,
        "status": norm_status,
        "bag_deduction_balance_paise": norm_bag_balance,
        "onboarding_date": norm_onboarding_date,
    }


# ==============================================================================
# Registration and Lookup Services
# ==============================================================================

def register_partner(
    partner_id: str,
    partner_name: str,
    partner_type: str,
    category: str,
    onboarding_date: Union[date, str],
    pan: Optional[str] = None,
    pan_status: Optional[str] = None,
    phone: Optional[str] = None,
    bank_account_number: Optional[str] = None,
    ifsc_code: Optional[str] = None,
    bank_verification_status: str = "PENDING",
    city: Optional[str] = "Bangalore",
    rating: float = 5.0,
    status: str = "ACTIVE",
    bag_deduction_balance_paise: int = config.BAG_TOTAL_AMOUNT_PAISE,
    db_path: Optional[Union[str, Any]] = None,
) -> Partner:
    """Validate and register a new partner in SQLite."""

    validated = validate_partner_data(
        partner_id=partner_id,
        partner_name=partner_name,
        partner_type=partner_type,
        category=category,
        onboarding_date=onboarding_date,
        pan=pan,
        pan_status=pan_status,
        phone=phone,
        bank_account_number=bank_account_number,
        ifsc_code=ifsc_code,
        bank_verification_status=bank_verification_status,
        city=city,
        rating=rating,
        status=status,
        bag_deduction_balance_paise=bag_deduction_balance_paise,
    )

    with db_session(db_path) as conn:
        cursor = conn.cursor()

        # Check duplicate partner ID
        cursor.execute(
            "SELECT partner_id FROM partners WHERE partner_id = ?;",
            (validated["partner_id"],),
        )

        if cursor.fetchone():
            raise DuplicatePartnerError(
                f"Partner with ID '{validated['partner_id']}' "
                "is already registered."
            )

        # Check duplicate PAN
        if validated["pan"] is not None:
            cursor.execute(
                "SELECT partner_id FROM partners WHERE pan = ?;",
                (validated["pan"],),
            )

            existing_pan_row = cursor.fetchone()

            if existing_pan_row:
                raise DuplicatePANError(
                    f"Partner with PAN '{validated['pan']}' "
                    f"is already registered "
                    f"(partner_id: '{existing_pan_row['partner_id']}')."
                )

        # Insert partner
        insert_sql = """
        INSERT INTO partners (
            partner_id,
            partner_name,
            partner_type,
            pan,
            pan_status,
            category,
            phone,
            bank_account_number,
            ifsc_code,
            bank_verification_status,
            city,
            rating,
            status,
            bag_deduction_balance_paise,
            onboarding_date
        )
        VALUES (
            :partner_id,
            :partner_name,
            :partner_type,
            :pan,
            :pan_status,
            :category,
            :phone,
            :bank_account_number,
            :ifsc_code,
            :bank_verification_status,
            :city,
            :rating,
            :status,
            :bag_deduction_balance_paise,
            :onboarding_date
        );
        """

        cursor.execute(insert_sql, validated)

    # Retrieve newly registered partner
    partner = get_partner(
        validated["partner_id"],
        db_path=db_path
    )

    if partner is None:
        raise DatabaseError(
            f"Failed to retrieve partner "
            f"'{validated['partner_id']}' after registration."
        )

    return partner


def get_partner(
    partner_id: str,
    db_path: Optional[Union[str, Any]] = None
) -> Optional[Partner]:
    """Retrieve a partner using partner ID."""

    conn = get_db_connection(db_path)

    try:
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM partners WHERE partner_id = ?;",
            (partner_id,),
        )

        row = cursor.fetchone()

        if row:
            return Partner.from_row(row)

        return None

    finally:
        conn.close()


def list_partners(
    db_path: Optional[Union[str, Any]] = None
) -> List[Partner]:
    """Retrieve all registered partners."""

    conn = get_db_connection(db_path)

    try:
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT * FROM partners
            ORDER BY onboarding_date ASC, partner_id ASC;
            """
        )

        rows = cursor.fetchall()

        return [
            Partner.from_row(row)
            for row in rows
        ]

    finally:
        conn.close()
