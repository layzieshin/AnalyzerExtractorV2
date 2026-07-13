from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from src.testui.api import normalize_file_row_key


@dataclass(frozen=True)
class WatchScanResult:
    stable_new_paths: list[str]
    observed_count: int
    known_count: int
    warning: str = ""


@dataclass(frozen=True)
class _Observation:
    size: int
    mtime: float
    observed_at: float


class InAppWatchScanner:
    def __init__(self) -> None:
        self._observations: dict[str, _Observation] = {}

    def scan(
        self,
        watch_dir: str | Path,
        known_paths: set[str],
        stable_window_s: float,
        now: float | None = None,
    ) -> WatchScanResult:
        current_time = time.time() if now is None else now
        known_keys = {normalize_file_row_key(path) for path in known_paths if path}
        watch_path = Path(watch_dir)

        if not watch_path.exists():
            self._observations.clear()
            return WatchScanResult([], 0, len(known_keys), f"watch_dir_missing: {watch_path}")
        if not watch_path.is_dir():
            self._observations.clear()
            return WatchScanResult([], 0, len(known_keys), f"watch_dir_not_directory: {watch_path}")

        try:
            entries = sorted(watch_path.iterdir(), key=lambda p: p.name.lower())
        except OSError as e:
            self._observations.clear()
            return WatchScanResult([], 0, len(known_keys), f"watch_dir_unreadable: {watch_path} ({e})")

        stable_paths: list[str] = []
        current_keys: set[str] = set()
        observed_count = 0

        for entry in entries:
            if entry.suffix.lower() != ".pdf":
                continue
            try:
                if not entry.is_file():
                    continue
                stat = entry.stat()
            except OSError:
                continue

            key = normalize_file_row_key(entry)
            if not key:
                continue
            current_keys.add(key)
            observed_count += 1

            if key in known_keys:
                continue

            if stable_window_s <= 0:
                stable_paths.append(str(entry.resolve(strict=False)))
                continue

            previous = self._observations.get(key)
            current = _Observation(stat.st_size, stat.st_mtime, current_time)
            if previous is None or previous.size != stat.st_size or previous.mtime != stat.st_mtime:
                self._observations[key] = current
                continue

            if current_time - previous.observed_at >= stable_window_s:
                stable_paths.append(str(entry.resolve(strict=False)))

        self._observations = {
            key: observation
            for key, observation in self._observations.items()
            if key in current_keys and key not in known_keys
        }
        return WatchScanResult(stable_paths, observed_count, len(known_keys))
