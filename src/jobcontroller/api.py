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
    "processing_eligibility_error",
    "reanalyze_run",
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
    output_mode: str = "sqlite",
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
    - output_mode: sqlite; legacy both|excel inputs normalize to sqlite
    - unknown output_mode returns FAILED before processing
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


def processing_eligibility_error(project_root: str | Path | None, job_id: str, *, require_evidence: bool = False) -> str:
    """Read-only completed-processing guard shared by result write owners.

    An absent legacy job is allowed only when no frozen source context claims
    its existence. A present failed/unfinished job or queue always blocks.
    """
    if not project_root or not str(job_id).strip():
        return ""
    from src.jobqueue.api import list_jobs

    evidence = get_job_evidence(project_root, job_id)
    if evidence is not None:
        if (evidence.state_available and evidence.status != "DONE") or (not evidence.state_available and (evidence.error or require_evidence)):
            return "Die urspruengliche Verarbeitung ist nicht erfolgreich abgeschlossen. Bitte Nacharbeit klaeren."
    elif require_evidence:
        return "Der urspruengliche Verarbeitungsnachweis fehlt. Bitte Nacharbeit klaeren."
    matching = [job for job in list_jobs(str(project_root), create_missing=False) if str(job.job_id) == str(job_id)]
    if any(job.status != "DONE" for job in matching):
        return "Die Verarbeitung steht noch nicht auf DONE. Bitte die Arbeitsliste klaeren."
    return ""


def reanalyze_run(project_root: str | Path, store_spec: dict[str, str], run_id: int, *,
                  expected_selection_token: str, request_id: str, operator_initials: str) -> dict[str, Any]:
    """Reanalyse exactly one unvalidated original source with a frozen active rule.

    PDF parse/extract runs in a bounded spawn child. This never rewrites a job,
    output plan or original result and never validates the resulting candidate.
    """
    from .reanalysis import reanalyze_run as _reanalyze_run

    return _reanalyze_run(project_root, store_spec, run_id,
        expected_selection_token=expected_selection_token, request_id=request_id, operator_initials=operator_initials)


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
    """Retired Excel compatibility call; never writes or releases output."""
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
    """Retired Excel compatibility call; never writes or retries output."""
    return JobController().retry_excel_export_by_job_id(project_root, job_id)
