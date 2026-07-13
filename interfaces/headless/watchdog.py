from __future__ import annotations

import os
from pathlib import Path

from src.runtime.api import load_runtime_config
from src.watchdog.api import run_watchdog_forever, scan_watch_once


def main() -> None:
    project_root = Path(__file__).resolve().parents[2]
    cfg = load_runtime_config(project_root)
    watch_dir = cfg.watch_dir or str(project_root / "input" / "watch")

    if os.getenv("ARE_WATCHDOG_ONCE", "").strip() == "1":
        created = scan_watch_once(str(project_root), watch_dir, stable_window_s=0)
        print(f"[watchdog] created_or_seen_jobs={len(created)}")
        return

    print(
        "[watchdog] started | "
        f"watch_dir={watch_dir} | "
        f"scan_interval_s={cfg.scan_interval_s} | "
        f"stable_window_s={cfg.watch_stable_window_s}"
    )
    run_watchdog_forever(
        str(project_root),
        watch_dir,
        scan_interval_s=cfg.scan_interval_s,
        stable_window_s=cfg.watch_stable_window_s,
    )
