from __future__ import annotations

import os
import socket
import time
from pathlib import Path

from src.jobcontroller.api import submit
from src.jobqueue.api import claim_next_job, mark_job_done, mark_job_failed, mark_job_pending, recover_stale_jobs
from src.runtime.api import load_runtime_config


def _worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def run_once(project_root: Path) -> bool:
    cfg = load_runtime_config(project_root)
    worker_id = _worker_id()
    queue_kwargs = {
        "processing_ttl_s": cfg.queue_processing_ttl_s,
        "claim_lock_ttl_s": cfg.queue_claim_lock_ttl_s,
        "max_attempts": cfg.queue_max_attempts,
    }
    recover_stale_jobs(
        str(project_root),
        cfg.queue_processing_ttl_s,
        claim_lock_ttl_s=cfg.queue_claim_lock_ttl_s,
    )
    job = claim_next_job(str(project_root), worker_id, **queue_kwargs)
    if job is None:
        return False

    lock_kwargs = {"claim_lock_ttl_s": cfg.queue_claim_lock_ttl_s}
    try:
        res = submit(
            job.pdf_path,
            str(project_root),
            output_mode=cfg.output_mode,
            sqlite_path=cfg.sqlite_path,
            lock_ttl_s=cfg.pipeline_lock_ttl_s,
            sqlite_busy_timeout_ms=cfg.sqlite_busy_timeout_ms,
            sqlite_retry_count=cfg.sqlite_retry_count,
            sqlite_retry_sleep_s=cfg.sqlite_retry_sleep_s,
            device_id=cfg.device_id,
        )
    except Exception as e:
        mark_job_failed(
            str(project_root),
            job.job_id,
            f"worker_submit_error: {e}",
            worker_id=worker_id,
            **lock_kwargs,
        )
        return True

    if res.status == "DONE":
        mark_job_done(str(project_root), job.job_id, worker_id=worker_id, **lock_kwargs)
    elif res.status == "FAILED":
        mark_job_failed(
            str(project_root),
            job.job_id,
            str(res.details.get("error", "unknown_error")),
            worker_id=worker_id,
            **lock_kwargs,
        )
    elif res.status == "SKIPPED" and str(res.details.get("reason", "")) == "already_done":
        mark_job_done(str(project_root), job.job_id, worker_id=worker_id, **lock_kwargs)
    else:
        reason = str(res.details.get("reason", "deferred"))
        mark_job_pending(
            str(project_root),
            job.job_id,
            f"deferred:{reason}",
            worker_id=worker_id,
            **lock_kwargs,
        )
    return True


def run_forever(project_root: Path) -> None:
    cfg = load_runtime_config(project_root)
    print(f"[worker] started | output_mode={cfg.output_mode} | sqlite={cfg.sqlite_path}")
    while True:
        processed = run_once(project_root)
        if not processed:
            time.sleep(cfg.worker_poll_interval_s)


def main() -> None:
    project_root = Path(__file__).resolve().parents[2]
    if os.getenv("ARE_WORKER_ONCE", "").strip() == "1":
        processed = run_once(project_root)
        print("[worker] processed_one_job" if processed else "[worker] no_pending_jobs")
        return
    run_forever(project_root)
