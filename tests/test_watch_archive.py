from __future__ import annotations

from pathlib import Path

import pytest

from src.application.api import ApplicationWatchError, SettingsValidationError, create_desktop_services
from src.ingestion.api import (
    IngestionError,
    get_import_record,
    reconcile_archive_recovery,
    register_import,
    retry_archive,
)
from src.ingestion.models import (
    ARCH_ARCHIVED,
    ARCH_FAILED,
    ARCH_NOT_REQUIRED,
    ARCH_RECOVERY_REQUIRED,
    PROC_DONE,
    SOURCE_MANUAL,
    SOURCE_WATCH_FOLDER,
)
from src.jobqueue.api import claim_next_job, enqueue_pdf_job, list_jobs, mark_job_done
from src.processing.api import ProcessingConfig, process_next_pending
from src.jobcontroller.model import JobResult


def _enqueue(root: Path):
    def enqueue(pdf_path: str, source: str, expected_sha256: str | None):
        return enqueue_pdf_job(str(root), pdf_path, source=source, expected_sha256=expected_sha256)

    return enqueue


def _register_watch(root: Path, pdf: Path, watch: Path, backup: Path):
    return register_import(
        root,
        pdf,
        source_kind=SOURCE_WATCH_FOLDER,
        enqueue=_enqueue(root),
        source_label="watch-folder",
        watch_input_path=str(watch),
        watch_backup_path=str(backup),
    ).record


def test_done_watch_job_archives_and_updates_current_path(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    watch = root / "watch"
    backup = root / "backup"
    watch.mkdir(parents=True)
    backup.mkdir(parents=True)
    pdf = watch / "sample.pdf"
    pdf.write_bytes(b"archive-me")

    record = _register_watch(root, pdf, watch, backup)
    from src.ingestion.api import reconcile_processing_for_job

    reconcile_processing_for_job(root, record.processing_job_id, "DONE")

    updated = get_import_record(root, record.ingestion_id)
    assert updated is not None
    assert updated.archive_status == ARCH_ARCHIVED
    assert not Path(record.original_path).exists()
    assert Path(updated.current_path).is_file()


def test_failed_watch_job_does_not_move(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    watch = root / "watch"
    backup = root / "backup"
    watch.mkdir(parents=True)
    backup.mkdir(parents=True)
    pdf = watch / "fail.pdf"
    pdf.write_bytes(b"fail")

    record = _register_watch(root, pdf, watch, backup)
    from src.ingestion.api import reconcile_processing_for_job

    reconcile_processing_for_job(root, record.processing_job_id, "FAILED", error="boom")
    updated = get_import_record(root, record.ingestion_id)
    assert updated is not None
    assert updated.archive_status != ARCH_ARCHIVED
    assert Path(record.original_path).is_file()


def test_archive_collision_does_not_overwrite(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    watch = root / "watch"
    backup = root / "backup"
    watch.mkdir(parents=True)
    backup.mkdir(parents=True)
    pdf = watch / "collision.pdf"
    pdf.write_bytes(b"new-content")
    existing = backup / "collision.pdf"
    existing.write_bytes(b"other-content")

    record = _register_watch(root, pdf, watch, backup)
    from src.ingestion.api import reconcile_processing_for_job

    reconcile_processing_for_job(root, record.processing_job_id, "DONE")
    updated = get_import_record(root, record.ingestion_id)
    assert updated is not None
    assert existing.read_bytes() == b"other-content"
    assert Path(updated.current_path).name != existing.name or updated.current_path != str(existing)


def _mark_queue_done(root: Path, job_id: str) -> None:
    claimed = claim_next_job(str(root), "test-worker")
    assert claimed is not None
    assert claimed.job_id == job_id
    mark_job_done(str(root), job_id, worker_id="test-worker")


def test_archive_failed_keeps_queue_done(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "proj"
    watch = root / "watch"
    backup = root / "backup"
    watch.mkdir(parents=True)
    backup.mkdir(parents=True)
    pdf = watch / "broken.pdf"
    pdf.write_bytes(b"broken")
    record = _register_watch(root, pdf, watch, backup)
    _mark_queue_done(root, record.processing_job_id)

    def boom(*_args, **_kwargs):
        raise OSError("disk-full")

    monkeypatch.setattr("src.ingestion.archive._stream_copy", boom)
    from src.ingestion.api import reconcile_processing_for_job

    reconcile_processing_for_job(root, record.processing_job_id, "DONE")
    updated = get_import_record(root, record.ingestion_id)
    assert updated is not None
    assert updated.archive_status == ARCH_FAILED
    assert list_jobs(str(root))[0].status == "DONE"


def test_retry_archive_does_not_enqueue_processing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "proj"
    watch = root / "watch"
    backup = root / "backup"
    watch.mkdir(parents=True)
    backup.mkdir(parents=True)
    pdf = watch / "retry.pdf"
    pdf.write_bytes(b"retry")
    record = _register_watch(root, pdf, watch, backup)
    _mark_queue_done(root, record.processing_job_id)

    def boom(*_args, **_kwargs):
        raise OSError("disk-full")

    monkeypatch.setattr("src.ingestion.archive._stream_copy", boom)
    from src.ingestion.api import reconcile_processing_for_job

    reconcile_processing_for_job(root, record.processing_job_id, "DONE")
    failed = get_import_record(root, record.ingestion_id)
    assert failed is not None
    assert failed.archive_status == ARCH_FAILED
    jobs_before = len(list_jobs(str(root)))
    retried = retry_archive(root, record.ingestion_id)
    assert len(list_jobs(str(root))) == jobs_before
    assert retried.processing_status == PROC_DONE


def test_recovery_source_present_target_missing(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    watch = root / "watch"
    backup = root / "backup"
    watch.mkdir(parents=True)
    backup.mkdir(parents=True)
    pdf = watch / "recover-a.pdf"
    pdf.write_bytes(b"recover-a")
    record = _register_watch(root, pdf, watch, backup)
    _mark_queue_done(root, record.processing_job_id)
    from src.ingestion.api import reconcile_processing_for_job

    reconcile_processing_for_job(root, record.processing_job_id, "DONE")
    updated = get_import_record(root, record.ingestion_id)
    assert updated is not None
    assert updated.archive_status == ARCH_ARCHIVED


def test_recovery_source_missing_target_valid(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    watch = root / "watch"
    backup = root / "backup"
    watch.mkdir(parents=True)
    backup.mkdir(parents=True)
    pdf = watch / "recover-b.pdf"
    content = b"recover-b"
    pdf.write_bytes(content)
    record = _register_watch(root, pdf, watch, backup)
    target = backup / "recover-b.pdf"
    target.write_bytes(content)
    pdf.unlink()
    from src.ingestion.store import save_record, update_record

    pending = update_record(
        record,
        processing_status=PROC_DONE,
        archive_status="PENDING",
        planned_archive_path=str(target),
        archive_target=str(target),
    )
    save_record(root, pending)
    recovered = reconcile_archive_recovery(root, str(backup))[0]
    assert recovered.archive_status == ARCH_ARCHIVED
    assert Path(recovered.current_path).is_file()


def test_watch_disabled_writes_nothing(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    services = create_desktop_services(root)
    summary = services.extraction.run_watch_cycle()
    assert summary.enabled is False
    assert not (root / "storage" / "ingestion").exists()


def test_watch_enabled_invalid_settings_fail_fast(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    services = create_desktop_services(root)
    settings = services.settings.load().__class__(
        output_mode="both",
        sqlite_path=str(root / "db.sqlite3"),
        watch_enabled=True,
        watch_input_path=str(root / "watch"),
        watch_backup_path=str(root / "watch"),
        device_id=None,
    )
    with pytest.raises(SettingsValidationError):
        services.settings.save(settings)


def test_already_done_second_watch_import_archives_without_processing(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    watch = root / "watch"
    backup = root / "backup"
    watch.mkdir(parents=True)
    backup.mkdir(parents=True)
    pdf_a = watch / "a.pdf"
    pdf_b = watch / "b.pdf"
    content = b"same-done"
    pdf_a.write_bytes(content)
    pdf_b.write_bytes(content)
    first = _register_watch(root, pdf_a, watch, backup)
    _mark_queue_done(root, first.processing_job_id)
    from src.ingestion.api import reconcile_processing_for_job

    reconcile_processing_for_job(root, first.processing_job_id, "DONE")
    second = _register_watch(root, pdf_b, watch, backup)
    updated = get_import_record(root, second.ingestion_id)
    assert updated is not None
    assert updated.processing_status == PROC_DONE
    assert updated.archive_status == ARCH_ARCHIVED
    assert len(list_jobs(str(root))) == 1


def test_manual_under_watch_dir_stays_unmoved(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    watch = root / "watch"
    watch.mkdir(parents=True)
    pdf = watch / "manual.pdf"
    pdf.write_bytes(b"manual-in-watch")
    record = register_import(
        root,
        pdf,
        source_kind=SOURCE_MANUAL,
        enqueue=_enqueue(root),
        source_label="manual",
    ).record
    assert record.archive_status == ARCH_NOT_REQUIRED
    assert Path(pdf).is_file()


def test_publish_race_leaves_foreign_target_and_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    root = tmp_path / "proj"
    watch = root / "watch"
    backup = root / "backup"
    watch.mkdir(parents=True)
    backup.mkdir(parents=True)
    pdf = watch / "race.pdf"
    pdf.write_bytes(b"race-content")
    record = _register_watch(root, pdf, watch, backup)
    from src.ingestion.api import reconcile_processing_for_job

    target = backup / "race.pdf"
    real_link = os.link

    def racing_link(src, dst, *args, **kwargs):
        Path(dst).write_bytes(b"foreign-bytes")
        raise FileExistsError

    monkeypatch.setattr(os, "link", racing_link)
    reconcile_processing_for_job(root, record.processing_job_id, "DONE")
    updated = get_import_record(root, record.ingestion_id)
    assert updated is not None
    assert updated.archive_status != ARCH_ARCHIVED
    assert pdf.is_file()
    assert target.read_bytes() == b"foreign-bytes"
    monkeypatch.setattr(os, "link", real_link)


def test_hardlink_unsupported_preserves_source_and_partial(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    root = tmp_path / "proj"
    watch = root / "watch"
    backup = root / "backup"
    watch.mkdir(parents=True)
    backup.mkdir(parents=True)
    pdf = watch / "nolink.pdf"
    content = b"nolink-content"
    pdf.write_bytes(content)
    record = _register_watch(root, pdf, watch, backup)
    from src.ingestion.archive import partial_path
    from src.ingestion.api import reconcile_processing_for_job

    target = backup / "nolink.pdf"
    partial = partial_path(target, record.ingestion_id)

    def fail_link(*_args, **_kwargs):
        raise OSError(1, "hardlink not supported")

    monkeypatch.setattr(os, "link", fail_link)
    monkeypatch.setattr("src.ingestion.archive._stream_copy", lambda src, dest: dest.write_bytes(content))
    reconcile_processing_for_job(root, record.processing_job_id, "DONE")
    updated = get_import_record(root, record.ingestion_id)
    assert updated is not None
    assert updated.archive_status == ARCH_FAILED
    assert pdf.is_file()
    assert partial.is_file()
    assert not target.exists()


def test_valid_partial_recovery_without_source(tmp_path: Path) -> None:
    from src.ingestion.archive import partial_path
    from src.ingestion.store import save_record, update_record

    root = tmp_path / "proj"
    watch = root / "watch"
    backup = root / "backup"
    watch.mkdir(parents=True)
    backup.mkdir(parents=True)
    pdf = watch / "partial-only.pdf"
    content = b"partial-only"
    pdf.write_bytes(content)
    record = _register_watch(root, pdf, watch, backup)
    target = backup / "partial-only.pdf"
    partial = partial_path(target, record.ingestion_id)
    partial.write_bytes(content)
    pdf.unlink()
    pending = update_record(
        record,
        processing_status=PROC_DONE,
        planned_archive_path=str(target),
        archive_target=str(target),
        archive_status="PENDING",
    )
    save_record(root, pending)
    recovered = reconcile_archive_recovery(root, str(backup))[0]
    assert recovered.archive_status == ARCH_ARCHIVED
    assert target.read_bytes() == content
    assert not partial.exists()
    assert Path(recovered.current_path).is_file()


def test_crash_after_link_before_partial_unlink_recovers(tmp_path: Path) -> None:
    from src.ingestion.archive import partial_path
    from src.ingestion.store import save_record, update_record

    root = tmp_path / "proj"
    watch = root / "watch"
    backup = root / "backup"
    watch.mkdir(parents=True)
    backup.mkdir(parents=True)
    pdf = watch / "linked.pdf"
    content = b"linked-content"
    pdf.write_bytes(content)
    record = _register_watch(root, pdf, watch, backup)
    target = backup / "linked.pdf"
    target.write_bytes(content)
    partial = partial_path(target, record.ingestion_id)
    partial.write_bytes(content)
    pending = update_record(
        record,
        processing_status=PROC_DONE,
        planned_archive_path=str(target),
        archive_target=str(target),
        archive_status="PENDING",
    )
    save_record(root, pending)
    recovered = reconcile_archive_recovery(root, str(backup))[0]
    assert recovered.archive_status == ARCH_ARCHIVED
    assert target.read_bytes() == content
    assert not partial.exists()


def test_stale_second_execute_does_not_downgrade_archived(tmp_path: Path) -> None:
    from src.ingestion.archive import execute_archive_step
    from src.ingestion.models import ARCH_PENDING
    from src.ingestion.store import save_record, update_record

    root = tmp_path / "proj"
    watch = root / "watch"
    backup = root / "backup"
    watch.mkdir(parents=True)
    backup.mkdir(parents=True)
    pdf = watch / "stale.pdf"
    pdf.write_bytes(b"stale")
    record = _register_watch(root, pdf, watch, backup)
    from src.ingestion.api import reconcile_processing_for_job

    archived = reconcile_processing_for_job(root, record.processing_job_id, "DONE")[0]
    assert archived.archive_status == ARCH_ARCHIVED
    stale = update_record(archived, archive_status=ARCH_PENDING, archive_error="stale-view")
    second = execute_archive_step(root, stale, backup)
    assert second.archive_status == ARCH_ARCHIVED


def test_pending_persisted_before_moving(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from src.ingestion.store import save_record, update_record

    root = tmp_path / "proj"
    watch = root / "watch"
    backup = root / "backup"
    watch.mkdir(parents=True)
    backup.mkdir(parents=True)
    pdf = watch / "pending-order.pdf"
    content = b"pending-order"
    pdf.write_bytes(content)
    record = _register_watch(root, pdf, watch, backup)
    _mark_queue_done(root, record.processing_job_id)
    pending = update_record(
        record,
        processing_status=PROC_DONE,
        planned_archive_path=str(backup / "pending-order.pdf"),
        archive_target=str(backup / "pending-order.pdf"),
        archive_status="PENDING",
    )
    save_record(root, pending)
    statuses: list[str] = []
    original_save = save_record

    def tracking_save(project_root, rec, **kwargs):
        statuses.append(rec.archive_status)
        return original_save(project_root, rec, **kwargs)

    monkeypatch.setattr("src.ingestion.archive.save_record", tracking_save)
    reconcile_archive_recovery(root, str(backup))
    assert "PENDING" in statuses
    assert "MOVING" in statuses
    assert statuses.index("PENDING") < statuses.index("MOVING")


def test_existing_fingerprint_reconciles_terminal_queue_done(tmp_path: Path) -> None:
    from src.jobqueue.api import claim_next_job, mark_job_done

    root = tmp_path / "proj"
    watch = root / "watch"
    backup = root / "backup"
    watch.mkdir(parents=True)
    backup.mkdir(parents=True)
    pdf = watch / "terminal.pdf"
    content = b"terminal-done"
    pdf.write_bytes(content)
    first = register_import(
        root,
        pdf,
        source_kind=SOURCE_WATCH_FOLDER,
        enqueue=_enqueue(root),
        source_label="watch-folder",
        watch_input_path=str(watch),
        watch_backup_path=str(backup),
    )
    claimed = claim_next_job(str(root), "w1")
    assert claimed is not None
    mark_job_done(str(root), claimed.job_id, worker_id="w1")
    from src.ingestion.store import save_record, update_record

    stale = update_record(first.record, processing_status="PENDING", archive_status="PENDING")
    save_record(root, stale)
    second = register_import(
        root,
        pdf,
        source_kind=SOURCE_WATCH_FOLDER,
        enqueue=_enqueue(root),
        source_label="watch-folder",
        watch_input_path=str(watch),
        watch_backup_path=str(backup),
    )
    assert second.created is False
    assert second.record.processing_status == PROC_DONE
    assert second.record.archive_status == ARCH_ARCHIVED


def test_reconcile_processing_done_still_archives_when_status_unchanged(tmp_path: Path) -> None:
    from src.ingestion.api import reconcile_processing_for_job
    from src.ingestion.store import save_record, update_record

    root = tmp_path / "proj"
    watch = root / "watch"
    backup = root / "backup"
    watch.mkdir(parents=True)
    backup.mkdir(parents=True)
    pdf = watch / "reconcile-done.pdf"
    pdf.write_bytes(b"reconcile-done")
    record = _register_watch(root, pdf, watch, backup)
    _mark_queue_done(root, record.processing_job_id)
    pending = update_record(
        record,
        processing_status=PROC_DONE,
        archive_status="PENDING",
        planned_archive_path=str(backup / "reconcile-done.pdf"),
        archive_target=str(backup / "reconcile-done.pdf"),
    )
    save_record(root, pending)
    updated = reconcile_processing_for_job(root, record.processing_job_id, "DONE")[0]
    assert updated.archive_status == ARCH_ARCHIVED
    again = reconcile_processing_for_job(root, record.processing_job_id, "DONE")[0]
    assert again.archive_status == ARCH_ARCHIVED


def test_current_path_equal_target_removes_original(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    watch = root / "watch"
    backup = root / "backup"
    watch.mkdir(parents=True)
    backup.mkdir(parents=True)
    pdf = watch / "idempotent.pdf"
    content = b"idempotent"
    pdf.write_bytes(content)
    record = _register_watch(root, pdf, watch, backup)
    target = backup / "idempotent.pdf"
    target.write_bytes(content)
    from src.ingestion.store import save_record, update_record

    done = update_record(
        record,
        processing_status=PROC_DONE,
        current_path=str(target),
        planned_archive_path=str(target),
        archive_target=str(target),
        archive_status="PENDING",
    )
    save_record(root, done)
    recovered = reconcile_archive_recovery(root, str(backup))[0]
    assert target.is_file()
    assert recovered.archive_status == ARCH_ARCHIVED
    assert not pdf.exists()


def test_changed_source_with_valid_target_never_deletes_target(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    watch = root / "watch"
    backup = root / "backup"
    watch.mkdir(parents=True)
    backup.mkdir(parents=True)
    pdf = watch / "keep-target.pdf"
    content = b"keep-target"
    pdf.write_bytes(content)
    record = _register_watch(root, pdf, watch, backup)
    target = backup / "keep-target.pdf"
    target.write_bytes(content)
    pdf.write_bytes(b"changed-source")
    from src.ingestion.store import save_record, update_record

    pending = update_record(
        record,
        processing_status=PROC_DONE,
        archive_status="PENDING",
        planned_archive_path=str(target),
        archive_target=str(target),
    )
    save_record(root, pending)
    recovered = reconcile_archive_recovery(root, str(backup))[0]
    assert target.read_bytes() == content
    assert recovered.archive_status != ARCH_ARCHIVED
    assert pdf.read_bytes() == b"changed-source"


def test_recovery_neither_source_nor_target(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    watch = root / "watch"
    backup = root / "backup"
    watch.mkdir(parents=True)
    backup.mkdir(parents=True)
    pdf = watch / "missing-both.pdf"
    content = b"missing-both"
    pdf.write_bytes(content)
    record = _register_watch(root, pdf, watch, backup)
    target = backup / "missing-both.pdf"
    pdf.unlink()
    from src.ingestion.store import save_record, update_record

    pending = update_record(
        record,
        processing_status=PROC_DONE,
        planned_archive_path=str(target),
        archive_target=str(target),
        archive_status="PENDING",
    )
    save_record(root, pending)
    recovered = reconcile_archive_recovery(root, str(backup))[0]
    assert recovered.archive_status == ARCH_RECOVERY_REQUIRED


def test_recovery_invalid_partial_is_not_deleted(tmp_path: Path) -> None:
    from src.ingestion.archive import partial_path
    from src.ingestion.store import save_record, update_record

    root = tmp_path / "proj"
    watch = root / "watch"
    backup = root / "backup"
    watch.mkdir(parents=True)
    backup.mkdir(parents=True)
    pdf = watch / "partial.pdf"
    pdf.write_bytes(b"partial")
    record = _register_watch(root, pdf, watch, backup)
    target = backup / "partial.pdf"
    partial = partial_path(target, record.ingestion_id)
    partial.write_bytes(b"wrong-partial")
    pdf.unlink()
    pending = update_record(
        record,
        processing_status=PROC_DONE,
        planned_archive_path=str(target),
        archive_target=str(target),
        archive_status="PENDING",
    )
    save_record(root, pending)
    recovered = reconcile_archive_recovery(root, str(backup))[0]
    assert partial.is_file()
    assert recovered.archive_status == ARCH_RECOVERY_REQUIRED


def test_source_changed_since_ingest_marks_failed(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    pdf = root / "change.pdf"
    pdf.write_bytes(b"before")
    enqueue_pdf_job(str(root), str(pdf))
    pdf.write_bytes(b"after-change")
    result = process_next_pending(
        root,
        ProcessingConfig(output_mode="both", sqlite_path=str(root / "out.sqlite3")),
        worker_id="w1",
        submit_func=lambda *_a, **_k: JobResult(job_id="x", pdf_path=str(pdf), status="DONE", details={}),
    )
    assert result.queue_status == "FAILED"
    assert "source_changed_since_ingest" in result.message


def test_run_watch_cycle_wraps_ingestion_failures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "proj"
    watch = root / "watch"
    backup = root / "backup"
    watch.mkdir(parents=True)
    backup.mkdir(parents=True)
    services = create_desktop_services(root)
    settings = services.settings.load().__class__(
        output_mode="both",
        sqlite_path=str(root / "db.sqlite3"),
        watch_enabled=True,
        watch_input_path=str(watch),
        watch_backup_path=str(backup),
        device_id=None,
    )
    services.settings.save(settings)

    def boom(*_args, **_kwargs):
        raise IngestionError("recovery_failed")

    monkeypatch.setattr("src.application.extraction_controller.run_watch_scan_cycle", boom)
    with pytest.raises(ApplicationWatchError, match="recovery_failed"):
        services.extraction.run_watch_cycle()


def test_watch_archives_before_validation_and_export_retry_needs_no_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json
    import sqlite3

    from src.jobcontroller.api import release_validated_run, retry_excel_export
    from src.parser.model import ParsedDocument, ParsedPage

    root = tmp_path / "proj"
    watch = root / "watch"
    backup = root / "backup"
    rules = root / "rules"
    watch.mkdir(parents=True)
    backup.mkdir(parents=True)
    rules.mkdir(parents=True)
    (root / "output" / "final").mkdir(parents=True)
    (rules / "index.json").write_text(
        json.dumps({"assays": [{"assay_key": "(1111)", "ruleset_file": "AssayA.json"}]}),
        encoding="utf-8",
    )
    (rules / "AssayA.json").write_text(
        json.dumps(
            {
                "assay_name": "Assay A",
                "assay_key": "(1111)",
                "lot_rule": {"regex": r"Lot:\s*(\w+)"},
                "extract_rules": {
                    "fields": [
                        {"key": "plate_name", "regex": r"Plate:\s*(\w+)", "required": True},
                        {"key": "test", "regex": r"Test:\s*(\w+)", "required": True},
                        {"key": "date", "regex": r"Date:\s*([0-9\-]+)", "required": True},
                        {"key": "time", "regex": r"Time:\s*([0-9:]+)", "required": True},
                    ]
                },
                "excel_rules": {
                    "excel_filename_template": "Frozen.xlsx",
                    "sheetname_template": "{lot_id}",
                    "column_mapping": {},
                },
            }
        ),
        encoding="utf-8",
    )
    pdf = watch / "sample.pdf"
    pdf.write_bytes(b"watch-excel")
    record = _register_watch(root, pdf, watch, backup)
    lines = [
        "Assay A",
        "(1111)",
        "Lot: LOTA",
        "Plate: PLATE1",
        "Test: TESTX",
        "Date: 2026-05-28",
        "Time: 12:00:00",
    ]
    monkeypatch.setattr(
        "src.parser.api.parse",
        lambda path: ParsedDocument(
            source_path=str(path),
            pages=[ParsedPage(page_number=1, lines=lines)],
            meta={"page_count": 1},
        ),
    )
    excel_calls = {"count": 0}
    real_excel = __import__("src.writer.api", fromlist=["write_record"]).write_record

    def excel_twice_then_ok(record_obj, ruleset, output_dir, **kwargs):
        excel_calls["count"] += 1
        if excel_calls["count"] < 3:
            raise RuntimeError("excel down")
        return real_excel(record_obj, ruleset, output_dir, **kwargs)

    monkeypatch.setattr("src.writer.api.write_record", excel_twice_then_ok)
    sqlite_path = root / "output" / "final" / "res.sqlite3"
    config = ProcessingConfig(output_mode="both", sqlite_path=str(sqlite_path), device_id="dev1")

    first = process_next_pending(root, config, worker_id="w-watch")
    assert first.queue_status == "DONE"
    updated = get_import_record(root, record.ingestion_id)
    assert updated is not None
    assert updated.archive_status == ARCH_ARCHIVED
    assert not pdf.is_file()
    with sqlite3.connect(sqlite_path) as conn:
        ids = [row[0] for row in conn.execute("SELECT id FROM runs ORDER BY id")]
    assert len(ids) == 1
    dumps = {
        path.name: path.read_bytes()
        for path in (root / "jobs").glob(f"{record.processing_job_id}*")
        if path.suffix != ".json"
    }

    released = release_validated_run(
        root,
        record.processing_job_id,
        ids[0],
        operator_initials="AB",
        validated_at_utc="2026-09-25T10:00:00+00:00",
        validation_id=1,
    )
    assert released.status == "FAILED"
    from src.application.api import create_desktop_services
    assert create_desktop_services(root).extraction.list_job_diagnoses()[0].retry_kind == "export_only"
    second = retry_excel_export(root, record.processing_job_id)
    assert second.status == "FAILED"
    third = retry_excel_export(root, record.processing_job_id)
    assert third.status == "DONE"
    assert create_desktop_services(root).extraction.list_job_diagnoses() == []
    with sqlite3.connect(sqlite_path) as conn:
        assert [row[0] for row in conn.execute("SELECT id FROM runs ORDER BY id")] == ids
    assert dumps == {
        path.name: path.read_bytes()
        for path in (root / "jobs").glob(f"{record.processing_job_id}*")
        if path.suffix != ".json"
    }


def test_empty_configured_field_keeps_watch_source_and_writes_no_sink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    from src.parser.model import ParsedDocument, ParsedPage

    root = tmp_path / "proj"
    watch = root / "watch"
    backup = root / "backup"
    rules = root / "rules"
    watch.mkdir(parents=True)
    backup.mkdir(parents=True)
    rules.mkdir(parents=True)
    (rules / "index.json").write_text(
        json.dumps({"assays": [{"assay_key": "(1111)", "ruleset_file": "AssayA.json"}]}),
        encoding="utf-8",
    )
    (rules / "AssayA.json").write_text(
        json.dumps(
            {
                "assay_name": "Assay A",
                "assay_key": "(1111)",
                "lot_rule": {"regex": r"Lot:\s*(\w+)"},
                "extract_rules": {
                    "fields": [
                        {"key": "plate_name", "regex": r"Plate:\s*(\w+)", "required": True},
                        {"key": "test", "regex": r"Test:\s*(\w+)", "required": True},
                        {"key": "date", "regex": r"Date:\s*([0-9\-]+)", "required": True},
                        {"key": "time", "regex": r"Time:\s*([0-9:]+)", "required": True},
                        {"key": "note", "regex": r"Note:\s*(\w+)", "required": False},
                    ]
                },
                "excel_rules": {
                    "excel_filename_template": "Frozen.xlsx",
                    "sheetname_template": "{lot_id}",
                    "column_mapping": {},
                },
            }
        ),
        encoding="utf-8",
    )
    pdf = watch / "sample.pdf"
    pdf.write_bytes(b"watch-empty-field")
    record = _register_watch(root, pdf, watch, backup)
    lines = [
        "Assay A",
        "(1111)",
        "Lot: LOTA",
        "Plate: PLATE1",
        "Test: TESTX",
        "Date: 2026-05-28",
        "Time: 12:00:00",
    ]
    monkeypatch.setattr(
        "src.parser.api.parse",
        lambda path: ParsedDocument(
            source_path=str(path),
            pages=[ParsedPage(page_number=1, lines=lines)],
            meta={"page_count": 1},
        ),
    )
    sqlite_path = root / "output" / "final" / "res.sqlite3"
    result = process_next_pending(
        root,
        ProcessingConfig(output_mode="both", sqlite_path=str(sqlite_path), device_id="dev1"),
        worker_id="w-watch",
    )
    assert result.queue_status == "FAILED"
    assert result.message.startswith("configured_fields_empty:")
    assert "note" in result.message
    updated = get_import_record(root, record.ingestion_id)
    assert updated is not None
    assert updated.archive_status != ARCH_ARCHIVED
    assert pdf.is_file()
    assert list(backup.iterdir()) == []
    assert not sqlite_path.exists()
    assert list((root / "output").rglob("*.xlsx")) == []
