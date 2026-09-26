from __future__ import annotations

import os
import time
from pathlib import Path

from interfaces.common.queue_worker import QueueWorkerConfig, default_worker_id, process_next_pending
from src.jobcontroller.api import submit
from src.runtime.api import load_runtime_config, resolve_app_root


def _project_root() -> Path:
    if os.getenv("ARE_HOME", "").strip():
        return resolve_app_root()
    return Path(__file__).resolve().parents[2]


def _worker_id() -> str:
    return default_worker_id()


def _worker_config_from_runtime(project_root: Path) -> QueueWorkerConfig:
    cfg = load_runtime_config(project_root)
    return QueueWorkerConfig(
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


def run_once(project_root: Path) -> bool:
    result = process_next_pending(
        project_root,
        _worker_config_from_runtime(project_root),
        worker_id=_worker_id(),
        submit_func=submit,
    )
    return result.processed


def run_forever(project_root: Path) -> None:
    cfg = load_runtime_config(project_root)
    print(f"[worker] started | output_mode={cfg.output_mode} | sqlite={cfg.sqlite_path}")
    while True:
        processed = run_once(project_root)
        if not processed:
            time.sleep(cfg.worker_poll_interval_s)


def main() -> None:
    project_root = _project_root()
    if os.getenv("ARE_WORKER_ONCE", "").strip() == "1":
        processed = run_once(project_root)
        print("[worker] processed_one_job" if processed else "[worker] no_pending_jobs")
        return
    run_forever(project_root)
