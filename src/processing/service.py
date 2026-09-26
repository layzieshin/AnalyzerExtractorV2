from __future__ import annotations

import os
import socket
from pathlib import Path
from typing import Any, Callable

from src.jobcontroller.api import submit
from src.jobqueue.api import (
    claim_next_job,
    enqueue_pdf_job,
    list_jobs,
    mark_job_done,
    mark_job_failed,
    mark_job_pending,
    recover_stale_jobs,
    retry_failed_job,
    verify_job_content_sha256,
)
from src.ingestion.api import mark_source_changed_failure, reconcile_processing_for_job
from src.runtime.api import load_runtime_config

from .models import ProcessingConfig, ProcessingJob, ProcessingResult

SubmitFunc = Callable[..., Any]


def default_worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def config_from_runtime_defaults(project_root: str | Path) -> ProcessingConfig:
    cfg = load_runtime_config(project_root)
    return ProcessingConfig(
        output_mode=cfg.output_mode,
        sqlite_path=cfg.sqlite_path,
        device_id=cfg.device_id,
        queue_processing_ttl_s=cfg.queue_processing_ttl_s,
        queue_claim_lock_ttl_s=cfg.queue_claim_lock_ttl_s,
        queue_max_attempts=cfg.queue_max_attempts,
        pipeline_lock_ttl_s=cfg.pipeline_lock_ttl_s,
        sqlite_busy_timeout_ms=cfg.sqlite_busy_timeout_ms,
        sqlite_retry_count=cfg.sqlite_retry_count,
        sqlite_retry_sleep_s=cfg.sqlite_retry_sleep_s,
    )


def _as_processing_job(job: object) -> ProcessingJob:
    return ProcessingJob(
        job_id=job.job_id,
        pdf_path=job.pdf_path,
        status=job.status,
        created_at=job.created_at,
        updated_at=job.updated_at,
        source=job.source,
        worker_id=job.worker_id,
        attempts=job.attempts,
        last_error=job.last_error,
    )


def enqueue_pdf(
    project_root: str | Path,
    pdf_path: str,
    *,
    source: str = "watchdog",
    expected_sha256: str | None = None,
) -> ProcessingJob:
    job = enqueue_pdf_job(
        str(project_root),
        pdf_path,
        source=source,
        expected_sha256=expected_sha256,
    )
    return _as_processing_job(job)


def list_processing_jobs(project_root: str | Path) -> list[ProcessingJob]:
    return [_as_processing_job(job) for job in list_jobs(str(project_root))]


def retry_failed(
    project_root: str | Path,
    job_id: str,
    *,
    reason: str = "retry_requested",
    worker_id: str = "",
) -> ProcessingJob:
    job = retry_failed_job(str(project_root), job_id, reason=reason, worker_id=worker_id)
    return _as_processing_job(job)


def process_next_pending(
    project_root: str | Path,
    config: ProcessingConfig,
    *,
    worker_id: str | None = None,
    submit_func: SubmitFunc | None = None,
) -> ProcessingResult:
    root = Path(project_root)
    wid = worker_id or default_worker_id()
    effective_submit = submit_func if submit_func is not None else submit
    queue_kwargs = {
        "processing_ttl_s": config.queue_processing_ttl_s,
        "claim_lock_ttl_s": config.queue_claim_lock_ttl_s,
        "max_attempts": config.queue_max_attempts,
    }
    recover_stale_jobs(
        str(root),
        config.queue_processing_ttl_s,
        claim_lock_ttl_s=config.queue_claim_lock_ttl_s,
    )
    job = claim_next_job(str(root), wid, **queue_kwargs)
    if job is None:
        return ProcessingResult(processed=False, message="no_pending_jobs")

    lock_kwargs = {"claim_lock_ttl_s": config.queue_claim_lock_ttl_s}
    try:
        verify_job_content_sha256(str(root), job.job_id, **lock_kwargs)
    except Exception as e:
        marked = mark_job_failed(
            str(root),
            job.job_id,
            str(e),
            worker_id=wid,
            **lock_kwargs,
        )
        mark_source_changed_failure(str(root), job.job_id, job.pdf_path)
        return ProcessingResult(
            processed=True,
            job_id=job.job_id,
            pdf_path=job.pdf_path,
            queue_status=marked.status,
            submit_status="FAILED",
            message=marked.last_error,
        )
    try:
        res = effective_submit(
            job.pdf_path,
            str(root),
            output_mode=config.output_mode,
            sqlite_path=config.sqlite_path,
            lock_ttl_s=config.pipeline_lock_ttl_s,
            sqlite_busy_timeout_ms=config.sqlite_busy_timeout_ms,
            sqlite_retry_count=config.sqlite_retry_count,
            sqlite_retry_sleep_s=config.sqlite_retry_sleep_s,
            device_id=config.device_id,
        )
    except Exception as e:
        marked = mark_job_failed(
            str(root),
            job.job_id,
            f"worker_submit_error: {e}",
            worker_id=wid,
            **lock_kwargs,
        )
        reconcile_processing_for_job(str(root), job.job_id, marked.status, error=marked.last_error)
        return ProcessingResult(
            processed=True,
            job_id=job.job_id,
            pdf_path=job.pdf_path,
            queue_status=marked.status,
            submit_status="FAILED",
            message=marked.last_error,
        )

    submit_status = str(getattr(res, "status", ""))
    details = getattr(res, "details", None)
    detail_map = details if isinstance(details, dict) else {}

    if submit_status == "DONE":
        marked = mark_job_done(str(root), job.job_id, worker_id=wid, **lock_kwargs)
    elif submit_status == "FAILED":
        marked = mark_job_failed(
            str(root),
            job.job_id,
            str(detail_map.get("error", "unknown_error")),
            worker_id=wid,
            **lock_kwargs,
        )
    elif submit_status == "SKIPPED" and str(detail_map.get("reason", "")) == "already_done":
        marked = mark_job_done(str(root), job.job_id, worker_id=wid, **lock_kwargs)
    else:
        reason = str(detail_map.get("reason", "deferred"))
        marked = mark_job_pending(
            str(root),
            job.job_id,
            f"deferred:{reason}",
            worker_id=wid,
            **lock_kwargs,
        )

    reconcile_processing_for_job(str(root), job.job_id, marked.status, error=marked.last_error)

    return ProcessingResult(
        processed=True,
        job_id=job.job_id,
        pdf_path=job.pdf_path,
        queue_status=marked.status,
        submit_status=submit_status,
        message=marked.last_error,
    )
