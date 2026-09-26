from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from src.ingestion.api import (
    DEFAULT_EXCLUDED_DIR_NAMES as INGESTION_DEFAULT_EXCLUDED_DIR_NAMES,
    StabilityScannerState,
    list_watch_pdf_paths as ingestion_list_watch_pdf_paths,
    observe_stable_pdfs,
)

DEFAULT_EXCLUDED_DIR_NAMES = INGESTION_DEFAULT_EXCLUDED_DIR_NAMES


@dataclass(frozen=True)
class WatchScanResult:
    stable_new_paths: list[str]
    observed_count: int
    known_count: int
    warning: str = ""


class InAppWatchScanner:
    def __init__(self) -> None:
        self._state = StabilityScannerState()

    @property
    def _observations(self) -> dict[str, tuple[int, int, float]]:
        return self._state.observations

    def scan(
        self,
        watch_dir: str | Path,
        known_paths: set[str],
        stable_window_s: float,
        now: float | None = None,
        *,
        recursive: bool = False,
        excluded_dir_names: set[str] | None = None,
    ) -> WatchScanResult:
        current_time = time.time() if now is None else now
        known_keys = {path for path in known_paths if path}
        watch_path = Path(watch_dir)

        if not watch_path.exists():
            self._state.observations.clear()
            return WatchScanResult([], 0, len(known_keys), f"watch_dir_missing: {watch_path}")
        if not watch_path.is_dir():
            self._state.observations.clear()
            return WatchScanResult([], 0, len(known_keys), f"watch_dir_not_directory: {watch_path}")

        try:
            listed = ingestion_list_watch_pdf_paths(
                watch_path,
                recursive=recursive,
                excluded_dir_names=excluded_dir_names,
            )
        except OSError as exc:
            self._state.observations.clear()
            return WatchScanResult([], 0, len(known_keys), f"watch_dir_unreadable: {watch_path} ({exc})")

        observed_count = len(listed)
        stable_paths = [
            str(Path(path).resolve(strict=False))
            for path in observe_stable_pdfs(
                watch_path,
                stable_window_s=stable_window_s,
                state=self._state,
                now=current_time,
                known_paths=known_keys,
                recursive=recursive,
                excluded_dir_names=excluded_dir_names,
            )
        ]
        return WatchScanResult(stable_paths, observed_count, len(known_keys))


def list_watch_pdf_paths(
    watch_dir: str | Path,
    *,
    recursive: bool = False,
    excluded_dir_names: set[str] | None = None,
) -> list[str]:
    return ingestion_list_watch_pdf_paths(
        watch_dir,
        recursive=recursive,
        excluded_dir_names=excluded_dir_names,
    )
