import json
from pathlib import Path

import pytest

from src.application.api import DesktopSettings, SettingsController, ExtractionController
from src.ingestion.api import list_import_records, reconcile_processing_for_job, retry_archive
from src.runtime.api import load_runtime_config
from src.watchdog.api import scan_watch_once


def test_monthly_settings_roundtrip_without_backup_or_watch_and_legacy_default(tmp_path):
    settings = SettingsController(tmp_path)
    assert settings.load().archive_mode == "immediate"
    incoming = tmp_path / "Result"
    incoming.mkdir()
    saved = settings.save(DesktopSettings("sqlite", str(tmp_path / "db.sqlite3"),
        archive_mode="monthly", watch_enabled=True, watch_input_path=str(incoming), watch_recursive=True))
    assert saved.archive_mode == settings.load().archive_mode == "monthly"
    assert json.loads(settings.settings_path().read_text())["archive_mode"] == "monthly"
    settings.save(DesktopSettings("sqlite", str(tmp_path / "db.sqlite3"), archive_mode="monthly", watch_enabled=False))
    assert not settings.load().watch_enabled


def test_monthly_watch_keeps_sources_and_ignores_years_even_with_recursive_setting(tmp_path):
    incoming = tmp_path / "Result"
    incoming.mkdir()
    loose = incoming / "loose.pdf"
    loose.write_bytes(b"synthetic current source")
    archived = incoming / "2026/11_November"
    archived.mkdir(parents=True)
    (archived / "old.pdf").write_bytes(b"do not scan archive")
    settings = DesktopSettings("sqlite", str(tmp_path / "db.sqlite3"), archive_mode="monthly",
        watch_enabled=True, watch_input_path=str(incoming), watch_recursive=True)
    extraction = ExtractionController(tmp_path, settings_provider=lambda: settings)
    cycle = extraction.run_watch_cycle(stable_window_s=0)
    assert cycle.scanned_count == 1
    records = list_import_records(tmp_path)
    assert len(records) == 1 and records[0].archive_mode == "monthly" and records[0].archive_status == "NOT_REQUIRED"
    reconcile_processing_for_job(tmp_path, records[0].processing_job_id, "DONE")
    record = list_import_records(tmp_path)[0]
    assert record.current_path == record.original_path and not record.planned_archive_path
    assert loose.exists() and (archived / "old.pdf").exists()
    with pytest.raises(Exception, match="Monatsmodus"):
        retry_archive(tmp_path, record.ingestion_id)


def test_headless_monthly_env_uses_same_flat_registration_without_backup(tmp_path, monkeypatch):
    incoming = tmp_path / "Result"
    incoming.mkdir()
    pdf = incoming / "a.pdf"
    pdf.write_bytes(b"standalone source")
    monkeypatch.setenv("ARE_ARCHIVE_MODE", "monthly")
    assert load_runtime_config(tmp_path).archive_mode == "monthly"
    assert SettingsController(tmp_path).load().archive_mode == "monthly"
    assert len(scan_watch_once(str(tmp_path), str(incoming), stable_window_s=0)) == 1
    assert list_import_records(tmp_path)[0].archive_mode == "monthly" and pdf.exists()


def test_preexisting_immediate_import_keeps_original_confirmed_route_after_mode_switch(tmp_path):
    from src.ingestion.api import SOURCE_WATCH_FOLDER, register_import
    from src.jobqueue.api import enqueue_pdf_job
    incoming, backup = tmp_path / "incoming", tmp_path / "old-confirmed-backup"
    incoming.mkdir()
    backup.mkdir()
    pdf = incoming / "original.pdf"
    pdf.write_bytes(b"old registered source")
    result = register_import(tmp_path, pdf, source_kind=SOURCE_WATCH_FOLDER, watch_input_path=str(incoming),
        watch_backup_path=str(backup), enqueue=lambda path, source, expected: enqueue_pdf_job(str(tmp_path), path, source=source, expected_sha256=expected))
    settings = DesktopSettings("sqlite", str(tmp_path / "db.sqlite3"), archive_mode="monthly", watch_enabled=True, watch_input_path=str(incoming))
    ExtractionController(tmp_path, settings_provider=lambda: settings).run_watch_cycle(stable_window_s=0)
    old = list_import_records(tmp_path)[0]
    assert old.ingestion_id == result.record.ingestion_id and old.archive_mode == "immediate" and old.watch_backup_path == str(backup)
    reconcile_processing_for_job(tmp_path, old.processing_job_id, "DONE")
    assert not pdf.exists() and (backup / pdf.name).exists()
