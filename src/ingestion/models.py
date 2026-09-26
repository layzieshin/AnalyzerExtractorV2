from __future__ import annotations

from dataclasses import dataclass, field

SCHEMA_VERSION = 1

SOURCE_MANUAL = "manual"
SOURCE_WATCH_FOLDER = "watch_folder"

PROC_REGISTERED = "REGISTERED"
PROC_PENDING = "PENDING"
PROC_PROCESSING = "PROCESSING"
PROC_DONE = "DONE"
PROC_FAILED = "FAILED"

ARCH_NOT_REQUIRED = "NOT_REQUIRED"
ARCH_PENDING = "PENDING"
ARCH_MOVING = "MOVING"
ARCH_ARCHIVED = "ARCHIVED"
ARCH_FAILED = "ARCHIVE_FAILED"
ARCH_RECOVERY_REQUIRED = "RECOVERY_REQUIRED"

PATH_RESOLVED = "resolved"
PATH_LEGACY = "legacy_fallback"
PATH_AMBIGUOUS = "ambiguous"


@dataclass(frozen=True)
class ImportRecord:
    schema_version: int
    ingestion_id: str
    source_kind: str
    original_path: str
    current_path: str
    content_sha256: str
    processing_job_id: str
    watch_input_path: str
    watch_backup_path: str
    discovered_at_utc: str
    updated_at_utc: str
    processing_status: str
    archive_status: str
    file_fingerprint: str
    file_size: int
    file_mtime_ns: int
    planned_archive_path: str = ""
    archive_target: str = ""
    archived_at_utc: str = ""
    last_error: str = ""
    archive_error: str = ""


@dataclass(frozen=True)
class StablePdfObservation:
    path: str
    size: int
    mtime_ns: int
    content_sha256: str


@dataclass(frozen=True)
class WatchScanOutcome:
    pdf_path: str
    outcome: str
    message: str = ""
    ingestion_id: str = ""
    job_id: str = ""


@dataclass(frozen=True)
class WatchCycleResult:
    enabled: bool
    disabled_reason: str = ""
    recovery_count: int = 0
    scanned_count: int = 0
    outcomes: tuple[WatchScanOutcome, ...] = ()
    busy: bool = False


@dataclass(frozen=True)
class RegisterImportResult:
    record: ImportRecord
    created: bool
    enqueued: bool
    queue_status: str = ""
    message: str = ""


@dataclass(frozen=True)
class PathResolution:
    source_pdf_path: str
    current_pdf_path: str
    ingestion_id: str
    path_status: str


@dataclass
class StabilityScannerState:
    observations: dict[str, tuple[int, int, float]] = field(default_factory=dict)
