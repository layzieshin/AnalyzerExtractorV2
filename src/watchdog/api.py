from __future__ import annotations

from typing import List

from src.jobqueue.api import QueueJob

from .service import WatchdogService


def scan_watch_once(
    project_root: str,
    watch_dir: str,
    stable_window_s: float = 1.0,
    *,
    watch_backup_path: str = "",
) -> List[QueueJob]:
    return WatchdogService(
        project_root=project_root,
        watch_dir=watch_dir,
        scan_interval_s=0.0,
        stable_window_s=stable_window_s,
        watch_backup_path=watch_backup_path,
    ).scan_once()


def run_watchdog_forever(
    project_root: str,
    watch_dir: str,
    scan_interval_s: float = 3.0,
    stable_window_s: float = 1.0,
    *,
    watch_backup_path: str = "",
) -> None:
    WatchdogService(
        project_root=project_root,
        watch_dir=watch_dir,
        scan_interval_s=scan_interval_s,
        stable_window_s=stable_window_s,
        watch_backup_path=watch_backup_path,
    ).run_forever()
