from __future__ import annotations

import os
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from src.jobcontroller.api import submit
from src.jobqueue.api import claim_next_job, mark_job_done, mark_job_failed, mark_job_pending, recover_stale_jobs


@dataclass(frozen=True)
class QueueWorkerConfig:
    output_mode: str = "both"
    sqlite_path: str | None = None
    device_id: str | None = None
    queue_processing_ttl_s: float = 300.0
    queue_claim_lock_ttl_s: float = 120.0
    queue_max_attempts: int = 5
    pipeline_lock_ttl_s: float = 900.0
    sqlite_busy_timeout_ms: int = 5000
    sqlite_retry_count: int = 3
    sqlite_retry_sleep_s: float = 0.2


@dataclass(frozen=True)
class QueueWorkerResult:
    processed: bool
    job_id: str = ""
    pdf_path: str = ""
    queue_status: str = ""
    submit_status: str = ""
    message: str = ""


SubmitFunc = Callable[..., Any]


def default_worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def process_next_pending(
    project_root: str | Path,
    config: QueueWorkerConfig,
    *,
    worker_id: str | None = None,
    submit_func: SubmitFunc = submit,
) -> QueueWorkerResult:
    root = Path(project_root)
    wid = worker_id or default_worker_id()
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
        return QueueWorkerResult(processed=False, message="no_pending_jobs")

    lock_kwargs = {"claim_lock_ttl_s": config.queue_claim_lock_ttl_s}
    try:
        res = submit_func(
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
        return QueueWorkerResult(
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

    return QueueWorkerResult(
        processed=True,
        job_id=job.job_id,
        pdf_path=job.pdf_path,
        queue_status=marked.status,
        submit_status=submit_status,
        message=marked.last_error,
    )
