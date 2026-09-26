from __future__ import annotations

import hashlib
import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.runtime.api import release_exclusive, try_acquire_exclusive

from .models import (
    ARCH_ARCHIVED,
    ARCH_FAILED,
    ARCH_MOVING,
    ARCH_NOT_REQUIRED,
    ARCH_PENDING,
    ARCH_RECOVERY_REQUIRED,
    ImportRecord,
    PROC_DONE,
    PROC_FAILED,
    PROC_PENDING,
    PROC_PROCESSING,
    PROC_REGISTERED,
    SCHEMA_VERSION,
    SOURCE_MANUAL,
    SOURCE_WATCH_FOLDER,
)

_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")

VALID_PROCESSING = {PROC_REGISTERED, PROC_PENDING, PROC_PROCESSING, PROC_DONE, PROC_FAILED}
VALID_ARCHIVE = {
    ARCH_NOT_REQUIRED,
    ARCH_PENDING,
    ARCH_MOVING,
    ARCH_ARCHIVED,
    ARCH_FAILED,
    ARCH_RECOVERY_REQUIRED,
}


class IngestionStoreError(RuntimeError):
    pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ingestion_dir(project_root: str | Path) -> Path:
    return Path(project_root).resolve() / "storage" / "ingestion"


def _record_path(project_root: str | Path, ingestion_id: str) -> Path:
    return ingestion_dir(project_root) / f"{ingestion_id}.json"


def _lock_path(project_root: str | Path, ingestion_id: str) -> Path:
    return ingestion_dir(project_root) / "locks" / f"{ingestion_id}.lock"


def _registration_lock_path(project_root: str | Path, fingerprint: str) -> Path:
    digest = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:32]
    return ingestion_dir(project_root) / "locks" / f"register-{digest}.lock"


def record_to_dict(record: ImportRecord) -> dict[str, Any]:
    return {
        "schema_version": record.schema_version,
        "ingestion_id": record.ingestion_id,
        "source_kind": record.source_kind,
        "original_path": record.original_path,
        "current_path": record.current_path,
        "content_sha256": record.content_sha256,
        "processing_job_id": record.processing_job_id,
        "watch_input_path": record.watch_input_path,
        "watch_backup_path": record.watch_backup_path,
        "discovered_at_utc": record.discovered_at_utc,
        "updated_at_utc": record.updated_at_utc,
        "processing_status": record.processing_status,
        "archive_status": record.archive_status,
        "file_fingerprint": record.file_fingerprint,
        "file_size": record.file_size,
        "file_mtime_ns": record.file_mtime_ns,
        "planned_archive_path": record.planned_archive_path,
        "archive_target": record.archive_target,
        "archived_at_utc": record.archived_at_utc,
        "last_error": record.last_error,
        "archive_error": record.archive_error,
    }


def _validate_uuid(value: str, field: str) -> None:
    try:
        uuid.UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise IngestionStoreError(f"invalid_{field}: {value}") from exc


def _normalize_sha256(value: str, field: str = "content_sha256") -> str:
    text = str(value or "").strip().lower()
    if not _SHA256_HEX_RE.fullmatch(text):
        raise IngestionStoreError(f"invalid_{field}: {value}")
    return text


def record_from_dict(data: dict[str, Any]) -> ImportRecord:
    if int(data.get("schema_version", 0)) != SCHEMA_VERSION:
        raise IngestionStoreError(f"unsupported_schema_version: {data.get('schema_version')}")
    required = (
        "ingestion_id",
        "source_kind",
        "original_path",
        "current_path",
        "content_sha256",
        "processing_job_id",
        "discovered_at_utc",
        "updated_at_utc",
        "processing_status",
        "archive_status",
        "file_fingerprint",
        "file_size",
        "file_mtime_ns",
    )
    for key in required:
        if key not in data:
            raise IngestionStoreError(f"missing_field: {key}")

    source_kind = str(data["source_kind"])
    if source_kind not in {SOURCE_MANUAL, SOURCE_WATCH_FOLDER}:
        raise IngestionStoreError(f"invalid_source_kind: {source_kind}")

    processing_status = str(data["processing_status"])
    if processing_status not in VALID_PROCESSING:
        raise IngestionStoreError(f"invalid_processing_status: {processing_status}")

    archive_status = str(data["archive_status"])
    if archive_status not in VALID_ARCHIVE:
        raise IngestionStoreError(f"invalid_archive_status: {archive_status}")

    _validate_uuid(str(data["ingestion_id"]), "ingestion_id")
    processing_job_id = str(data["processing_job_id"]).strip()
    if not processing_job_id:
        raise IngestionStoreError("invalid_processing_job_id: empty")

    content_sha256 = _normalize_sha256(str(data["content_sha256"]))

    file_size = int(data["file_size"])
    file_mtime_ns = int(data["file_mtime_ns"])
    if file_size < 0:
        raise IngestionStoreError(f"invalid_file_size: {file_size}")
    if file_mtime_ns < 0:
        raise IngestionStoreError(f"invalid_file_mtime_ns: {file_mtime_ns}")

    original_path = str(data["original_path"]).strip()
    current_path = str(data["current_path"]).strip()
    if not original_path or not current_path:
        raise IngestionStoreError("invalid_path: empty")

    fingerprint = str(data["file_fingerprint"]).strip()
    if not fingerprint:
        raise IngestionStoreError("invalid_file_fingerprint: empty")

    return ImportRecord(
        schema_version=SCHEMA_VERSION,
        ingestion_id=str(data["ingestion_id"]),
        source_kind=source_kind,
        original_path=original_path,
        current_path=current_path,
        content_sha256=content_sha256,
        processing_job_id=processing_job_id,
        watch_input_path=str(data.get("watch_input_path") or ""),
        watch_backup_path=str(data.get("watch_backup_path") or ""),
        discovered_at_utc=str(data["discovered_at_utc"]),
        updated_at_utc=str(data["updated_at_utc"]),
        processing_status=processing_status,
        archive_status=archive_status,
        file_fingerprint=fingerprint,
        file_size=file_size,
        file_mtime_ns=file_mtime_ns,
        planned_archive_path=str(data.get("planned_archive_path") or ""),
        archive_target=str(data.get("archive_target") or ""),
        archived_at_utc=str(data.get("archived_at_utc") or ""),
        last_error=str(data.get("last_error") or ""),
        archive_error=str(data.get("archive_error") or ""),
    )


def compute_fingerprint(path: str | Path, *, size: int, mtime_ns: int, content_sha256: str) -> str:
    normalized = str(Path(path).resolve(strict=False))
    return f"{normalized}|{size}|{mtime_ns}|{content_sha256}"


def list_records(project_root: str | Path) -> list[ImportRecord]:
    root = ingestion_dir(project_root)
    if not root.is_dir():
        return []
    records: list[ImportRecord] = []
    for path in sorted(root.glob("*.json")):
        records.append(load_record_file(path))
    return records


def load_record_file(path: Path) -> ImportRecord:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IngestionStoreError(f"corrupt_record: {path.name}: {exc}") from exc
    if not isinstance(data, dict):
        raise IngestionStoreError(f"corrupt_record: {path.name}: root must be object")
    return record_from_dict(data)


def get_record(project_root: str | Path, ingestion_id: str) -> ImportRecord | None:
    path = _record_path(project_root, ingestion_id)
    if not path.is_file():
        return None
    return load_record_file(path)


def find_by_fingerprint(project_root: str | Path, fingerprint: str) -> ImportRecord | None:
    for record in list_records(project_root):
        if record.file_fingerprint == fingerprint:
            return record
    return None


def find_by_job_and_original_path(
    project_root: str | Path,
    job_id: str,
    original_path: str,
) -> list[ImportRecord]:
    normalized = str(Path(original_path).resolve(strict=False))
    matches = []
    for record in list_records(project_root):
        if record.processing_job_id != job_id:
            continue
        if str(Path(record.original_path).resolve(strict=False)) != normalized:
            continue
        matches.append(record)
    return matches


def _persist_record(project_root: str | Path, record: ImportRecord) -> ImportRecord:
    root = ingestion_dir(project_root)
    root.mkdir(parents=True, exist_ok=True)
    path = _record_path(project_root, record.ingestion_id)
    payload = json.dumps(record_to_dict(record), indent=2, ensure_ascii=False) + "\n"
    tmp = path.with_suffix(path.suffix + f".{uuid.uuid4().hex}.tmp")
    try:
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, path)
    except OSError as exc:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        raise IngestionStoreError(f"record_save_failed: {exc}") from exc
    return record


def save_record(
    project_root: str | Path,
    record: ImportRecord,
    *,
    lock_held: bool = False,
) -> ImportRecord:
    lock_path = _lock_path(project_root, record.ingestion_id)
    if lock_held:
        return _persist_record(project_root, record)
    root = ingestion_dir(project_root)
    root.mkdir(parents=True, exist_ok=True)
    (root / "locks").mkdir(parents=True, exist_ok=True)
    if not try_acquire_exclusive(lock_path, 120.0):
        raise IngestionStoreError(f"record_locked: {record.ingestion_id}")
    try:
        return _persist_record(project_root, record)
    finally:
        release_exclusive(lock_path)


def acquire_registration_lock(
    project_root: str | Path,
    fingerprint: str,
    *,
    timeout_s: float = 120.0,
) -> Path:
    root = ingestion_dir(project_root)
    root.mkdir(parents=True, exist_ok=True)
    (root / "locks").mkdir(parents=True, exist_ok=True)
    lock_path = _registration_lock_path(project_root, fingerprint)
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if try_acquire_exclusive(lock_path, timeout_s):
            return lock_path
        time.sleep(0.01)
    raise IngestionStoreError(f"registration_locked: {fingerprint}")


def release_registration_lock(lock_path: Path) -> None:
    release_exclusive(lock_path)


def create_record(
    *,
    source_kind: str,
    original_path: str,
    content_sha256: str,
    processing_job_id: str,
    file_size: int,
    file_mtime_ns: int,
    watch_input_path: str = "",
    watch_backup_path: str = "",
    archive_status: str | None = None,
) -> ImportRecord:
    now = _now_iso()
    resolved = str(Path(original_path).resolve(strict=False))
    fingerprint = compute_fingerprint(
        resolved,
        size=file_size,
        mtime_ns=file_mtime_ns,
        content_sha256=content_sha256,
    )
    if archive_status is None:
        archive_status = ARCH_NOT_REQUIRED if source_kind == SOURCE_MANUAL else ARCH_PENDING
    return ImportRecord(
        schema_version=SCHEMA_VERSION,
        ingestion_id=str(uuid.uuid4()),
        source_kind=source_kind,
        original_path=resolved,
        current_path=resolved,
        content_sha256=content_sha256,
        processing_job_id=processing_job_id,
        watch_input_path=watch_input_path,
        watch_backup_path=watch_backup_path,
        discovered_at_utc=now,
        updated_at_utc=now,
        processing_status=PROC_REGISTERED,
        archive_status=archive_status,
        file_fingerprint=fingerprint,
        file_size=file_size,
        file_mtime_ns=file_mtime_ns,
    )


def update_record(record: ImportRecord, **changes: Any) -> ImportRecord:
    data = record_to_dict(record)
    data.update(changes)
    data["updated_at_utc"] = _now_iso()
    return record_from_dict(data)
