from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


VALID_OUTPUT_MODES = {"both", "excel", "sqlite"}


@dataclass(frozen=True)
class RuntimeConfig:
    output_mode: str = "both"
    sqlite_path: str | None = None
    watch_dir: str | None = None
    device_id: str | None = None
    scan_interval_s: float = 3.0
    watch_stable_window_s: float = 1.0
    worker_poll_interval_s: float = 2.0
    queue_processing_ttl_s: float = 300.0
    queue_claim_lock_ttl_s: float = 120.0
    queue_max_attempts: int = 5
    pipeline_lock_ttl_s: float = 900.0
    sqlite_busy_timeout_ms: int = 5000
    sqlite_retry_count: int = 3
    sqlite_retry_sleep_s: float = 0.2

    @property
    def enable_excel(self) -> bool:
        return self.output_mode in ("both", "excel")

    @property
    def enable_sqlite(self) -> bool:
        return self.output_mode in ("both", "sqlite")


def load_runtime_config(project_root: str | Path) -> RuntimeConfig:
    root = Path(project_root)
    output_mode = os.getenv("ARE_OUTPUT_MODE", "both").strip().lower()
    if output_mode not in VALID_OUTPUT_MODES:
        output_mode = "both"

    sqlite_path = os.getenv("ARE_SQLITE_PATH", "").strip() or str(root / "output" / "final" / "results.sqlite3")
    watch_dir = os.getenv("ARE_WATCH_DIR", "").strip() or str(root / "input" / "watch")
    device_id = os.getenv("ARE_DEVICE_ID", "").strip() or None

    scan_interval = _read_float_env("ARE_SCAN_INTERVAL_S", 3.0)
    watch_stable_window = _read_float_env("ARE_WATCH_STABLE_WINDOW_S", 1.0)
    worker_poll_interval = _read_float_env("ARE_WORKER_POLL_INTERVAL_S", 2.0)
    queue_processing_ttl = _read_float_env("ARE_QUEUE_PROCESSING_TTL_S", 300.0)
    queue_claim_lock_ttl = _read_float_env("ARE_QUEUE_CLAIM_LOCK_TTL_S", 120.0)
    queue_max_attempts = _read_int_env("ARE_QUEUE_MAX_ATTEMPTS", 5)
    pipeline_lock_ttl = _read_float_env("ARE_PIPELINE_LOCK_TTL_S", 900.0)
    sqlite_busy_timeout_ms = _read_int_env("ARE_SQLITE_BUSY_TIMEOUT_MS", 5000)
    sqlite_retry_count = _read_int_env("ARE_SQLITE_RETRY_COUNT", 3)
    sqlite_retry_sleep = _read_float_env("ARE_SQLITE_RETRY_SLEEP_S", 0.2)
    return RuntimeConfig(
        output_mode=output_mode,
        sqlite_path=sqlite_path,
        watch_dir=watch_dir,
        device_id=device_id,
        scan_interval_s=scan_interval,
        watch_stable_window_s=watch_stable_window,
        worker_poll_interval_s=worker_poll_interval,
        queue_processing_ttl_s=queue_processing_ttl,
        queue_claim_lock_ttl_s=queue_claim_lock_ttl,
        queue_max_attempts=queue_max_attempts,
        pipeline_lock_ttl_s=pipeline_lock_ttl,
        sqlite_busy_timeout_ms=sqlite_busy_timeout_ms,
        sqlite_retry_count=sqlite_retry_count,
        sqlite_retry_sleep_s=sqlite_retry_sleep,
    )


def _read_float_env(key: str, default: float) -> float:
    raw = os.getenv(key, "")
    try:
        return float(raw) if raw else default
    except ValueError:
        return default


def _read_int_env(key: str, default: int) -> int:
    raw = os.getenv(key, "")
    try:
        return int(raw) if raw else default
    except ValueError:
        return default
