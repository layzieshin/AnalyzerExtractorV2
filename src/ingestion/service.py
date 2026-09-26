from __future__ import annotations

import hashlib
import os
import time
from collections.abc import Callable, Iterator
from datetime import datetime, timezone
from pathlib import Path

from src.jobqueue.api import QueueJob, list_jobs
from src.runtime.api import release_exclusive, try_acquire_exclusive

from .archive import execute_archive_step, plan_archive_target, reconcile_archive_record, sha256_file
from .models import (
    ARCH_ARCHIVED,
    ARCH_FAILED,
    ARCH_NOT_REQUIRED,
    ARCH_PENDING,
    ARCH_RECOVERY_REQUIRED,
    PROC_DONE,
    PROC_FAILED,
    PROC_PENDING,
    PROC_PROCESSING,
    PROC_REGISTERED,
    PATH_AMBIGUOUS,
    PATH_LEGACY,
    PATH_RESOLVED,
    SOURCE_MANUAL,
    SOURCE_WATCH_FOLDER,
    ImportRecord,
    PathResolution,
    RegisterImportResult,
    StabilityScannerState,
    WatchCycleResult,
    WatchScanOutcome,
)
from .store import (
    IngestionStoreError,
    acquire_registration_lock,
    compute_fingerprint,
    create_record,
    find_by_fingerprint,
    find_by_job_and_original_path,
    get_record,
    list_records,
    release_registration_lock,
    save_record,
    update_record,
)

DEFAULT_EXCLUDED_DIR_NAMES = frozenset(
    {"processed", "failed", "duplicates", "duplicate", "archive", "_archive"}
)


class IngestionError(RuntimeError):
    pass


EnqueueCallable = Callable[[str, str, str | None], QueueJob]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def compute_content_sha256(path: Path) -> tuple[str, int, int]:
    stat = path.stat()
    size = stat.st_size
    mtime_ns = stat.st_mtime_ns
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    after = path.stat()
    if after.st_size != size or after.st_mtime_ns != mtime_ns:
        raise IngestionError("source_changed_during_hash")
    return digest.hexdigest(), size, mtime_ns


def normalize_watch_path_key(path: str | Path) -> str:
    normalized = os.path.normpath(str(path or ""))
    return os.path.normcase(str(Path(normalized).resolve(strict=False)))


def _resolve_watch_path(path: str) -> Path:
    normalized = os.path.normpath(str(path or "").strip())
    if not normalized:
        raise IngestionError("invalid_path: empty")
    return Path(normalized).resolve(strict=False)


def validate_watch_path_pair(watch_input_path: str, watch_backup_path: str) -> None:
    if not str(watch_input_path or "").strip():
        raise IngestionError("watch_input_path_required")
    if not str(watch_backup_path or "").strip():
        raise IngestionError("watch_backup_path_required")
    input_path = _resolve_watch_path(watch_input_path)
    backup_path = _resolve_watch_path(watch_backup_path)
    if not input_path.is_dir():
        raise IngestionError(f"watch_input_not_directory: {input_path}")
    if backup_path.exists() and backup_path.is_file():
        raise IngestionError(f"watch_backup_path_is_file: {backup_path}")
    if os.path.normcase(str(input_path)) == os.path.normcase(str(backup_path)):
        raise IngestionError("watch_input_backup_same_path")
    if _path_is_contained(backup_path, input_path):
        raise IngestionError("watch_backup_under_input")
    if _path_is_contained(input_path, backup_path):
        raise IngestionError("watch_input_under_backup")
    if not backup_path.is_dir():
        backup_path.mkdir(parents=True, exist_ok=True)


def _path_is_contained(inner: Path, outer: Path) -> bool:
    inner_key = normalize_watch_path_key(inner)
    outer_key = normalize_watch_path_key(outer)
    if inner_key == outer_key:
        return False
    prefix = outer_key + os.sep
    return inner_key.startswith(prefix)


def _normalized_excluded_dir_names(excluded_dir_names: set[str] | None) -> set[str]:
    names = DEFAULT_EXCLUDED_DIR_NAMES if excluded_dir_names is None else excluded_dir_names
    return {name.casefold() for name in names}


def iter_watch_pdf_files(
    watch_path: Path,
    *,
    recursive: bool = False,
    excluded_dir_names: set[str] | None = None,
) -> Iterator[Path]:
    if not watch_path.is_dir():
        return

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
                if entry.is_file() and not entry.is_symlink():
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
                if entry.suffix.lower() == ".pdf" and entry.is_file() and not entry.is_symlink():
                    yield entry
            except OSError:
                continue

    yield from walk(watch_path)


def list_watch_pdfs(watch_dir: Path) -> list[Path]:
    return list(iter_watch_pdf_files(watch_dir, recursive=False))


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
    for entry in iter_watch_pdf_files(
        watch_path,
        recursive=recursive,
        excluded_dir_names=excluded_dir_names,
    ):
        try:
            paths.append(str(entry.resolve(strict=False)))
        except OSError:
            continue
    return sorted(paths, key=str.casefold)


def observe_stable_pdfs(
    watch_dir: Path,
    *,
    stable_window_s: float,
    state: StabilityScannerState,
    now: float | None = None,
    known_paths: set[str] | None = None,
    recursive: bool = False,
    excluded_dir_names: set[str] | None = None,
) -> list[Path]:
    current_time = time.time() if now is None else now
    stable: list[Path] = []
    seen_keys: set[str] = set()
    known_keys = {normalize_watch_path_key(path) for path in (known_paths or set()) if path}

    for pdf in iter_watch_pdf_files(
        watch_dir,
        recursive=recursive,
        excluded_dir_names=excluded_dir_names,
    ):
        key = normalize_watch_path_key(pdf)
        if not key:
            continue
        seen_keys.add(key)
        if key in known_keys:
            continue
        try:
            stat = pdf.stat()
        except OSError:
            state.observations.pop(key, None)
            continue
        size = stat.st_size
        mtime_ns = stat.st_mtime_ns
        if stable_window_s <= 0:
            stable.append(pdf)
            continue
        prev = state.observations.get(key)
        if prev is None:
            state.observations[key] = (size, mtime_ns, current_time)
            continue
        prev_size, prev_mtime_ns, prev_ts = prev
        if prev_size != size or prev_mtime_ns != mtime_ns:
            state.observations[key] = (size, mtime_ns, current_time)
            continue
        if (current_time - prev_ts) >= stable_window_s:
            stable.append(pdf)

    for key in list(state.observations):
        if key not in seen_keys or key in known_keys:
            state.observations.pop(key, None)
    return stable


def hash_stable_pdf(pdf: Path) -> tuple[str, int, int]:
    stat_before = pdf.stat()
    size = stat_before.st_size
    mtime_ns = stat_before.st_mtime_ns
    digest = hashlib.sha256()
    with open(pdf, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    stat_after = pdf.stat()
    if stat_after.st_size != size or stat_after.st_mtime_ns != mtime_ns:
        raise IngestionError("source_changed_during_hash")
    return digest.hexdigest(), size, mtime_ns


def _lookup_queue_job(project_root: str | Path, job_id: str) -> QueueJob | None:
    for job in list_jobs(str(project_root)):
        if job.job_id == job_id:
            return job
    return None


def register_import(
    project_root: str | Path,
    pdf_path: str | Path,
    *,
    source_kind: str,
    enqueue: EnqueueCallable,
    watch_input_path: str = "",
    watch_backup_path: str = "",
    source_label: str = "ingestion",
) -> RegisterImportResult:
    path = Path(pdf_path)
    if not path.is_file():
        raise IngestionError(f"pdf_not_found: {path}")
    content_sha256, size, mtime_ns = hash_stable_pdf(path)
    fingerprint = compute_fingerprint(path, size=size, mtime_ns=mtime_ns, content_sha256=content_sha256)

    registration_lock: Path | None = None
    try:
        registration_lock = acquire_registration_lock(project_root, fingerprint)
        existing = find_by_fingerprint(project_root, fingerprint)
        if existing is not None:
            fresh_job = _lookup_queue_job(project_root, existing.processing_job_id)
            if fresh_job is not None:
                mapped_status = _map_queue_status(fresh_job.status)
                if (
                    existing.processing_status != mapped_status
                    or existing.last_error != fresh_job.last_error
                ):
                    reconciled = reconcile_processing_for_job(
                        project_root,
                        existing.processing_job_id,
                        fresh_job.status,
                        error=fresh_job.last_error,
                    )
                    if reconciled:
                        existing = reconciled[-1]
                    else:
                        refreshed = get_record(project_root, existing.ingestion_id)
                        if refreshed is not None:
                            existing = refreshed
                elif mapped_status == PROC_DONE and existing.source_kind == SOURCE_WATCH_FOLDER:
                    if existing.archive_status not in {ARCH_ARCHIVED, ARCH_NOT_REQUIRED}:
                        existing = maybe_archive_record(project_root, existing)
            return RegisterImportResult(
                record=existing,
                created=False,
                enqueued=False,
                queue_status=fresh_job.status if fresh_job is not None else existing.processing_status,
                message="already_registered",
            )

        try:
            job = enqueue(str(path), source_label, content_sha256)
        except Exception as exc:
            raise IngestionError(str(exc)) from exc

        archive_status = ARCH_NOT_REQUIRED if source_kind == SOURCE_MANUAL else ARCH_PENDING
        record = create_record(
            source_kind=source_kind,
            original_path=str(path),
            content_sha256=content_sha256,
            processing_job_id=job.job_id,
            file_size=size,
            file_mtime_ns=mtime_ns,
            watch_input_path=watch_input_path,
            watch_backup_path=watch_backup_path,
            archive_status=archive_status,
        )
        record = update_record(
            record,
            processing_status=_map_queue_status(job.status),
            last_error=job.last_error,
        )
        if source_kind == SOURCE_WATCH_FOLDER and job.status == "DONE":
            planned = plan_archive_target(record, Path(watch_backup_path))
            record = update_record(
                record,
                planned_archive_path=str(planned),
                archive_target=str(planned),
            )
        record = save_record(project_root, record)

        fresh_job = _lookup_queue_job(project_root, job.job_id)
        if fresh_job is not None and (
            fresh_job.status != job.status or fresh_job.last_error != job.last_error
        ):
            reconciled = reconcile_processing_for_job(
                project_root,
                job.job_id,
                fresh_job.status,
                error=fresh_job.last_error,
            )
            if reconciled:
                record = reconciled[-1]
            else:
                refreshed = get_record(project_root, record.ingestion_id)
                if refreshed is not None:
                    record = refreshed
        elif source_kind == SOURCE_WATCH_FOLDER and record.processing_status == PROC_DONE:
            record = maybe_archive_record(project_root, record)

        return RegisterImportResult(
            record=record,
            created=True,
            enqueued=job.status == "PENDING",
            queue_status=fresh_job.status if fresh_job is not None else job.status,
            message="registered",
        )
    finally:
        if registration_lock is not None:
            release_registration_lock(registration_lock)


def _map_queue_status(status: str) -> str:
    mapping = {
        "PENDING": PROC_PENDING,
        "PROCESSING": PROC_PROCESSING,
        "DONE": PROC_DONE,
        "FAILED": PROC_FAILED,
    }
    return mapping.get(status, PROC_REGISTERED)


def reconcile_processing_for_job(
    project_root: str | Path,
    job_id: str,
    queue_status: str,
    *,
    error: str = "",
) -> list[ImportRecord]:
    updated: list[ImportRecord] = []
    proc_status = _map_queue_status(queue_status)
    for record in list_records(project_root):
        if record.processing_job_id != job_id:
            continue
        if record.processing_status == proc_status and record.last_error == error:
            if proc_status == PROC_DONE and record.source_kind == SOURCE_WATCH_FOLDER:
                if record.archive_status not in {ARCH_ARCHIVED, ARCH_NOT_REQUIRED}:
                    record = maybe_archive_record(project_root, record)
            updated.append(record)
            continue
        record = update_record(record, processing_status=proc_status, last_error=error)
        record = save_record(project_root, record)
        if proc_status == PROC_DONE and record.source_kind == SOURCE_WATCH_FOLDER:
            backup = Path(record.watch_backup_path)
            if record.planned_archive_path:
                record = maybe_archive_record(project_root, record)
            elif backup.is_dir() or str(record.watch_backup_path):
                planned = plan_archive_target(record, backup)
                record = save_record(
                    project_root,
                    update_record(
                        record,
                        planned_archive_path=str(planned),
                        archive_target=str(planned),
                        archive_status=ARCH_PENDING,
                    ),
                )
                record = maybe_archive_record(project_root, record)
        updated.append(record)
    return updated


def maybe_archive_record(project_root: str | Path, record: ImportRecord) -> ImportRecord:
    if record.source_kind != SOURCE_WATCH_FOLDER:
        return record
    if record.processing_status != PROC_DONE:
        return record
    if record.archive_status == ARCH_NOT_REQUIRED:
        return record
    if record.archive_status == ARCH_ARCHIVED:
        return record
    backup_dir = Path(record.watch_backup_path)
    if not str(record.watch_backup_path).strip():
        return save_record(
            project_root,
            update_record(
                record,
                archive_status=ARCH_FAILED,
                archive_error="watch_backup_path_missing",
            ),
        )
    backup_dir.mkdir(parents=True, exist_ok=True)
    return execute_archive_step(project_root, record, backup_dir)


def reconcile_archive_recovery(project_root: str | Path, watch_backup_path: str) -> list[ImportRecord]:
    backup_dir = Path(watch_backup_path)
    updated: list[ImportRecord] = []
    for record in list_records(project_root):
        if record.source_kind != SOURCE_WATCH_FOLDER:
            continue
        if record.archive_status in {ARCH_ARCHIVED, ARCH_NOT_REQUIRED}:
            continue
        if record.processing_status != PROC_DONE:
            continue
        updated.append(reconcile_archive_record(project_root, record, backup_dir))
    return updated


def retry_archive(project_root: str | Path, ingestion_id: str) -> ImportRecord:
    record = get_record(project_root, ingestion_id)
    if record is None:
        raise IngestionError(f"ingestion_not_found: {ingestion_id}")
    if record.source_kind != SOURCE_WATCH_FOLDER:
        raise IngestionError("archive_retry_not_applicable")
    if record.processing_status != PROC_DONE:
        raise IngestionError("processing_not_done")
    backup_dir = Path(record.watch_backup_path)
    if not str(record.watch_backup_path).strip():
        raise IngestionError("watch_backup_path_missing")
    backup_dir.mkdir(parents=True, exist_ok=True)
    planned = plan_archive_target(record, backup_dir)
    record = save_record(
        project_root,
        update_record(
            record,
            planned_archive_path=str(planned),
            archive_target=str(planned),
            archive_status=ARCH_PENDING,
            archive_error="",
        ),
    )
    return execute_archive_step(project_root, record, backup_dir)


def resolve_current_path(
    project_root: str | Path,
    job_id: str,
    original_pdf_path: str,
) -> PathResolution:
    source_path = str(Path(original_pdf_path).resolve(strict=False))
    matches = find_by_job_and_original_path(project_root, job_id, source_path)
    if len(matches) == 1:
        record = matches[0]
        return PathResolution(
            source_pdf_path=record.original_path,
            current_pdf_path=record.current_path,
            ingestion_id=record.ingestion_id,
            path_status=PATH_RESOLVED,
        )
    if len(matches) > 1:
        return PathResolution(
            source_pdf_path=source_path,
            current_pdf_path=source_path,
            ingestion_id="",
            path_status=PATH_AMBIGUOUS,
        )
    return PathResolution(
        source_pdf_path=source_path,
        current_pdf_path=source_path,
        ingestion_id="",
        path_status=PATH_LEGACY,
    )


def _watch_cycle_lock(project_root: str | Path) -> Path:
    root = Path(project_root).resolve()
    lock_dir = root / "storage" / "ingestion" / "locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    return lock_dir / "watch_cycle.lock"


def run_watch_scan_cycle(
    project_root: str | Path,
    *,
    watch_input_path: str,
    watch_backup_path: str,
    stable_window_s: float,
    enqueue: EnqueueCallable,
    state: StabilityScannerState | None = None,
    recursive: bool = False,
) -> WatchCycleResult:
    validate_watch_path_pair(watch_input_path, watch_backup_path)
    lock_path = _watch_cycle_lock(project_root)
    if not try_acquire_exclusive(lock_path, 120.0):
        return WatchCycleResult(enabled=True, busy=True, outcomes=())

    scanner_state = state or StabilityScannerState()
    outcomes: list[WatchScanOutcome] = []
    try:
        recovery = reconcile_archive_recovery(project_root, watch_backup_path)
        watch_dir = Path(watch_input_path)
        stable_pdfs = observe_stable_pdfs(
            watch_dir,
            stable_window_s=stable_window_s,
            state=scanner_state,
            recursive=recursive,
        )
        for pdf in stable_pdfs:
            try:
                result = register_import(
                    project_root,
                    pdf,
                    source_kind=SOURCE_WATCH_FOLDER,
                    enqueue=enqueue,
                    watch_input_path=watch_input_path,
                    watch_backup_path=watch_backup_path,
                    source_label="watch-folder",
                )
                outcomes.append(
                    WatchScanOutcome(
                        pdf_path=str(pdf),
                        outcome="registered" if result.created else "skipped",
                        message=result.message,
                        ingestion_id=result.record.ingestion_id,
                        job_id=result.record.processing_job_id,
                    )
                )
            except Exception as exc:
                outcomes.append(
                    WatchScanOutcome(
                        pdf_path=str(pdf),
                        outcome="error",
                        message=str(exc),
                    )
                )
        return WatchCycleResult(
            enabled=True,
            recovery_count=len(recovery),
            scanned_count=len(stable_pdfs),
            outcomes=tuple(outcomes),
        )
    finally:
        release_exclusive(lock_path)


def mark_source_changed_failure(project_root: str | Path, job_id: str, pdf_path: str) -> list[ImportRecord]:
    return reconcile_processing_for_job(
        project_root,
        job_id,
        "FAILED",
        error="source_changed_since_ingest",
    )
