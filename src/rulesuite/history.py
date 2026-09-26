"""Bytegenaue Snapshots einer bestehenden aktiven Rule vor dem Ueberschreiben.

Phase 5 publiziert nur die Kopie unter ``rules/history/``. Inventar, Restore und
UI gehoeren nicht hierher.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .errors import RuleSuiteError


class _SnapshotCollision(Exception):
    pass


def snapshot_existing_active_ruleset(active_path: Path) -> Path:
    """Kopiert ``active_path`` bytegenau nach ``rules/history/``.

    Die Zieldatei wird erst nach verifizierter Temp-Kopie publiziert. Jeder
    Fehler bricht ab, ohne die aktive Datei zu aendern. Temp-Dateien werden
    bestmoeglich entfernt.
    """
    source = Path(active_path)
    payload = _read_source_bytes(source)
    history_dir = _ensure_history_dir(source.parent / "history")
    stamp = _utc_stamp()
    stem = source.stem
    if not stem or stem in {".", ".."}:
        raise RuleSuiteError(f"snapshot_invalid_stem: {source.name}")

    for attempt in range(1, 10001):
        final = history_dir / _history_name(stem, stamp, attempt)
        if final.exists():
            continue
        tmp = history_dir / f".{final.name}.{uuid4().hex}.tmp"
        published = False
        try:
            _write_temp_bytes(tmp, payload)
            _verify_snapshot_bytes(tmp, payload, stage="verify")
            _publish_snapshot(tmp, final)
            published = True
            _verify_snapshot_bytes(final, payload, stage="publish_verify")
            return final
        except _SnapshotCollision:
            continue
        except RuleSuiteError:
            if published:
                _best_effort_remove(final)
            raise
        finally:
            _best_effort_remove(tmp)
    raise RuleSuiteError("snapshot_name_exhausted")


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _history_name(stem: str, stamp: str, attempt: int) -> str:
    if attempt == 1:
        return f"{stem}-{stamp}.json"
    return f"{stem}-{stamp}-{attempt}.json"


def _read_source_bytes(path: Path) -> bytes:
    try:
        if not path.is_file():
            raise RuleSuiteError(f"snapshot_read_failed: {path}")
        return path.read_bytes()
    except RuleSuiteError:
        raise
    except OSError as exc:
        raise RuleSuiteError(f"snapshot_read_failed: {path}: {exc}") from exc


def _ensure_history_dir(path: Path) -> Path:
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RuleSuiteError(f"snapshot_mkdir_failed: {path}: {exc}") from exc
    if not path.is_dir():
        raise RuleSuiteError(f"snapshot_mkdir_failed: {path}")
    return path


def _write_temp_bytes(path: Path, payload: bytes) -> None:
    try:
        with path.open("wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise RuleSuiteError(f"snapshot_write_failed: {path}: {exc}") from exc


def _verify_snapshot_bytes(path: Path, payload: bytes, *, stage: str) -> None:
    code = "snapshot_verify_failed" if stage == "verify" else "snapshot_publish_verify_failed"
    try:
        actual = path.read_bytes()
    except OSError as exc:
        raise RuleSuiteError(f"{code}: {path}: {exc}") from exc
    if actual != payload:
        raise RuleSuiteError(f"{code}: {path}")


def _publish_snapshot(tmp: Path, final: Path) -> None:
    if final.exists():
        raise _SnapshotCollision()
    try:
        os.link(tmp, final)
        return
    except FileExistsError as exc:
        raise _SnapshotCollision() from exc
    except OSError as link_error:
        if final.exists():
            raise _SnapshotCollision() from link_error
        try:
            os.replace(tmp, final)
        except OSError as exc:
            _best_effort_remove(final)
            raise RuleSuiteError(f"snapshot_publish_failed: {final}: {exc}") from exc


def _best_effort_remove(path: Path) -> None:
    try:
        if path.is_file() or path.is_symlink():
            path.unlink()
    except OSError:
        return
