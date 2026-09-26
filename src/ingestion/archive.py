from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path

from src.runtime.api import release_exclusive, try_acquire_exclusive

from .models import (
    ARCH_ARCHIVED,
    ARCH_FAILED,
    ARCH_MOVING,
    ARCH_PENDING,
    ARCH_RECOVERY_REQUIRED,
    ImportRecord,
    PROC_DONE,
    SOURCE_WATCH_FOLDER,
)
from .store import _lock_path, get_record, save_record, update_record


def _save_locked(project_root: str | Path, record: ImportRecord) -> ImportRecord:
    return save_record(project_root, record, lock_held=True)


class ArchiveError(RuntimeError):
    pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolved(path: Path) -> Path:
    return path.resolve(strict=False)


def _same_path_case_insensitive(left: Path, right: Path) -> bool:
    return os.path.normcase(str(_resolved(left))) == os.path.normcase(str(_resolved(right)))


def plan_archive_target(record: ImportRecord, backup_dir: Path) -> Path:
    if not backup_dir.is_dir():
        raise ArchiveError("backup_dir_missing")
    source_name = Path(record.original_path).name
    base_target = backup_dir / source_name
    if not base_target.exists():
        return base_target
    if base_target.is_file():
        try:
            if sha256_file(base_target) == record.content_sha256:
                return base_target
        except OSError:
            pass
    stem = Path(source_name).stem
    suffix = Path(source_name).suffix or ".pdf"
    short = record.content_sha256[:12]
    candidate = backup_dir / f"{stem}_{short}{suffix}"
    if not candidate.exists():
        return candidate
    if candidate.is_file():
        try:
            if sha256_file(candidate) == record.content_sha256:
                return candidate
        except OSError:
            pass
    ingestion_candidate = backup_dir / f"{stem}_{short}_{record.ingestion_id[:8]}{suffix}"
    if not ingestion_candidate.exists():
        return ingestion_candidate
    if ingestion_candidate.is_file():
        try:
            if sha256_file(ingestion_candidate) == record.content_sha256:
                return ingestion_candidate
        except OSError:
            pass
        raise ArchiveError(f"archive_target_collision: {ingestion_candidate}")
    return ingestion_candidate


def partial_path(target: Path, ingestion_id: str) -> Path:
    return target.with_name(f"{target.name}.{ingestion_id}.partial")


def _stream_copy(source: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(source, "rb") as src, open(dest, "wb") as dst:
        for chunk in iter(lambda: src.read(1024 * 1024), b""):
            dst.write(chunk)
        dst.flush()
        os.fsync(dst.fileno())


def _exclusive_publish(partial: Path, target: Path, expected_sha256: str) -> Path:
    if not partial.is_file():
        raise ArchiveError("partial_missing")

    if target.exists():
        if target.is_file() and sha256_file(target) == expected_sha256:
            partial.unlink(missing_ok=True)
            return target
        raise ArchiveError(f"target_exists_different_content: {target}")

    if sha256_file(partial) != expected_sha256:
        raise ArchiveError("partial_hash_mismatch")

    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(partial, target)
    except FileExistsError:
        if target.is_file() and sha256_file(target) == expected_sha256:
            partial.unlink(missing_ok=True)
            return target
        raise ArchiveError(f"target_exists_different_content: {target}") from None
    except (AttributeError, OSError) as exc:
        raise ArchiveError(f"hardlink_publish_failed: {exc}") from exc

    if sha256_file(target) != expected_sha256:
        raise ArchiveError("final_hash_mismatch")
    partial.unlink(missing_ok=True)
    return target


def _verify_source_matches_ledger(source: Path, record: ImportRecord) -> None:
    stat = source.stat()
    if stat.st_size != record.file_size:
        raise ArchiveError("source_size_changed")
    if sha256_file(source) != record.content_sha256:
        raise ArchiveError("source_hash_changed")


def _safe_remove_source(source: Path, target: Path, record: ImportRecord) -> None:
    if _same_path_case_insensitive(source, target):
        return
    if not source.is_file():
        return
    _verify_source_matches_ledger(source, record)
    source.unlink(missing_ok=True)


def _resolve_archive_source(record: ImportRecord, target: Path) -> Path:
    current = Path(record.current_path)
    original = Path(record.original_path)
    if _same_path_case_insensitive(current, target) and original.is_file():
        if not _same_path_case_insensitive(original, target):
            return original
    if current.is_file():
        return current
    if original.is_file():
        return original
    return current


def _remove_verified_partial(partial: Path, expected_sha256: str) -> None:
    if not partial.is_file():
        return
    if sha256_file(partial) == expected_sha256:
        partial.unlink(missing_ok=True)


def _finalize_archived(
    project_root: str | Path,
    record: ImportRecord,
    target: Path,
    *,
    source: Path | None = None,
) -> ImportRecord:
    _remove_verified_partial(partial_path(target, record.ingestion_id), record.content_sha256)
    if source is not None and source.is_file() and not _same_path_case_insensitive(source, target):
        try:
            _safe_remove_source(source, target, record)
        except ArchiveError as exc:
            return _save_locked(
                project_root,
                update_record(
                    record,
                    archive_status=ARCH_FAILED,
                    archive_error=str(exc),
                ),
            )
    return _save_locked(
        project_root,
        update_record(
            record,
            current_path=str(_resolved(target)),
            archive_status=ARCH_ARCHIVED,
            archived_at_utc=record.archived_at_utc or _now_iso(),
            planned_archive_path=str(target),
            archive_target=str(target),
            archive_error="",
        ),
    )


def _reload_record_or_raise(project_root: str | Path, record: ImportRecord) -> ImportRecord:
    fresh = get_record(project_root, record.ingestion_id)
    if fresh is None:
        raise ArchiveError(f"ingestion_not_found: {record.ingestion_id}")
    return fresh


def _persist_pending(
    project_root: str | Path,
    record: ImportRecord,
    target: Path,
) -> ImportRecord:
    return _save_locked(
        project_root,
        update_record(
            record,
            planned_archive_path=str(target),
            archive_target=str(target),
            archive_status=ARCH_PENDING,
            archive_error="",
        ),
    )


def _finalize_from_valid_partial(
    project_root: str | Path,
    record: ImportRecord,
    target: Path,
    *,
    source: Path | None = None,
) -> ImportRecord:
    partial = partial_path(target, record.ingestion_id)
    if not partial.is_file():
        return _save_locked(
            project_root,
            update_record(
                record,
                archive_status=ARCH_RECOVERY_REQUIRED,
                archive_error="partial_missing_for_finalize",
            ),
        )
    try:
        if sha256_file(partial) != record.content_sha256:
            return _save_locked(
                project_root,
                update_record(
                    record,
                    archive_status=ARCH_RECOVERY_REQUIRED,
                    archive_error="invalid_partial_hash",
                ),
            )
        resolved_source = source
        if resolved_source is None:
            candidate = _resolve_archive_source(record, target)
            resolved_source = candidate if candidate.is_file() else None
        final_target = _exclusive_publish(partial, target, record.content_sha256)
        return _finalize_archived(project_root, record, final_target, source=resolved_source)
    except ArchiveError as exc:
        return _save_locked(
            project_root,
            update_record(
                record,
                archive_status=ARCH_FAILED,
                archive_error=str(exc),
            ),
        )
    except OSError as exc:
        return _save_locked(
            project_root,
            update_record(
                record,
                archive_status=ARCH_RECOVERY_REQUIRED,
                archive_error=f"invalid_partial_io: {exc}",
            ),
        )


def _complete_valid_target(
    project_root: str | Path,
    record: ImportRecord,
    target: Path,
    *,
    source: Path | None = None,
) -> ImportRecord | None:
    if not target.is_file():
        return None
    try:
        if sha256_file(target) != record.content_sha256:
            return None
    except OSError as exc:
        return _save_locked(
            project_root,
            update_record(
                record,
                archive_status=ARCH_FAILED,
                archive_error=f"target_verify_failed: {exc}",
            ),
        )
    resolved_source = source
    if resolved_source is None:
        candidate = _resolve_archive_source(record, target)
        resolved_source = candidate if candidate.is_file() else None
    return _finalize_archived(project_root, record, target, source=resolved_source)


def execute_archive_step(project_root: str | Path, record: ImportRecord, backup_dir: Path) -> ImportRecord:
    if record.source_kind != SOURCE_WATCH_FOLDER:
        raise ArchiveError("archive_not_applicable")
    if record.processing_status != PROC_DONE:
        raise ArchiveError("processing_not_done")

    lock_path = _lock_path(project_root, record.ingestion_id)
    if not try_acquire_exclusive(lock_path, 120.0):
        raise ArchiveError(f"archive_locked: {record.ingestion_id}")
    try:
        record = _reload_record_or_raise(project_root, record)
        if record.archive_status == ARCH_ARCHIVED:
            return record
        return _execute_archive_step_locked(project_root, record, backup_dir)
    finally:
        release_exclusive(lock_path)


def _execute_archive_step_locked(
    project_root: str | Path,
    record: ImportRecord,
    backup_dir: Path,
) -> ImportRecord:
    target = Path(record.planned_archive_path or str(plan_archive_target(record, backup_dir)))
    source = _resolve_archive_source(record, target)

    completed = _complete_valid_target(project_root, record, target, source=source if source.is_file() else None)
    if completed is not None:
        return completed

    if target.is_file():
        return _save_locked(
            project_root,
            update_record(
                record,
                archive_status=ARCH_FAILED,
                archive_error="target_exists_different_content",
            ),
        )

    if not source.is_file():
        partial = partial_path(target, record.ingestion_id)
        if partial.is_file():
            return _finalize_from_valid_partial(project_root, record, target)
        return _save_locked(
            project_root,
            update_record(
                record,
                archive_status=ARCH_RECOVERY_REQUIRED,
                archive_error="source_missing_for_archive",
            ),
        )

    record = _persist_pending(project_root, record, target)

    record = _save_locked(
        project_root,
        update_record(
            record,
            planned_archive_path=str(target),
            archive_target=str(target),
            archive_status=ARCH_MOVING,
            archive_error="",
        ),
    )

    partial = partial_path(target, record.ingestion_id)
    try:
        if partial.is_file():
            try:
                if sha256_file(partial) == record.content_sha256:
                    final_target = _exclusive_publish(partial, target, record.content_sha256)
                    return _finalize_archived(project_root, record, final_target, source=source)
                return _save_locked(
                    project_root,
                    update_record(
                        record,
                        archive_status=ARCH_RECOVERY_REQUIRED,
                        archive_error="invalid_partial_hash",
                    ),
                )
            except OSError as exc:
                return _save_locked(
                    project_root,
                    update_record(
                        record,
                        archive_status=ARCH_RECOVERY_REQUIRED,
                        archive_error=f"invalid_partial_io: {exc}",
                    ),
                )

        _stream_copy(source, partial)
        if partial.stat().st_size != record.file_size:
            raise ArchiveError("partial_size_mismatch")
        if sha256_file(partial) != record.content_sha256:
            raise ArchiveError("partial_hash_mismatch")

        final_target = _exclusive_publish(partial, target, record.content_sha256)
        return _finalize_archived(project_root, record, final_target, source=source)
    except Exception as exc:
        return _save_locked(
            project_root,
            update_record(
                record,
                archive_status=ARCH_FAILED,
                archive_error=str(exc),
            ),
        )


def reconcile_archive_record(
    project_root: str | Path,
    record: ImportRecord,
    backup_dir: Path,
) -> ImportRecord:
    lock_path = _lock_path(project_root, record.ingestion_id)
    if not try_acquire_exclusive(lock_path, 120.0):
        raise ArchiveError(f"archive_locked: {record.ingestion_id}")
    try:
        record = _reload_record_or_raise(project_root, record)
        if record.archive_status == ARCH_ARCHIVED:
            return record
        return _reconcile_archive_record_locked(project_root, record, backup_dir)
    finally:
        release_exclusive(lock_path)


def _reconcile_archive_record_locked(
    project_root: str | Path,
    record: ImportRecord,
    backup_dir: Path,
) -> ImportRecord:
    target_text = record.archive_target or record.planned_archive_path
    try:
        target = Path(target_text) if target_text else plan_archive_target(record, backup_dir)
    except ArchiveError as exc:
        return _save_locked(
            project_root,
            update_record(record, archive_status=ARCH_RECOVERY_REQUIRED, archive_error=str(exc)),
        )
    partial = partial_path(target, record.ingestion_id)
    source = _resolve_archive_source(record, target)

    source_exists = source.is_file()
    target_exists = target.is_file()

    if target_exists:
        completed = _complete_valid_target(
            project_root,
            record,
            target,
            source=source if source_exists else None,
        )
        if completed is not None:
            return completed

    if source_exists and not target_exists:
        planned = plan_archive_target(record, backup_dir)
        record = _persist_pending(project_root, record, planned)
        return _execute_archive_step_locked(project_root, record, backup_dir)

    if not source_exists and target_exists:
        return _save_locked(
            project_root,
            update_record(
                record,
                archive_status=ARCH_RECOVERY_REQUIRED,
                archive_error="target_present_source_missing_hash_unknown",
            ),
        )

    if source_exists and target_exists:
        return _save_locked(
            project_root,
            update_record(
                record,
                archive_status=ARCH_RECOVERY_REQUIRED,
                archive_error="target_hash_conflict",
            ),
        )

    if not source_exists and not target_exists:
        if partial.is_file():
            try:
                if sha256_file(partial) == record.content_sha256:
                    planned = plan_archive_target(record, backup_dir)
                    record = _persist_pending(project_root, record, planned)
                    return _finalize_from_valid_partial(project_root, record, planned)
                return _save_locked(
                    project_root,
                    update_record(
                        record,
                        archive_status=ARCH_RECOVERY_REQUIRED,
                        archive_error="invalid_partial_hash",
                    ),
                )
            except OSError as exc:
                return _save_locked(
                    project_root,
                    update_record(
                        record,
                        archive_status=ARCH_RECOVERY_REQUIRED,
                        archive_error=f"invalid_partial_io: {exc}",
                    ),
                )
        return _save_locked(
            project_root,
            update_record(
                record,
                archive_status=ARCH_RECOVERY_REQUIRED,
                archive_error="source_and_target_missing",
            ),
        )

    return record
