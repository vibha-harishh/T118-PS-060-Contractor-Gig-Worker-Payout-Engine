"""
Task Event CSV Ingestion Module
Project: T118-PS-060
Member 1: Payout and Earnings Module

This module implements:
- Batch reading and parsing of delivery and service task events from CSV files.
- Row-by-row validation using the domain Task model.
- Validation that the referenced partner exists in the database.
- Safe insertion into the SQLite database with transaction safety.
- Detection of duplicate task IDs and foreign key violations.
- Graceful error handling (errors on a single row do NOT abort the batch).
- Detailed import summary with row numbers, error categories, and diagnostics.
"""

import csv
from dataclasses import asdict, dataclass, field
import io
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import config
from src.models.partner import PartnerNotFoundError
from src.models.task import (
    DuplicateTaskError,
    Task,
    TaskValidationError,
    record_task,
)


# ==============================================================================
# Summary and Error Data Classes
# ==============================================================================
@dataclass
class TaskImportRowError:
    """Represents a failure encountered during task row processing."""
    row_number: int                          # 1-based CSV line number
    task_id: Optional[str]                   # Task ID if extractable
    error_type: str                          # 'VALIDATION_ERROR', 'DUPLICATE_TASK_ID', 'PARTNER_NOT_FOUND', 'CSV_FORMAT_ERROR'
    message: str                             # Descriptive reason for the failure
    raw_data: Optional[Dict[str, Any]] = None  # Original row data for debugging

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TaskImportSummary:
    """Summary of batch task CSV import results."""
    total_rows_processed: int = 0
    successful_imports: int = 0
    failed_rows: int = 0
    duplicate_records: int = 0
    partner_not_found_errors: int = 0
    validation_errors: int = 0
    errors: List[TaskImportRowError] = field(default_factory=list)
    imported_task_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_rows_processed": self.total_rows_processed,
            "successful_imports": self.successful_imports,
            "failed_rows": self.failed_rows,
            "duplicate_records": self.duplicate_records,
            "partner_not_found_errors": self.partner_not_found_errors,
            "validation_errors": self.validation_errors,
            "errors": [err.to_dict() for err in self.errors],
            "imported_task_ids": self.imported_task_ids,
        }

    def report(self) -> str:
        """Generates a formatted human-readable summary report."""
        lines = [
            "==================================================",
            "          TASK CSV IMPORT SUMMARY REPORT          ",
            "==================================================",
            f"Total Rows Processed     : {self.total_rows_processed}",
            f"Successfully Imported    : {self.successful_imports}",
            f"Failed Rows              : {self.failed_rows}",
            f"  - Duplicate Records    : {self.duplicate_records}",
            f"  - Partner Not Found    : {self.partner_not_found_errors}",
            f"  - Validation Errors    : {self.validation_errors}",
            "--------------------------------------------------",
        ]
        if self.errors:
            lines.append("FAILURE DETAILS:")
            for err in self.errors:
                tid = err.task_id or "N/A"
                lines.append(f"  [Row {err.row_number}] Task '{tid}' | {err.error_type}: {err.message}")
        else:
            lines.append("All task event rows were imported successfully without errors.")
        lines.append("==================================================")
        return "\n".join(lines)


# ==============================================================================
# CSV Ingestion Engine
# ==============================================================================
def import_tasks_from_csv(
    csv_source: Union[str, Path, io.TextIOBase],
    db_path: Optional[Union[str, Path]] = None,
) -> TaskImportSummary:
    """
    Reads, validates, and imports task events from a CSV file or text stream.

    Features:
    - Accepts file path (str, Path) or open stream (TextIOBase).
    - Normalizes header names (ignores whitespace, case, BOM).
    - Validates mandatory columns: task_id, partner_id, event_type, distance_km, task_timestamp.
    - Validates that the partner exists in the database.
    - Validates distance >= 0, duration >= 0, rating in [1.0, 5.0], and surge flags.
    - Converts event timestamps to IST and computes the ISO week identifier.
    - Catches duplicate task IDs, missing partners, and validation errors per row.
    - Does NOT stop the entire import because of individual row failures.

    :param csv_source: File path or stream.
    :param db_path: Optional SQLite database path.
    :return: TaskImportSummary object.
    """
    summary = TaskImportSummary()

    # Determine input type
    opened_file = None
    if isinstance(csv_source, (str, Path)):
        file_path = Path(csv_source)
        if not file_path.exists():
            summary.errors.append(
                TaskImportRowError(
                    row_number=0,
                    task_id=None,
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
            TaskImportRowError(
                row_number=0,
                task_id=None,
                error_type="INVALID_SOURCE",
                message=f"Unsupported csv_source type: {type(csv_source)}",
            )
        )
        return summary

    try:
        reader = csv.DictReader(file_stream)
        if reader.fieldnames is None:
            summary.errors.append(
                TaskImportRowError(
                    row_number=0,
                    task_id=None,
                    error_type="CSV_FORMAT_ERROR",
                    message="CSV file is empty or missing header row.",
                )
            )
            return summary

        # Normalized header map: stripped & lowercased
        field_map = {
            name.strip().lstrip("\ufeff").lower(): name
            for name in reader.fieldnames
            if name
        }

        # Check for mandatory headers
        mandatory_headers = ["task_id", "partner_id", "event_type", "distance_km", "task_timestamp"]
        missing_headers = [h for h in mandatory_headers if h not in field_map]
        if missing_headers:
            summary.errors.append(
                TaskImportRowError(
                    row_number=1,
                    task_id=None,
                    error_type="CSV_FORMAT_ERROR",
                    message=f"CSV header is missing mandatory columns: {missing_headers}",
                )
            )
            return summary

        # Process rows
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

            task_id = get_val("task_id")

            # Check for extra unmapped columns in the row
            if None in row and row[None]:
                summary.failed_rows += 1
                summary.validation_errors += 1
                summary.errors.append(
                    TaskImportRowError(
                        row_number=row_num,
                        task_id=task_id,
                        error_type="VALIDATION_ERROR",
                        message=f"Malformed row: contains extra unexpected columns ({row[None]}).",
                        raw_data=dict(row),
                    )
                )
                continue

            partner_id = get_val("partner_id")
            event_type = get_val("event_type")
            distance_km = get_val("distance_km")
            task_timestamp = get_val("task_timestamp")
            duration_minutes = get_val("duration_minutes", 0.0)
            task_type = get_val("task_type", "DELIVERY")
            slot_type = get_val("slot_type", "REGULAR")
            is_slot_surge = get_val("is_slot_surge", 0)
            is_rain_surge = get_val("is_rain_surge", 0)
            rating = get_val("rating")
            cancellation_reason = get_val("cancellation_reason")

            # Attempt to record task
            try:
                task = record_task(
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
                    db_path=db_path,
                )
                summary.successful_imports += 1
                summary.imported_task_ids.append(task.task_id)

            except DuplicateTaskError as e:
                summary.failed_rows += 1
                summary.duplicate_records += 1
                summary.errors.append(
                    TaskImportRowError(
                        row_number=row_num,
                        task_id=task_id,
                        error_type="DUPLICATE_TASK_ID",
                        message=str(e),
                        raw_data=dict(row),
                    )
                )

            except PartnerNotFoundError as e:
                summary.failed_rows += 1
                summary.partner_not_found_errors += 1
                summary.errors.append(
                    TaskImportRowError(
                        row_number=row_num,
                        task_id=task_id,
                        error_type="PARTNER_NOT_FOUND",
                        message=str(e),
                        raw_data=dict(row),
                    )
                )

            except TaskValidationError as e:
                summary.failed_rows += 1
                summary.validation_errors += 1
                summary.errors.append(
                    TaskImportRowError(
                        row_number=row_num,
                        task_id=task_id,
                        error_type="VALIDATION_ERROR",
                        message=str(e),
                        raw_data=dict(row),
                    )
                )

            except Exception as e:
                summary.failed_rows += 1
                summary.errors.append(
                    TaskImportRowError(
                        row_number=row_num,
                        task_id=task_id,
                        error_type="UNEXPECTED_ERROR",
                        message=f"Unexpected error: {e}",
                        raw_data=dict(row),
                    )
                )

    finally:
        if opened_file is not None:
            opened_file.close()

    return summary
