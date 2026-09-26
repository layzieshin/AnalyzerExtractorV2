from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProcessingConfig:
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
class ProcessingResult:
    processed: bool
    job_id: str = ""
    pdf_path: str = ""
    queue_status: str = ""
    submit_status: str = ""
    message: str = ""


@dataclass(frozen=True)
class ProcessingJob:
    job_id: str
    pdf_path: str
    status: str
    created_at: str
    updated_at: str
    source: str
    worker_id: str = ""
    attempts: int = 0
    last_error: str = ""
