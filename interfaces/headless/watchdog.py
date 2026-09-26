from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from src.application.api import ApplicationWatchError, SettingsValidationError, create_desktop_services
from src.runtime.api import load_runtime_config, resolve_app_root


def _project_root() -> Path:
    if os.getenv("ARE_HOME", "").strip():
        return resolve_app_root()
    return Path(__file__).resolve().parents[2]


def main() -> None:
    project_root = _project_root()
    cfg = load_runtime_config(project_root)
    try:
        services = create_desktop_services(project_root)
    except SettingsValidationError as exc:
        print(f"[watchdog] watch_cycle_error={exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    if os.getenv("ARE_WATCHDOG_ONCE", "").strip() == "1":
        try:
            stable_window_s = cfg.watch_stable_window_s
            if stable_window_s > 0:
                services.extraction.run_watch_cycle(stable_window_s=stable_window_s)
                time.sleep(stable_window_s)
            summary = services.extraction.run_watch_cycle(stable_window_s=stable_window_s)
        except ApplicationWatchError as exc:
            print(f"[watchdog] watch_cycle_error={exc}", file=sys.stderr)
            raise SystemExit(1) from exc
        if not summary.enabled:
            print(f"[watchdog] watch_disabled reason={summary.disabled_reason}")
            return
        if summary.busy:
            print("[watchdog] watch_cycle_busy=1")
            return
        print(
            "[watchdog] watch_cycle_complete | "
            f"recovery={summary.recovery_count} | "
            f"scanned={summary.scanned_count} | "
            f"outcomes={len(summary.outcomes)}"
        )
        return

    print(
        "[watchdog] started | "
        f"scan_interval_s={cfg.scan_interval_s} | "
        f"stable_window_s={cfg.watch_stable_window_s}"
    )
    while True:
        try:
            summary = services.extraction.run_watch_cycle(stable_window_s=cfg.watch_stable_window_s)
            if summary.enabled and not summary.busy:
                print(
                    "[watchdog] cycle | "
                    f"recovery={summary.recovery_count} | "
                    f"scanned={summary.scanned_count} | "
                    f"outcomes={len(summary.outcomes)}"
                )
        except ApplicationWatchError as exc:
            print(f"[watchdog] watch_cycle_error={exc}", file=sys.stderr)
        time.sleep(cfg.scan_interval_s)
