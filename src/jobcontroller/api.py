from __future__ import annotations

from .jobcontroller import JobController
from .model import JobResult

__all__ = ["JobResult", "submit"]



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
