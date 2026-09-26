from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.application.api import (
    ExtractionController,
    ProcessingOutcome,
    create_desktop_services,
    map_ingestion_display_status,
)
from src.jobcontroller.model import JobResult
from src.jobqueue.api import enqueue_pdf_job, list_jobs


def test_enqueue_manual_pdfs_preserves_per_file_outcomes(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    good = root / "good.pdf"
    good.write_bytes(b"good")
    missing = root / "missing.pdf"

    services = create_desktop_services(root)
    third = root / "third.pdf"
    third.write_bytes(b"third")
    summary = services.extraction.enqueue_manual_pdfs([str(good), str(missing), str(third)])

    assert summary.queued == 2
    assert summary.skipped == 0
    assert summary.errors == 1
    assert len(summary.outcomes) == 3

    assert summary.outcomes[0].pdf_path == str(good)
    assert summary.outcomes[0].file_name == "good.pdf"
    assert summary.outcomes[0].outcome == "queued"
    assert summary.outcomes[0].job_id

    assert summary.outcomes[1].pdf_path == str(missing)
    assert summary.outcomes[1].file_name == "missing.pdf"
    assert summary.outcomes[1].outcome == "error"
    assert "pdf_not_found" in summary.outcomes[1].message

    assert summary.outcomes[2].pdf_path == str(third)
    assert summary.outcomes[2].outcome == "queued"

    jobs = list_jobs(str(root))
    assert len(jobs) == 2
    assert jobs[0].source == "test-app-manual"


def test_enqueue_manual_pdfs_reports_skipped_duplicate(tmp_path: Path) -> None:
    from src.jobqueue.api import claim_next_job, mark_job_done

    root = tmp_path / "proj"
    root.mkdir()
    pdf = root / "dup.pdf"
    pdf.write_bytes(b"dup-content")
    existing = enqueue_pdf_job(str(root), str(pdf), source="test-app-manual")
    claimed = claim_next_job(str(root), "w-test")
    assert claimed is not None
    mark_job_done(str(root), claimed.job_id, worker_id="w-test")

    services = create_desktop_services(root)
    summary = services.extraction.enqueue_manual_pdfs([str(pdf)])

    assert summary.queued == 0
    assert summary.skipped == 1
    assert summary.errors == 0
    assert summary.outcomes[0].outcome == "skipped"
    assert summary.outcomes[0].pdf_path == str(pdf)
    assert summary.outcomes[0].file_name == "dup.pdf"
    assert summary.outcomes[0].job_id


def test_list_processing_items_maps_dto_fields(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    pdf = root / "dto.pdf"
    pdf.write_bytes(b"dto")
    enqueue_pdf_job(str(root), str(pdf), source="test-app-manual")

    items = create_desktop_services(root).extraction.list_processing_items()
    assert len(items) == 1
    item = items[0]
    assert item.job_id
    assert item.pdf_path == str(pdf)
    assert item.file_name == "dto.pdf"
    assert item.status == "PENDING"
    assert item.source == "test-app-manual"
    assert item.attempts == 0
    assert item.created_at
    assert item.updated_at


def test_process_next_uses_injected_fake_submit(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    pdf = root / "work.pdf"
    pdf.write_bytes(b"work")
    job = enqueue_pdf_job(str(root), str(pdf), source="test-app-manual")

    calls: list[dict[str, object]] = []

    def fake_submit(*_args, **kwargs) -> JobResult:
        calls.append(dict(kwargs))
        return JobResult(
            job_id=job.job_id,
            pdf_path=str(pdf),
            status="FAILED",
            details={"error": "fake-boom"},
        )

    settings = create_desktop_services(root).settings
    controller = ExtractionController(root, settings_provider=settings.load, submit_func=fake_submit)
    result = controller.process_next()

    assert calls
    assert calls[0]["output_mode"] == "both"
    assert isinstance(result, ProcessingOutcome)
    assert result.queue_status == "FAILED"
    assert result.message == "fake-boom"
    assert result.file_name == "work.pdf"

    retried = controller.retry_failed(job.job_id)
    assert retried.status == "PENDING"


def test_process_next_uses_updated_settings_without_service_rebuild(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    pdf = root / "settings.pdf"
    pdf.write_bytes(b"settings")
    enqueue_pdf_job(str(root), str(pdf), source="test-app-manual")

    services = create_desktop_services(root)
    new_db = root / "updated.sqlite3"
    services.settings.save(
        services.settings.load().__class__(
            output_mode="sqlite",
            sqlite_path=str(new_db),
            watch_input_path=str(root / "input" / "watch"),
            device_id="analyzer_i_9",
        )
    )

    captured_configs: list[object] = []

    def fake_process_next(_root, config, **kwargs):
        captured_configs.append(config)
        return type(
            "ProcessingResult",
            (),
            {
                "processed": True,
                "job_id": "job",
                "pdf_path": str(pdf),
                "queue_status": "FAILED",
                "submit_status": "FAILED",
                "message": "stop",
            },
        )()

    monkeypatch.setattr("src.application.extraction_controller.process_next_pending", fake_process_next)
    result = services.extraction.process_next()

    assert len(captured_configs) == 1
    config = captured_configs[0]
    assert config.output_mode == "sqlite"
    assert config.sqlite_path == str(new_db)
    assert config.device_id == "analyzer_i_9"
    assert result.message == "stop"


def test_map_ingestion_display_status_contract() -> None:
    assert map_ingestion_display_status("PENDING", "NOT_REQUIRED") == "Wartet"
    assert map_ingestion_display_status("PROCESSING", "NOT_REQUIRED") == "Wird verarbeitet"
    assert map_ingestion_display_status("DONE", "PENDING") == "Verarbeitet - wird archiviert"
    assert map_ingestion_display_status("DONE", "ARCHIVED") == "Fertig"
    assert map_ingestion_display_status("FAILED", "NOT_REQUIRED") == "Verarbeitung fehlgeschlagen"
    assert map_ingestion_display_status("DONE", "ARCHIVE_FAILED") == "Verarbeitet - Archivierung fehlgeschlagen"
    assert map_ingestion_display_status("DONE", "RECOVERY_REQUIRED") == "Klaerung erforderlich"


def test_list_ingestion_instances_merges_queue_and_ledger(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    pdf = root / "merge.pdf"
    pdf.write_bytes(b"merge")
    services = create_desktop_services(root)
    services.extraction.enqueue_manual_pdfs([str(pdf)])

    items = services.extraction.list_ingestion_instances()
    assert len(items) == 1
    item = items[0]
    assert item.ingestion_id
    assert item.job_id
    assert item.display_status == "Wartet"
    assert item.queue_only is False


def test_list_ingestion_instances_includes_queue_only_fallback(tmp_path: Path) -> None:
    from src.jobqueue.api import enqueue_pdf_job

    root = tmp_path / "proj"
    root.mkdir()
    pdf = root / "queue-only.pdf"
    pdf.write_bytes(b"queue-only")
    enqueue_pdf_job(str(root), str(pdf), source="legacy")

    items = create_desktop_services(root).extraction.list_ingestion_instances()
    assert len(items) == 1
    assert items[0].queue_only is True
    assert items[0].ingestion_id == ""
    assert items[0].display_status == "Wartet"


def test_get_job_diagnosis_for_rule_relevant_failure(tmp_path: Path) -> None:
    import json

    from src.jobqueue.api import claim_next_job, enqueue_pdf_job, mark_job_failed

    root = tmp_path / "proj"
    root.mkdir()
    (root / "jobs").mkdir()
    pdf = root / "fail.pdf"
    pdf.write_bytes(b"fail")
    job = enqueue_pdf_job(str(root), str(pdf), source="test-app-manual")
    claimed = claim_next_job(str(root), "w-test")
    assert claimed is not None
    mark_job_failed(str(root), job.job_id, worker_id="w-test", error="no_assay_detected")
    normalized = root / "jobs" / f"{job.job_id}_normalized.txt"
    normalized.write_text("normalized", encoding="utf-8")
    (root / "jobs" / f"{job.job_id}.json").write_text(
        json.dumps(
            {
                "job_id": job.job_id,
                "pdf_path": str(pdf),
                "status": "FAILED",
                "error": "no_assay_detected",
                "steps": [{"step": "debug", "normalized_dump": str(normalized)}],
            }
        ),
        encoding="utf-8",
    )

    diagnosis = create_desktop_services(root).extraction.get_job_diagnosis(job.job_id)
    assert diagnosis is not None
    assert diagnosis.error_label == "Assay nicht erkannt"
    assert diagnosis.context_label == "Normalisierter Text"
    assert diagnosis.friendly_message
    assert diagnosis.context_available is True
    assert "normalized" in diagnosis.context_text


def test_get_job_diagnosis_classifies_excel_output_after_save(tmp_path: Path) -> None:
    import json

    from src.jobqueue.api import claim_next_job, enqueue_pdf_job, mark_job_failed

    root = tmp_path / "proj"
    root.mkdir()
    (root / "jobs").mkdir()
    pdf = root / "excel.pdf"
    pdf.write_bytes(b"excel")
    job = enqueue_pdf_job(str(root), str(pdf), source="test-app-manual")
    claimed = claim_next_job(str(root), "w-test")
    assert claimed is not None
    technical = "excel_write_failed_after_save:(1111):disk full"
    mark_job_failed(str(root), job.job_id, worker_id="w-test", error=technical)
    (root / "jobs" / f"{job.job_id}.json").write_text(
        json.dumps({"job_id": job.job_id, "pdf_path": str(pdf), "status": "FAILED", "error": technical, "steps": []}),
        encoding="utf-8",
    )

    diagnosis = create_desktop_services(root).extraction.get_job_diagnosis(job.job_id)
    assert diagnosis is not None
    assert diagnosis.error_label == "Excel-Ausgabe"
    assert diagnosis.friendly_message == "Ergebnis gespeichert – Excel-Ausgabe fehlgeschlagen"
    assert diagnosis.technical_detail == technical

    excel_only = "excel_write_failed:(1111):disk full"
    assert create_desktop_services(root).extraction.get_job_diagnosis(job.job_id).error_label == "Excel-Ausgabe"
    from src.application.api import friendly_processing_message

    assert friendly_processing_message(excel_only) == "Excel-Ausgabe fehlgeschlagen"


def test_done_queue_job_exposes_export_only_excel_diagnosis(tmp_path: Path) -> None:
    from src.jobqueue.api import claim_next_job, enqueue_pdf_job, mark_job_done

    root = tmp_path / "proj"
    root.mkdir()
    pdf = root / "archived-away.pdf"
    pdf.write_bytes(b"excel")
    job = enqueue_pdf_job(str(root), str(pdf), source="test-app-manual")
    assert claim_next_job(str(root), "w-test") is not None
    mark_job_done(str(root), job.job_id, worker_id="w-test")
    pdf.unlink()
    technical = "excel_write_failed_after_validation:(1111):disk full"
    (root / "jobs" / f"{job.job_id}.json").write_text(
        json.dumps(
            {
                "job_id": job.job_id,
                "pdf_path": str(pdf),
                "status": "DONE",
                "error": technical,
                "excel_status": "failed",
                "export_retry_available": True,
                "steps": [],
            }
        ),
        encoding="utf-8",
    )

    diagnoses = create_desktop_services(root).extraction.list_job_diagnoses()
    assert len(diagnoses) == 1
    assert diagnoses[0].queue_status == "DONE"
    assert diagnoses[0].retry_kind == "export_only"
    assert diagnoses[0].friendly_message == "Validierung gespeichert – Excel-Ausgabe fehlgeschlagen"


def test_get_job_diagnosis_uses_block_label_when_normalized_dump_empty(tmp_path: Path) -> None:
    import json

    from src.jobqueue.api import claim_next_job, enqueue_pdf_job, mark_job_failed

    root = tmp_path / "proj"
    root.mkdir()
    (root / "jobs").mkdir()
    pdf = root / "fail.pdf"
    pdf.write_bytes(b"fail")
    job = enqueue_pdf_job(str(root), str(pdf), source="test-app-manual")
    claimed = claim_next_job(str(root), "w-test")
    assert claimed is not None
    mark_job_failed(str(root), job.job_id, worker_id="w-test", error="no_assay_detected")
    normalized = root / "jobs" / f"{job.job_id}_normalized.txt"
    normalized.write_text("", encoding="utf-8")
    block_dump = root / "jobs" / f"{job.job_id}_block.txt"
    block_dump.write_text("block-content", encoding="utf-8")
    (root / "jobs" / f"{job.job_id}.json").write_text(
        json.dumps(
            {
                "job_id": job.job_id,
                "pdf_path": str(pdf),
                "status": "FAILED",
                "error": "no_assay_detected",
                "steps": [
                    {
                        "step": "debug",
                        "normalized_dump": str(normalized),
                        "block_dumps": {"(1111)": str(block_dump)},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    diagnosis = create_desktop_services(root).extraction.get_job_diagnosis(job.job_id)
    assert diagnosis is not None
    assert diagnosis.context_label == "Assay-Block (1111)"
    assert "block-content" in diagnosis.context_text


def test_get_job_diagnosis_classifies_empty_configured_fields(tmp_path: Path) -> None:
    import json

    from src.jobqueue.api import claim_next_job, enqueue_pdf_job, mark_job_failed

    root = tmp_path / "proj"
    root.mkdir()
    (root / "jobs").mkdir()
    pdf = root / "empty-fields.pdf"
    pdf.write_bytes(b"empty-fields")
    job = enqueue_pdf_job(str(root), str(pdf), source="test-app-manual")
    claimed = claim_next_job(str(root), "w-test")
    assert claimed is not None
    technical = "configured_fields_empty: note,comment"
    mark_job_failed(str(root), job.job_id, worker_id="w-test", error=technical)
    (root / "jobs" / f"{job.job_id}.json").write_text(
        json.dumps(
            {
                "job_id": job.job_id,
                "pdf_path": str(pdf),
                "status": "FAILED",
                "error": technical,
                "steps": [],
            }
        ),
        encoding="utf-8",
    )

    diagnosis = create_desktop_services(root).extraction.get_job_diagnosis(job.job_id)
    assert diagnosis is not None
    assert diagnosis.error_label == "Felder nicht extrahiert"
    assert diagnosis.friendly_message == "Felder nicht extrahiert"
    assert diagnosis.technical_detail == technical
    assert diagnosis.root_error == technical


def test_ingestion_display_uses_queue_status_when_present(tmp_path: Path) -> None:
    import json

    from src.jobqueue.api import claim_next_job, enqueue_pdf_job

    root = tmp_path / "proj"
    root.mkdir()
    (root / "storage" / "ingestion").mkdir(parents=True)
    pdf = root / "queue.pdf"
    pdf.write_bytes(b"queue")
    job = enqueue_pdf_job(str(root), str(pdf), source="test-app-manual")
    claimed = claim_next_job(str(root), "w-test")
    assert claimed is not None

    services = create_desktop_services(root)
    services.extraction.enqueue_manual_pdfs([str(pdf)])
    record = services.extraction.list_import_records()[0]
    ledger_path = root / "storage" / "ingestion" / f"{record.ingestion_id}.json"
    payload = json.loads(ledger_path.read_text(encoding="utf-8"))
    payload["processing_status"] = "PENDING"
    ledger_path.write_text(json.dumps(payload), encoding="utf-8")

    item = services.extraction.get_ingestion_instance(record.ingestion_id)
    assert item is not None
    assert item.processing_status == "PENDING"
    assert item.queue_status == "PROCESSING"
    assert item.display_status == "Wird verarbeitet"


def test_ingestion_display_prefers_terminal_queue_done(tmp_path: Path) -> None:
    import json

    from src.jobqueue.api import claim_next_job, enqueue_pdf_job, mark_job_done

    root = tmp_path / "proj"
    root.mkdir()
    pdf = root / "done.pdf"
    pdf.write_bytes(b"done")
    job = enqueue_pdf_job(str(root), str(pdf), source="test-app-manual")
    claimed = claim_next_job(str(root), "w-test")
    assert claimed is not None
    mark_job_done(str(root), job.job_id, worker_id="w-test")

    services = create_desktop_services(root)
    services.extraction.enqueue_manual_pdfs([str(pdf)])
    record = services.extraction.list_import_records()[0]
    ledger_path = root / "storage" / "ingestion" / f"{record.ingestion_id}.json"
    payload = json.loads(ledger_path.read_text(encoding="utf-8"))
    payload["processing_status"] = "PENDING"
    ledger_path.write_text(json.dumps(payload), encoding="utf-8")

    item = services.extraction.get_ingestion_instance(record.ingestion_id)
    assert item is not None
    assert item.queue_status == "DONE"
    assert item.display_status == "Fertig"


def test_two_ingestion_instances_keep_distinct_archive_states(tmp_path: Path) -> None:
    from src.ingestion.api import SOURCE_WATCH_FOLDER, register_import
    from src.jobqueue.api import enqueue_pdf_job

    root = tmp_path / "proj"
    root.mkdir()
    content = b"shared"
    pdf_a = root / "a.pdf"
    pdf_b = root / "b.pdf"
    pdf_a.write_bytes(content)
    pdf_b.write_bytes(content)

    def enqueue(pdf_path: str, source: str, expected_sha256: str | None):
        return enqueue_pdf_job(str(root), pdf_path, source=source, expected_sha256=expected_sha256)

    first = register_import(
        root,
        pdf_a,
        source_kind=SOURCE_WATCH_FOLDER,
        enqueue=enqueue,
        source_label="watch",
        watch_input_path=str(root / "watch"),
        watch_backup_path=str(root / "backup"),
    ).record
    second = register_import(
        root,
        pdf_b,
        source_kind=SOURCE_WATCH_FOLDER,
        enqueue=enqueue,
        source_label="watch",
        watch_input_path=str(root / "watch"),
        watch_backup_path=str(root / "backup"),
    ).record
    assert first.processing_job_id == second.processing_job_id

    from src.jobqueue.api import claim_next_job, mark_job_done

    claimed = claim_next_job(str(root), "w-archive")
    assert claimed is not None
    mark_job_done(str(root), first.processing_job_id, worker_id="w-archive")

    services = create_desktop_services(root)
    ledger_a = root / "storage" / "ingestion" / f"{first.ingestion_id}.json"
    ledger_b = root / "storage" / "ingestion" / f"{second.ingestion_id}.json"
    import json

    payload_a = json.loads(ledger_a.read_text(encoding="utf-8"))
    payload_b = json.loads(ledger_b.read_text(encoding="utf-8"))
    payload_a["archive_status"] = "ARCHIVED"
    payload_b["archive_status"] = "PENDING"
    payload_a["processing_status"] = "DONE"
    payload_b["processing_status"] = "DONE"
    ledger_a.write_text(json.dumps(payload_a), encoding="utf-8")
    ledger_b.write_text(json.dumps(payload_b), encoding="utf-8")

    item_a = services.extraction.get_ingestion_instance(first.ingestion_id)
    item_b = services.extraction.get_ingestion_instance(second.ingestion_id)
    assert item_a is not None and item_b is not None
    assert item_a.job_id == item_b.job_id
    assert item_a.archive_status == "ARCHIVED"
    assert item_b.archive_status == "PENDING"
    assert item_a.display_status != item_b.display_status


def test_run_watch_cycle_uses_runtime_stable_window_when_omitted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (tmp_path / "watch").mkdir()
    (tmp_path / "backup").mkdir()
    monkeypatch.setenv("ARE_WATCH_STABLE_WINDOW_S", "2.5")
    services = create_desktop_services(root)
    settings = services.settings.load()
    services.settings.save(
        settings.__class__(
            output_mode=settings.output_mode,
            sqlite_path=settings.sqlite_path,
            watch_enabled=True,
            watch_input_path=str(tmp_path / "watch"),
            watch_backup_path=str(tmp_path / "backup"),
            device_id=settings.device_id,
        )
    )
    captured: list[float] = []

    def fake_cycle(*_args, **kwargs):
        captured.append(float(kwargs["stable_window_s"]))
        from src.ingestion.models import WatchCycleResult

        return WatchCycleResult(enabled=True, scanned_count=0, outcomes=())

    monkeypatch.setattr("src.application.extraction_controller.run_watch_scan_cycle", fake_cycle)
    services.extraction.run_watch_cycle()
    assert captured == [2.5]


def test_run_watch_cycle_forwards_recursive_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (tmp_path / "watch").mkdir()
    (tmp_path / "backup").mkdir()
    services = create_desktop_services(root)
    settings = services.settings.load()
    services.settings.save(
        settings.__class__(
            output_mode=settings.output_mode,
            sqlite_path=settings.sqlite_path,
            watch_enabled=True,
            watch_input_path=str(tmp_path / "watch"),
            watch_backup_path=str(tmp_path / "backup"),
            watch_recursive=True,
            device_id=settings.device_id,
        )
    )
    captured: list[bool] = []

    def fake_cycle(*_args, **kwargs):
        captured.append(bool(kwargs["recursive"]))
        from src.ingestion.models import WatchCycleResult

        return WatchCycleResult(enabled=True, scanned_count=0, outcomes=())

    monkeypatch.setattr("src.application.extraction_controller.run_watch_scan_cycle", fake_cycle)
    services.extraction.run_watch_cycle(stable_window_s=0.0)
    assert captured == [True]
