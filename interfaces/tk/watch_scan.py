from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from src.testui.api import normalize_file_row_key

DEFAULT_EXCLUDED_DIR_NAMES = frozenset(
    {"processed", "failed", "duplicates", "duplicate", "archive", "_archive"}
)


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


def _normalized_excluded_dir_names(excluded_dir_names: set[str] | None) -> set[str]:
    names = DEFAULT_EXCLUDED_DIR_NAMES if excluded_dir_names is None else excluded_dir_names
    return {name.casefold() for name in names}


def _iter_watch_pdf_files(
    watch_path: Path,
    *,
    recursive: bool,
    excluded_dir_names: set[str] | None = None,
) -> Iterator[Path]:
    excluded = _normalized_excluded_dir_names(excluded_dir_names)

    if not recursive:
        try:
            entries = sorted(watch_path.iterdir(), key=lambda p: p.name.lower())
        except OSError:
            return
        for entry in entries:
            if entry.suffix.lower() != ".pdf":
                continue
            try:
                if entry.is_file():
                    yield entry
            except OSError:
                continue
        return

    def walk(current: Path) -> Iterator[Path]:
        try:
            entries = sorted(current.iterdir(), key=lambda p: p.name.lower())
        except OSError:
            return
        for entry in entries:
            try:
                if entry.is_dir():
                    if entry.is_symlink():
                        continue
                    if entry.name.casefold() in excluded:
                        continue
                    yield from walk(entry)
                    continue
                if entry.suffix.lower() == ".pdf" and entry.is_file():
                    yield entry
            except OSError:
                continue

    yield from walk(watch_path)


def list_watch_pdf_paths(
    watch_dir: str | Path,
    *,
    recursive: bool = False,
    excluded_dir_names: set[str] | None = None,
) -> list[str]:
    watch_path = Path(watch_dir)
    if not watch_path.exists() or not watch_path.is_dir():
        return []

    paths: list[str] = []
    for entry in _iter_watch_pdf_files(
        watch_path,
        recursive=recursive,
        excluded_dir_names=excluded_dir_names,
    ):
        try:
            paths.append(str(entry.resolve(strict=False)))
        except OSError:
            continue
    return sorted(paths, key=str.casefold)


class InAppWatchScanner:
    def __init__(self) -> None:
        self._observations: dict[str, _Observation] = {}

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
        known_keys = {normalize_file_row_key(path) for path in known_paths if path}
        watch_path = Path(watch_dir)

        if not watch_path.exists():
            self._observations.clear()
            return WatchScanResult([], 0, len(known_keys), f"watch_dir_missing: {watch_path}")
        if not watch_path.is_dir():
            self._observations.clear()
            return WatchScanResult([], 0, len(known_keys), f"watch_dir_not_directory: {watch_path}")

        stable_paths: list[str] = []
        current_keys: set[str] = set()
        observed_count = 0

        try:
            pdf_entries = list(
                _iter_watch_pdf_files(
                    watch_path,
                    recursive=recursive,
                    excluded_dir_names=excluded_dir_names,
                )
            )
        except OSError as e:
            self._observations.clear()
            return WatchScanResult([], 0, len(known_keys), f"watch_dir_unreadable: {watch_path} ({e})")

        for entry in pdf_entries:
            try:
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
