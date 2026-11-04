"""
Partner CSV Ingestion Module
Project: T118-PS-060
Member 1: Payout and Earnings Module

This module implements:
- Batch reading and parsing of partner records from CSV files.
- Row-by-row validation using the domain Partner model.
- Safe insertion into the SQLite database with transaction safety.
- Detection of duplicate partner IDs and duplicate non-null PAN values.
- Graceful error handling (errors on a single row do NOT abort the batch).
- Detailed import summary with row numbers, error categories, and diagnostics.
"""

import csv
from dataclasses import asdict, dataclass, field
import io
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import config
from src.models.partner import (
    DuplicatePANError,
    DuplicatePartnerError,
    Partner,
    PartnerValidationError,
    register_partner,
)


# ==============================================================================
# Summary and Error Data Classes
# ==============================================================================
@dataclass
class PartnerImportRowError:
    """Represents a failure encountered during row processing."""
    row_number: int                          # 1-based CSV line number
    partner_id: Optional[str]                # Partner ID from row if available
    error_type: str                          # 'VALIDATION_ERROR', 'DUPLICATE_PARTNER_ID', 'DUPLICATE_PAN', 'CSV_FORMAT_ERROR'
    message: str                             # Descriptive reason for the failure
    raw_data: Optional[Dict[str, Any]] = None  # Original row data for debugging

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PartnerImportSummary:
    """Summary of batch partner CSV import results."""
    total_rows_processed: int = 0
    successful_imports: int = 0
    failed_rows: int = 0
    duplicate_records: int = 0
    validation_errors: int = 0
    errors: List[PartnerImportRowError] = field(default_factory=list)
    imported_partner_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_rows_processed": self.total_rows_processed,
            "successful_imports": self.successful_imports,
            "failed_rows": self.failed_rows,
            "duplicate_records": self.duplicate_records,
            "validation_errors": self.validation_errors,
            "errors": [err.to_dict() for err in self.errors],
            "imported_partner_ids": self.imported_partner_ids,
        }

    def report(self) -> str:
        """Generates a formatted human-readable summary report."""
        lines = [
            "==================================================",
            "        PARTNER CSV IMPORT SUMMARY REPORT         ",
            "==================================================",
            f"Total Rows Processed : {self.total_rows_processed}",
            f"Successfully Imported: {self.successful_imports}",
            f"Failed Rows          : {self.failed_rows}",
            f"  - Duplicate Records: {self.duplicate_records}",
            f"  - Validation Errors: {self.validation_errors}",
            "--------------------------------------------------",
        ]
        if self.errors:
            lines.append("FAILURE DETAILS:")
            for err in self.errors:
                pid = err.partner_id or "N/A"
                lines.append(f"  [Row {err.row_number}] Partner '{pid}' | {err.error_type}: {err.message}")
        else:
            lines.append("All rows were imported successfully without errors.")
        lines.append("==================================================")
        return "\n".join(lines)


# ==============================================================================
# CSV Ingestion Engine
# ==============================================================================
def import_partners_from_csv(
    csv_source: Union[str, Path, io.TextIOBase],
    db_path: Optional[Union[str, Path]] = None,
) -> PartnerImportSummary:
    """
    Reads, validates, and imports partner onboarding records from a CSV file.

    Features:
    - Accepts a file path or an open text stream (e.g. StringIO for tests).
    - Normalizes header names (ignores leading/trailing whitespace, case, and BOM).
    - Validates every row using the Partner domain rules.
    - Captures duplicate partner IDs and duplicate PAN numbers without crashing the entire import.
    - Handles missing or invalid PAN values according to PS-060 rules.
    - Handles unverified or missing bank details gracefully.
    - Generates a PartnerImportSummary with row-level diagnostics.

    :param csv_source: File path (str, Path) or text stream (TextIOBase).
    :param db_path: Optional database path; defaults to config.DATABASE_PATH.
    :return: PartnerImportSummary object.
    """
    summary = PartnerImportSummary()

    # Determine if input is a path or an existing text stream
    opened_file = None
    if isinstance(csv_source, (str, Path)):
        file_path = Path(csv_source)
        if not file_path.exists():
            summary.errors.append(
                PartnerImportRowError(
                    row_number=0,
                    partner_id=None,
                    error_type="FILE_NOT_FOUND",
                    message=f"CSV file not found at path: {file_path}",
                )
            )
            return summary
        opened_file = open(file_path, "r", encoding="utf-8-sig")
        file_stream = opened_file
    elif isinstance(csv_source, io.TextIOBase):
        file_stream = csv_source
    else:
        summary.errors.append(
            PartnerImportRowError(
                row_number=0,
                partner_id=None,
                error_type="INVALID_SOURCE",
                message=f"Unsupported csv_source type: {type(csv_source)}",
            )
        )
        return summary

    try:
        reader = csv.DictReader(file_stream)
        if reader.fieldnames is None:
            summary.errors.append(
                PartnerImportRowError(
                    row_number=0,
                    partner_id=None,
                    error_type="CSV_FORMAT_ERROR",
                    message="CSV file is empty or missing header row.",
                )
            )
            return summary

        # Normalize header keys: stripped and lowercased mapping
        field_map = {name.strip().lower(): name for name in reader.fieldnames if name}

        # Check for absolute minimal required header columns
        required_headers = ["partner_id", "partner_name", "partner_type", "category", "onboarding_date"]
        missing_headers = [h for h in required_headers if h not in field_map]
        if missing_headers:
            summary.errors.append(
                PartnerImportRowError(
                    row_number=1,
                    partner_id=None,
                    error_type="CSV_FORMAT_ERROR",
                    message=f"CSV header is missing mandatory columns: {missing_headers}",
                )
            )
            return summary

        # Process data rows
        for row in reader:
            summary.total_rows_processed += 1
            row_num = reader.line_num

            # Helper to extract value by normalized field name
            def get_val(key: str, default: Any = None) -> Any:
                orig_key = field_map.get(key)
                if orig_key is not None:
                    val = row.get(orig_key)
                    if val is not None and str(val).strip():
                        return str(val).strip()
                return default

            partner_id = get_val("partner_id")
            partner_name = get_val("partner_name")
            partner_type = get_val("partner_type")
            category = get_val("category")
            onboarding_date = get_val("onboarding_date")
            pan = get_val("pan")
            pan_status = get_val("pan_status")
            phone = get_val("phone")
            bank_account_number = get_val("bank_account_number") or get_val("account_number")
            ifsc_code = get_val("ifsc_code") or get_val("ifsc")
            bank_verification_status = get_val("bank_verification_status", "PENDING")
            city = get_val("city", "Bangalore")
            rating = float(get_val("rating", 5.0))
            status = get_val("status", "ACTIVE")

            bag_balance_raw = get_val("bag_deduction_balance_paise") or get_val("bag_balance_paise")
            if bag_balance_raw is not None:
                try:
                    bag_deduction_balance_paise = int(bag_balance_raw)
                except ValueError:
                    bag_deduction_balance_paise = config.BAG_TOTAL_AMOUNT_PAISE
            else:
                bag_deduction_balance_paise = config.BAG_TOTAL_AMOUNT_PAISE

            # Check for extra unmapped columns in the row (malformed row with excess columns)
            if None in row and row[None]:
                summary.failed_rows += 1
                summary.validation_errors += 1
                summary.errors.append(
                    PartnerImportRowError(
                        row_number=row_num,
                        partner_id=partner_id,
                        error_type="VALIDATION_ERROR",
                        message=f"Malformed row: contains extra unexpected columns ({row[None]}).",
                        raw_data=dict(row),
                    )
                )
                continue

            # Attempt registration of the individual row
            try:
                registered = register_partner(
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
                    db_path=db_path,
                )
                summary.successful_imports += 1
                summary.imported_partner_ids.append(registered.partner_id)

            except DuplicatePartnerError as e:
                summary.failed_rows += 1
                summary.duplicate_records += 1
                summary.errors.append(
                    PartnerImportRowError(
                        row_number=row_num,
                        partner_id=partner_id,
                        error_type="DUPLICATE_PARTNER_ID",
                        message=str(e),
                        raw_data=dict(row),
                    )
                )

            except DuplicatePANError as e:
                summary.failed_rows += 1
                summary.duplicate_records += 1
                summary.errors.append(
                    PartnerImportRowError(
                        row_number=row_num,
                        partner_id=partner_id,
                        error_type="DUPLICATE_PAN",
                        message=str(e),
                        raw_data=dict(row),
                    )
                )

            except PartnerValidationError as e:
                summary.failed_rows += 1
                summary.validation_errors += 1
                summary.errors.append(
                    PartnerImportRowError(
                        row_number=row_num,
                        partner_id=partner_id,
                        error_type="VALIDATION_ERROR",
                        message=str(e),
                        raw_data=dict(row),
                    )
                )

            except Exception as e:
                summary.failed_rows += 1
                summary.errors.append(
                    PartnerImportRowError(
                        row_number=row_num,
                        partner_id=partner_id,
                        error_type="UNEXPECTED_ERROR",
                        message=f"Unexpected error: {e}",
                        raw_data=dict(row),
                    )
                )

    finally:
        if opened_file is not None:
            opened_file.close()

    return summary
