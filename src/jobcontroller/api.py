from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .jobcontroller import JobController
from .model import JobResult

__all__ = [
    "JobDiagnosticSources",
    "JobEvidence",
    "JobResult",
    "get_job_diagnostic_sources",
    "get_job_evidence",
    "release_validated_run",
    "retry_excel_export",
    "submit",
]


@dataclass(frozen=True)
class JobEvidence:
    job_id: str
    pdf_path: str
    status: str
    error: str
    steps: tuple[dict[str, Any], ...]
    normalized_dump_path: str
    block_dump_paths: tuple[tuple[str, str], ...]
    state_path: str
    state_available: bool
    context_text: str = ""
    context_truncated: bool = False
    context_available: bool = False
    context_source_label: str = ""
    context_source_kind: str = ""
    retry_kind: str = ""


@dataclass(frozen=True)
class JobDiagnosticSources:
    job_id: str
    normalized_text: str
    block_texts: tuple[tuple[str, str], ...]



def submit(
    pdf_path: str,
    project_root: str,
    output_mode: str = "both",
    sqlite_path: str | None = None,
    lock_ttl_s: float | None = None,
    sqlite_busy_timeout_ms: int = 5000,
    sqlite_retry_count: int = 3,
    sqlite_retry_sleep_s: float = 0.2,
    device_id: str | None = None,
) -> JobResult:
    """Public API (JobController)

    Contract:
    - job_id = sha256(file_bytes)[:16]
    - lock file under locks/<job_id>.lock (create-exclusive)
    - state file under jobs/<job_id>.json
    - serial pipeline
    - output_mode: both|excel|sqlite (default both)
    """
    return JobController().submit(
        pdf_path,
        project_root,
        output_mode=output_mode,
        sqlite_path=sqlite_path,
        lock_ttl_s=lock_ttl_s,
        sqlite_busy_timeout_ms=sqlite_busy_timeout_ms,
        sqlite_retry_count=sqlite_retry_count,
        sqlite_retry_sleep_s=sqlite_retry_sleep_s,
        device_id=device_id,
    )


def get_job_evidence(project_root: str | Path, job_id: str) -> JobEvidence | None:
    """Read-only job-state/evidence boundary for application diagnosis DTOs."""
    return JobController().read_job_evidence(project_root, job_id)


def get_job_diagnostic_sources(project_root: str | Path, job_id: str) -> JobDiagnosticSources | None:
    """Return full validated job diagnostic texts for owner-side discovery."""
    return JobController().read_job_diagnostic_sources(project_root, job_id)


def release_validated_run(
    project_root: str | Path,
    job_id: str,
    run_id: int,
    *,
    operator_initials: str,
    validated_at_utc: str,
    validation_id: int,
    correction: bool = False,
) -> JobResult:
    return JobController().release_validated_run(
        project_root,
        job_id,
        run_id,
        operator_initials=operator_initials,
        validated_at_utc=validated_at_utc,
        validation_id=validation_id,
        correction=correction,
    )


def retry_excel_export(project_root: str | Path, job_id: str) -> JobResult:
    return JobController().retry_excel_export_by_job_id(project_root, job_id)
