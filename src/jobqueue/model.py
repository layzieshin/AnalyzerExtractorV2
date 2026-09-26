from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class QueueJob:
    job_id: str
    pdf_path: str
    status: str  # PENDING|PROCESSING|DONE|FAILED
    created_at: str
    updated_at: str
    source: str
    worker_id: str = ""
    attempts: int = 0
    last_error: str = ""
    content_sha256: str = ""
