from __future__ import annotations

from typing import List

from .model import QueueJob
from .queue import JobQueue

__all__ = [
    "QueueJob",
    "claim_next_job",
    "enqueue_pdf_job",
    "list_jobs",
    "mark_job_done",
    "mark_job_failed",
    "mark_job_pending",
    "recover_stale_jobs",
    "retry_failed_job",
]


def _queue(
    processing_ttl_s: float | None = None,
    claim_lock_ttl_s: float | None = None,
    max_attempts: int | None = None,
) -> JobQueue:
    kwargs: dict[str, float | int] = {}
    if processing_ttl_s is not None:
        kwargs["processing_ttl_s"] = processing_ttl_s
    if claim_lock_ttl_s is not None:
        kwargs["claim_lock_ttl_s"] = claim_lock_ttl_s
    if max_attempts is not None:
        kwargs["max_attempts"] = max_attempts
    return JobQueue(**kwargs)


def enqueue_pdf_job(
    project_root: str,
    pdf_path: str,
    source: str = "watchdog",
    *,
    claim_lock_ttl_s: float | None = None,
    max_attempts: int | None = None,
) -> QueueJob:
    return _queue(claim_lock_ttl_s=claim_lock_ttl_s, max_attempts=max_attempts).enqueue_pdf_job(
        project_root, pdf_path, source
    )


def claim_next_job(
    project_root: str,
    worker_id: str,
    *,
    processing_ttl_s: float | None = None,
    claim_lock_ttl_s: float | None = None,
    max_attempts: int | None = None,
) -> QueueJob | None:
    return _queue(
        processing_ttl_s=processing_ttl_s,
        claim_lock_ttl_s=claim_lock_ttl_s,
        max_attempts=max_attempts,
    ).claim_next_job(project_root, worker_id)


def mark_job_done(
    project_root: str,
    job_id: str,
    worker_id: str = "",
    *,
    claim_lock_ttl_s: float | None = None,
) -> QueueJob:
    return _queue(claim_lock_ttl_s=claim_lock_ttl_s).mark_job_done(
        project_root, job_id, worker_id=worker_id
    )


def mark_job_failed(
    project_root: str,
    job_id: str,
    error: str,
    worker_id: str = "",
    *,
    claim_lock_ttl_s: float | None = None,
) -> QueueJob:
    return _queue(claim_lock_ttl_s=claim_lock_ttl_s).mark_job_failed(
        project_root, job_id, error, worker_id=worker_id
    )


def mark_job_pending(
    project_root: str,
    job_id: str,
    reason: str,
    worker_id: str = "",
    *,
    claim_lock_ttl_s: float | None = None,
) -> QueueJob:
    return _queue(claim_lock_ttl_s=claim_lock_ttl_s).mark_job_pending(
        project_root, job_id, reason, worker_id=worker_id
    )


def retry_failed_job(
    project_root: str,
    job_id: str,
    reason: str = "retry_requested",
    worker_id: str = "",
    *,
    claim_lock_ttl_s: float | None = None,
) -> QueueJob:
    return _queue(claim_lock_ttl_s=claim_lock_ttl_s).retry_failed_job(
        project_root, job_id, reason=reason, worker_id=worker_id
    )


def recover_stale_jobs(
    project_root: str,
    processing_ttl_s: float = 300.0,
    *,
    claim_lock_ttl_s: float | None = None,
) -> int:
    return _queue(
        processing_ttl_s=processing_ttl_s,
        claim_lock_ttl_s=claim_lock_ttl_s,
    ).recover_stale_jobs(project_root, processing_ttl_s)


def list_jobs(project_root: str) -> List[QueueJob]:
    return JobQueue().list_jobs(project_root)
