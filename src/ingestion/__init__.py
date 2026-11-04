"""
Ingestion package for batch CSV processing (Partners and Tasks).
"""

from .partner_loader import (
    PartnerImportRowError,
    PartnerImportSummary,
    import_partners_from_csv,
)

from .task_loader import (
    TaskImportRowError,
    TaskImportSummary,
    import_tasks_from_csv,
)

__all__ = [
    "PartnerImportRowError",
    "PartnerImportSummary",
    "import_partners_from_csv",
    "TaskImportRowError",
    "TaskImportSummary",
    "import_tasks_from_csv",
]
