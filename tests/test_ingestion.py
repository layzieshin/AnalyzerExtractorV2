from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from src.ingestion.api import (
    IngestionError,
    compute_content_sha256,
    get_import_record,
    list_import_records,
    register_import,
    resolve_current_path,
    validate_watch_path_pair,
)
from src.ingestion.models import ARCH_NOT_REQUIRED, PROC_DONE, SOURCE_MANUAL, SOURCE_WATCH_FOLDER
from src.ingestion.store import IngestionStoreError, load_record_file, save_record, update_record
from src.jobqueue.api import enqueue_pdf_job, list_jobs


def _enqueue(root: Path):
    def enqueue(pdf_path: str, source: str, expected_sha256: str | None):
        return enqueue_pdf_job(str(root), pdf_path, source=source, expected_sha256=expected_sha256)

    return enqueue


def test_record_roundtrip_and_required_fields(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    pdf = root / "a.pdf"
    pdf.write_bytes(b"ledger-test")

    result = register_import(
        root,
        pdf,
        source_kind=SOURCE_MANUAL,
        enqueue=_enqueue(root),
        source_label="manual",
    )
    record = result.record
    assert record.schema_version == 1
    assert record.ingestion_id
    assert record.source_kind == SOURCE_MANUAL
    assert record.original_path
    assert record.current_path == record.original_path
    assert len(record.content_sha256) == 64
    assert record.processing_job_id
    assert record.archive_status == ARCH_NOT_REQUIRED
    assert record.file_fingerprint
    assert record.discovered_at_utc
    assert record.updated_at_utc


def test_corrupt_record_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    store = root / "storage" / "ingestion"
    store.mkdir(parents=True)
    bad = store / "bad.json"
    bad.write_text("{not-json", encoding="utf-8")
    with pytest.raises(IngestionStoreError):
        load_record_file(bad)


def test_same_path_idempotent(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    pdf = root / "same.pdf"
    pdf.write_bytes(b"same-content")
    enqueue = _enqueue(root)
    first = register_import(root, pdf, source_kind=SOURCE_MANUAL, enqueue=enqueue, source_label="manual")
    second = register_import(root, pdf, source_kind=SOURCE_MANUAL, enqueue=enqueue, source_label="manual")
    assert first.created is True
    assert second.created is False
    assert len(list_jobs(str(root))) == 1
    assert len(list_import_records(root)) == 1


def test_same_bytes_two_paths_two_imports_one_job(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    pdf_a = root / "a.pdf"
    pdf_b = root / "b.pdf"
    content = b"shared-bytes"
    pdf_a.write_bytes(content)
    pdf_b.write_bytes(content)
    enqueue = _enqueue(root)
    first = register_import(root, pdf_a, source_kind=SOURCE_WATCH_FOLDER, enqueue=enqueue, source_label="watch")
    second = register_import(
        root,
        pdf_b,
        source_kind=SOURCE_WATCH_FOLDER,
        enqueue=enqueue,
        source_label="watch",
        watch_input_path=str(root / "watch"),
        watch_backup_path=str(root / "backup"),
    )
    assert first.record.ingestion_id != second.record.ingestion_id
    assert first.record.processing_job_id == second.record.processing_job_id
    assert len(list_jobs(str(root))) == 1
    assert len(list_import_records(root)) == 2


def test_changed_content_new_generation(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    pdf = root / "gen.pdf"
    pdf.write_bytes(b"v1")
    enqueue = _enqueue(root)
    first = register_import(root, pdf, source_kind=SOURCE_MANUAL, enqueue=enqueue, source_label="manual")
    pdf.write_bytes(b"v2-changed")
    second = register_import(root, pdf, source_kind=SOURCE_MANUAL, enqueue=enqueue, source_label="manual")
    assert first.record.ingestion_id != second.record.ingestion_id
    assert first.record.processing_job_id != second.record.processing_job_id


def test_hash_stable_pdf_detects_content_change(tmp_path: Path) -> None:
    from src.ingestion.api import hash_stable_pdf

    pdf = tmp_path / "race.pdf"
    pdf.write_bytes(b"before")
    first_hash, _, _ = hash_stable_pdf(pdf)
    pdf.write_bytes(b"after")
    second_hash, _, _ = hash_stable_pdf(pdf)
    assert first_hash != second_hash


def test_validate_watch_paths_rejects_overlap(tmp_path: Path) -> None:
    watch = tmp_path / "watch"
    backup = watch / "backup"
    watch.mkdir()
    backup.mkdir()
    with pytest.raises(IngestionError, match="watch_backup_under_input"):
        validate_watch_path_pair(str(watch), str(backup))


def test_manual_import_never_archives(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    pdf = root / "manual.pdf"
    pdf.write_bytes(b"manual")
    record = register_import(
        root,
        pdf,
        source_kind=SOURCE_MANUAL,
        enqueue=_enqueue(root),
        source_label="manual",
    ).record
    assert record.archive_status == ARCH_NOT_REQUIRED
    assert Path(record.current_path).is_file()


def test_old_queue_json_without_content_sha256_still_readable(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    queue = root / "jobs" / "queue"
    queue.mkdir(parents=True)
    payload = {
        "job_id": "abc123",
        "pdf_path": str(root / "old.pdf"),
        "status": "PENDING",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "source": "legacy",
        "worker_id": "",
        "attempts": 0,
        "last_error": "",
    }
    (root / "old.pdf").write_bytes(b"legacy")
    (queue / "abc123.json").write_text(json.dumps(payload), encoding="utf-8")
    jobs = list_jobs(str(root))
    assert jobs[0].content_sha256 == ""


def test_resolve_current_path_legacy_and_exact_match(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    pdf = root / "run.pdf"
    pdf.write_bytes(b"run")
    record = register_import(
        root,
        pdf,
        source_kind=SOURCE_WATCH_FOLDER,
        enqueue=_enqueue(root),
        source_label="watch",
        watch_input_path=str(root / "watch"),
        watch_backup_path=str(root / "backup"),
    ).record
    claimed = resolve_current_path(root, record.processing_job_id, str(pdf))
    assert claimed.path_status == "resolved"
    assert claimed.ingestion_id == record.ingestion_id

    legacy = resolve_current_path(root, "missing-job", str(pdf))
    assert legacy.path_status == "legacy_fallback"


def test_resolve_current_path_ambiguous_when_multiple_records(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    pdf = root / "dup-path.pdf"
    pdf.write_bytes(b"x")
    record_a = register_import(
        root,
        pdf,
        source_kind=SOURCE_MANUAL,
        enqueue=_enqueue(root),
        source_label="manual",
    ).record
    duplicate = update_record(record_a, ingestion_id=str(uuid.uuid4()))
    save_record(root, duplicate)
    resolution = resolve_current_path(root, record_a.processing_job_id, str(pdf))
    assert resolution.path_status == "ambiguous"


def test_get_import_record_roundtrip(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    pdf = root / "get.pdf"
    pdf.write_bytes(b"get")
    created = register_import(
        root,
        pdf,
        source_kind=SOURCE_MANUAL,
        enqueue=_enqueue(root),
        source_label="manual",
    ).record
    loaded = get_import_record(root, created.ingestion_id)
    assert loaded is not None
    assert loaded.ingestion_id == created.ingestion_id


def test_done_job_reconciles_processing_status(tmp_path: Path) -> None:
    from src.ingestion.api import reconcile_processing_for_job

    root = tmp_path / "proj"
    root.mkdir()
    pdf = root / "done.pdf"
    pdf.write_bytes(b"done")
    record = register_import(
        root,
        pdf,
        source_kind=SOURCE_MANUAL,
        enqueue=_enqueue(root),
        source_label="manual",
    ).record
    updated = reconcile_processing_for_job(root, record.processing_job_id, "DONE")[0]
    assert updated.processing_status == PROC_DONE


def test_list_records_raises_on_corrupt_json(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    store = root / "storage" / "ingestion"
    store.mkdir(parents=True)
    (store / "broken.json").write_text("{bad", encoding="utf-8")
    with pytest.raises(IngestionStoreError, match="corrupt_record"):
        list_import_records(root)


def test_register_import_raises_on_corrupt_ledger(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    store = root / "storage" / "ingestion"
    store.mkdir(parents=True)
    (store / "broken.json").write_text("{bad", encoding="utf-8")
    pdf = root / "x.pdf"
    pdf.write_bytes(b"x")
    with pytest.raises(IngestionStoreError):
        register_import(
            root,
            pdf,
            source_kind=SOURCE_MANUAL,
            enqueue=_enqueue(root),
            source_label="manual",
        )
    assert len(list_jobs(str(root))) == 0


def test_reconcile_raises_on_invalid_processing_status(tmp_path: Path) -> None:
    from src.ingestion.api import reconcile_archive_recovery, reconcile_processing_for_job

    root = tmp_path / "proj"
    root.mkdir()
    pdf = root / "bad-status.pdf"
    pdf.write_bytes(b"x")
    record = register_import(
        root,
        pdf,
        source_kind=SOURCE_WATCH_FOLDER,
        enqueue=_enqueue(root),
        source_label="watch",
        watch_input_path=str(root / "watch"),
        watch_backup_path=str(root / "backup"),
    ).record
    record_path = root / "storage" / "ingestion" / f"{record.ingestion_id}.json"
    payload = json.loads(record_path.read_text(encoding="utf-8"))
    payload["processing_status"] = "BROKEN"
    record_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(IngestionStoreError, match="invalid_processing_status"):
        reconcile_processing_for_job(root, record.processing_job_id, "DONE")
    with pytest.raises(IngestionStoreError, match="invalid_processing_status"):
        reconcile_archive_recovery(root, str(root / "backup"))


def test_observe_stable_pdfs_timing_sequence_and_reset(tmp_path: Path) -> None:
    from src.ingestion.api import StabilityScannerState, observe_stable_pdfs

    watch = tmp_path / "watch"
    watch.mkdir()
    pdf = watch / "timing.pdf"
    pdf.write_bytes(b"timing")
    state = StabilityScannerState()

    assert observe_stable_pdfs(watch, stable_window_s=1.0, state=state, now=0.0) == []
    assert observe_stable_pdfs(watch, stable_window_s=1.0, state=state, now=0.4) == []
    assert observe_stable_pdfs(watch, stable_window_s=1.0, state=state, now=0.8) == []
    stable = observe_stable_pdfs(watch, stable_window_s=1.0, state=state, now=1.2)
    assert [str(pdf.resolve())] == [str(p.resolve()) for p in stable]

    pdf.write_bytes(b"timing-changed")
    assert observe_stable_pdfs(watch, stable_window_s=1.0, state=state, now=2.0) == []
    assert observe_stable_pdfs(watch, stable_window_s=1.0, state=state, now=3.1) == [pdf]


def test_validate_watch_paths_rejects_case_and_parent_child(tmp_path: Path) -> None:
    watch = tmp_path / "Watch"
    backup = tmp_path / "watch" / "backup"
    watch.mkdir()
    backup.mkdir(parents=True)
    with pytest.raises(IngestionError, match="watch_backup_under_input"):
        validate_watch_path_pair(str(watch), str(backup))

    nested = tmp_path / "outer" / "inner"
    nested.mkdir(parents=True)
    with pytest.raises(IngestionError, match="watch_input_under_backup"):
        validate_watch_path_pair(str(nested), str(tmp_path / "outer"))

    file_input = tmp_path / "file-input.txt"
    file_input.write_text("x", encoding="utf-8")
    backup_dir = tmp_path / "backup-flat"
    with pytest.raises(IngestionError, match="watch_input_not_directory"):
        validate_watch_path_pair(str(file_input), str(backup_dir))
    assert not backup_dir.exists()


def test_parallel_same_path_registration_is_single_record(tmp_path: Path) -> None:
    import threading

    root = tmp_path / "proj"
    root.mkdir()
    pdf = root / "parallel.pdf"
    pdf.write_bytes(b"parallel")
    enqueue = _enqueue(root)
    results: list = []
    errors: list[Exception] = []

    def worker() -> None:
        try:
            results.append(
                register_import(
                    root,
                    pdf,
                    source_kind=SOURCE_MANUAL,
                    enqueue=enqueue,
                    source_label="manual",
                )
            )
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors
    assert len({item.record.ingestion_id for item in results}) == 1
    assert len(list_jobs(str(root))) == 1


def test_run_watch_scan_cycle_honors_recursive_flag(tmp_path: Path, monkeypatch) -> None:
    from src.ingestion.api import run_watch_scan_cycle
    from src.ingestion.models import StabilityScannerState

    root = tmp_path / "proj"
    watch = root / "watch"
    backup = root / "backup"
    nested = watch / "nested"
    nested.mkdir(parents=True)
    backup.mkdir()
    nested_pdf = nested / "deep.pdf"
    nested_pdf.write_bytes(b"deep")
    calls: list[bool] = []

    def fake_observe_stable_pdfs(_watch_dir, **kwargs):
        calls.append(bool(kwargs.get("recursive")))
        return []

    monkeypatch.setattr("src.ingestion.service.observe_stable_pdfs", fake_observe_stable_pdfs)
    run_watch_scan_cycle(
        root,
        watch_input_path=str(watch),
        watch_backup_path=str(backup),
        stable_window_s=0.0,
        enqueue=_enqueue(root),
        state=StabilityScannerState(),
        recursive=True,
    )
    assert calls == [True]
