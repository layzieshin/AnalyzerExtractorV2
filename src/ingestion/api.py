from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from src.jobqueue.api import QueueJob

from .models import (
    ImportRecord,
    PathResolution,
    RegisterImportResult,
    SOURCE_MANUAL,
    SOURCE_WATCH_FOLDER,
    StabilityScannerState,
    WatchCycleResult,
)
from .service import (
    DEFAULT_EXCLUDED_DIR_NAMES,
    IngestionError,
    compute_content_sha256,
    hash_stable_pdf,
    list_watch_pdf_paths,
    list_watch_pdfs,
    mark_source_changed_failure,
    maybe_archive_record,
    normalize_watch_path_key,
    observe_stable_pdfs,
    reconcile_archive_recovery,
    reconcile_processing_for_job,
    register_import,
    resolve_current_path,
    retry_archive,
    run_watch_scan_cycle,
    validate_watch_path_pair,
)
from .store import get_record, list_records

EnqueueCallable = Callable[[str, str, str | None], QueueJob]

__all__ = [
    "EnqueueCallable",
    "ImportRecord",
    "IngestionError",
    "PathResolution",
    "RegisterImportResult",
    "SOURCE_MANUAL",
    "SOURCE_WATCH_FOLDER",
    "StabilityScannerState",
    "WatchCycleResult",
    "DEFAULT_EXCLUDED_DIR_NAMES",
    "compute_content_sha256",
    "get_import_record",
    "hash_stable_pdf",
    "list_import_records",
    "list_watch_pdf_paths",
    "list_watch_pdfs",
    "normalize_watch_path_key",
    "mark_source_changed_failure",
    "maybe_archive_record",
    "observe_stable_pdfs",
    "reconcile_archive_recovery",
    "reconcile_processing_for_job",
    "register_import",
    "resolve_current_path",
    "retry_archive",
    "run_watch_scan_cycle",
    "validate_watch_path_pair",
]


def get_import_record(project_root: str | Path, ingestion_id: str) -> ImportRecord | None:
    return get_record(project_root, ingestion_id)


def list_import_records(project_root: str | Path) -> list[ImportRecord]:
    return list_records(project_root)
