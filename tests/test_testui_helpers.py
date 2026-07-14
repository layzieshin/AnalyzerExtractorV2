from src.testui.helpers import (
    build_rework_items,
    classify_job_outcome,
    filter_rework_items,
    format_assay_data_detail,
    format_assay_overview_rows,
    format_device_choice,
    format_duplicate_candidate_detail,
    format_duplicate_candidate_summary,
    format_duplicate_field_comparison,
    format_enqueue_result,
    format_extractor_error_label,
    format_extractor_file_row,
    format_job_result_summary,
    format_partial_writes_note,
    format_queue_job_row,
    format_rework_context_text,
    format_rework_item_detail,
    format_rework_item_summary,
    format_rules_report,
    format_runtime_options_summary,
    format_submit_row_update,
    format_validation_status,
    format_watch_file_row,
    format_write_outputs,
    format_write_status_lines,
    humanize_job_error,
    merge_file_rows_with_queue,
    normalize_file_row_key,
)


class _QueueLike:
    job_id = "j1"
    pdf_path = "C:/in/a.pdf"
    status = "PENDING"
    created_at = "c"
    updated_at = "u"
    source = "watchdog"
    worker_id = ""
    attempts = 2
    last_error = "locked"


def test_classify_job_outcome():
    assert classify_job_outcome("DONE", {}) == "PASS"
    assert classify_job_outcome("SKIPPED", {"reason": "already_done"}) == "PASS"
    assert classify_job_outcome("SKIPPED", {"reason": "locked"}) == "WARN"
    assert classify_job_outcome("FAILED", {"error": "x"}) == "FAIL"


def test_humanize_job_error_maps_common_cases():
    assert "Bereits verarbeitet" in humanize_job_error(reason="already_done")
    assert "Lock" in humanize_job_error(reason="locked")
    assert humanize_job_error(error="pdf_not_found") == "PDF-Datei nicht gefunden."
    assert humanize_job_error(error="no_assay_detected") == "Kein Assay im PDF erkannt."
    assert "Excel-Schreibfehler" in humanize_job_error(error="excel_write_failed:(1):locked")
    assert "Dedupe-Basis" in humanize_job_error(error="dedupe basis missing: PLATTE")


def test_format_job_result_summary_includes_status_and_human_text():
    summary = format_job_result_summary(
        pdf_path="C:/in/sample.pdf",
        job_id="abc123",
        status="SKIPPED",
        details={"reason": "already_done"},
        outcome="PASS",
    )
    assert "PASS" in summary
    assert "SKIPPED" in summary
    assert "sample.pdf" in summary
    assert "abc123" in summary
    assert "already_done" in summary


def test_format_assay_overview_rows_compact():
    rows = format_assay_overview_rows(
        [
            {
                "assay_key": "(1111)",
                "assay_name": "Assay A",
                "ruleset_file": "AssayA.json",
                "lot_id": "LOT1",
                "dedupe_key": "(1111)|LOT1|X",
                "missing_required": ["date"],
                "outputs": [{"sink": "excel", "status": "created", "excel_path": "a.xlsx", "sheet": "LOT1"}],
            }
        ]
    )
    assert len(rows) == 1
    assert rows[0]["assay_key"] == "(1111)"
    assert rows[0]["missing_required"] == "date"
    assert "Excel" in rows[0]["write_status"]


def test_format_assay_data_detail_shows_values_and_missing():
    text = format_assay_data_detail(
        {
            "data": {"test": "VAL", "date": None},
            "missing_required": ["date"],
        }
    )
    assert "test: 'VAL'" in text
    assert "missing_required: date" in text
    assert "optional_missing: date" in text


def test_format_assay_data_detail_shows_dedupe_meta():
    text = format_assay_data_detail(
        {
            "device_id": "dev1",
            "dedupe_version": "v2",
            "dedupe_key": "v2|dev1|P|D|T|A.asy",
            "duplicate_status": "pending",
            "duplicate_candidate_id": 7,
            "existing_run_id": 3,
            "pdf_sha256": "a" * 64,
            "assay_block_hash": "b" * 64,
            "dedupe_basis": {"PLATTE": "P", "TEST": "A.asy"},
            "data": {"TEST": "A.asy"},
        }
    )
    assert "device_id: dev1" in text
    assert "duplicate_status: pending" in text
    assert "duplicate_candidate_id: 7" in text
    assert "existing_run_id: 3" in text
    assert "dedupe_basis:" in text
    assert "PLATTE: P" in text


def test_format_write_status_lines_excel_and_sqlite():
    lines = format_write_status_lines(
        [
            {"sink": "excel", "status": "created", "excel_path": "a.xlsx", "sheet": "S1"},
            {"sink": "sqlite", "status": "skipped", "sqlite_path": "a.db", "table": "runs"},
            {"sink": "sqlite", "status": "duplicate_pending", "duplicate_candidate_id": 9},
            {"sink": "excel", "status": "skipped_duplicate_pending"},
            {"sink": "excel", "status": "failed", "error": "locked", "excel_path": "a.xlsx"},
        ]
    )
    assert any("Excel: created" in line for line in lines)
    assert any("uebersprungen" in line for line in lines)
    assert any("Duplikat zur Pruefung" in line for line in lines)
    assert any("Duplikat wartet auf Pruefung" in line for line in lines)
    assert any("NICHT geschrieben" in line for line in lines)


def test_format_write_outputs_handles_excel_and_sqlite():
    details = {
        "writes": [
            {
                "assay_key": "(1)",
                "outputs": [
                    {"sink": "excel", "status": "created", "excel_path": "a.xlsx", "sheet": "S1"},
                    {"sink": "sqlite", "status": "inserted", "sqlite_path": "a.db", "table": "runs"},
                ],
            }
        ]
    }
    out = format_write_outputs(details)
    assert any("assay=(1)" in x and "Excel" in x for x in out)
    assert any("SQLite" in x for x in out)


def test_format_partial_writes_note():
    note = format_partial_writes_note(
        {"partial_writes": [{"assay_key": "(1111)"}, {"assay_key": "(2222)"}]}
    )
    assert "Teilweise geschrieben" in note
    assert "(1111)" in note


def test_format_rules_report_counts_sections():
    lines = format_rules_report(
        {
            "missing_files": ["a"],
            "key_mismatches": [],
            "duplicate_json_key_files": ["b", "c"],
            "orphan_rulesets": [],
        }
    )
    assert "missing_files: 1" in lines
    assert "duplicate_json_key_files: 2" in lines


def test_duplicate_candidate_formatters_show_status_and_comparison():
    summary = format_duplicate_candidate_summary(
        {
            "candidate_id": 7,
            "status": "pending",
            "existing_run_id": 3,
            "assay_key": "(1111)",
            "dedupe_key": "v2|dev1|P|D|T|A.asy",
            "device_id": "dev1",
            "detected_at": "2026-01-01T10:00:00+00:00",
        }
    )
    assert summary["candidate_id"] == "7"
    assert summary["status"] == "wartet auf Pruefung"
    assert summary["device_id"] == "dev1"

    detail = {
        "candidate": {
            "candidate_id": 7,
            "status": "deleted",
            "existing_run_id": 3,
            "assay_key": "(1111)",
            "device_id": "dev1",
            "dedupe_key": "v2|dev1|P|D|T|A.asy",
            "decision_by": "tester",
            "decision_note": "false alarm",
            "dedupe_basis": {"TEST": "A.asy"},
        },
        "existing": {
            "run_id": 3,
            "job_id": "j1",
            "pdf_path": "a.pdf",
            "assay_key": "(1111)",
            "dedupe_key": "v2|dev1|P|D|T|A.asy",
        },
        "field_comparison": [
            {"field": "test", "existing": "A", "candidate": "B", "same": False},
            {"field": "unit", "existing": "mg/L", "candidate": "mg/L", "same": True},
        ],
    }
    text = format_duplicate_candidate_detail(detail)
    assert "status: verworfen" in text
    assert "decision_by: tester" in text
    assert "run_id: 3" in text
    assert "TEST: A.asy" in text

    rows = format_duplicate_field_comparison(detail)
    assert rows[0] == {"field": "test", "existing": "A", "candidate": "B", "same": "Nein"}
    assert rows[1] == {"field": "unit", "existing": "mg/L", "candidate": "mg/L", "same": "Ja"}


def test_test_app_presenters_format_device_queue_options_watch_and_validation():
    device = format_device_choice({"device_id": "dev1", "display_name": "Analyzer I", "active": True})
    assert device == {
        "device_id": "dev1",
        "display_name": "Analyzer I",
        "label": "Analyzer I (dev1)",
        "status": "aktiv",
    }

    obj_row = format_queue_job_row(_QueueLike())
    map_row = format_queue_job_row(
        {
            "job_id": "j1",
            "pdf_path": "C:/in/a.pdf",
            "status": "PENDING",
            "updated_at": "u",
            "source": "watchdog",
            "worker_id": "",
            "attempts": 2,
            "last_error": "locked",
        }
    )
    assert obj_row == map_row
    assert obj_row["file"] == "a.pdf"
    assert obj_row["last_error"] == "locked"

    options = format_runtime_options_summary(
        {
            "output_mode": "both",
            "sqlite_path": "out/results.sqlite3",
            "watch_dir": "input/watch",
            "device_id": "dev1",
            "watch_mode": "Ueberwachter Ordner",
        }
    )
    assert "Output: both" in options
    assert "Geraet: dev1" in options

    watch_row = format_watch_file_row("C:/watch/sample.pdf", source="manual")
    assert watch_row["file"] == "sample.pdf"
    assert watch_row["source"] == "manual"
    assert watch_row["action"] == "bereit"

    ok = format_validation_status({"missing_files": [], "key_mismatches": []})
    bad = format_validation_status({"missing_files": ["a"], "key_mismatches": []})
    assert ok["status"] == "OK"
    assert bad["status"] == "FEHLER"
    assert bad["missing_files"] == "1"


def test_format_extractor_file_row_translates_technical_values():
    row = format_extractor_file_row(
        {
            "file": "auto.pdf",
            "path": "C:/watch/auto.pdf",
            "source": "test-app-auto-watch",
            "queue_status": "PENDING",
            "job_id": "job1",
            "device_id": "dev1",
            "last_error": "",
            "action": "queued",
        }
    )

    assert row["source"] == "Automatisch gefunden"
    assert row["queue_status"] == "Wartet"
    assert row["action"] == "Wartet auf Extraktion"
    assert row["job_id"] == "job1"

    manual = format_extractor_file_row({"source": "manual", "queue_status": "FAILED", "action": "bereit"})
    assert manual["source"] == "Manuell hinzugefügt"
    assert manual["queue_status"] == "Fehler"
    assert manual["action"] == "Bereit"

    unknown = format_extractor_file_row({"source": "custom", "queue_status": "PAUSED", "action": "review"})
    assert unknown["source"] == "custom"
    assert unknown["queue_status"] == "PAUSED"
    assert unknown["action"] == "review"


def test_format_extractor_error_label_translates_failed_job_errors():
    assert format_extractor_error_label("no_assay_detected") == "Assay nicht erkannt"
    assert format_extractor_error_label("validation_failed") == "Validierung fehlgeschlagen"
    assert format_extractor_error_label("max_attempts_exceeded") == "Maximale Versuche erreicht"
    assert format_extractor_error_label("worker_submit_error: boom") == "Technischer Verarbeitungsfehler"
    assert format_extractor_error_label("excel_write_failed:(1):locked") == "Excel-Schreibfehler"
    assert format_extractor_error_label("sqlite_write_failed:(1):locked") == "SQLite-Schreibfehler"
    assert format_extractor_error_label("content_split_failed: assay missing") == "Aufteilung fehlgeschlagen"
    assert format_extractor_error_label("unexpected") == "Technischer Fehler"


def test_format_extractor_file_row_shows_friendly_error_only_for_failed_rows():
    failed = format_extractor_file_row({"queue_status": "FAILED", "last_error": "no_assay_detected"})
    pending = format_extractor_file_row({"queue_status": "PENDING", "last_error": "retry_requested"})

    assert failed["last_error"] == "Assay nicht erkannt"
    assert pending["last_error"] == ""


def test_file_row_key_normalizes_equivalent_paths(tmp_path):
    pdf = tmp_path / "watch" / "sample.pdf"
    key_direct = normalize_file_row_key(pdf)
    key_relative = normalize_file_row_key(tmp_path / "watch" / "." / "sample.pdf")
    assert key_direct
    assert key_direct == key_relative


def test_merge_file_rows_with_queue_is_non_mutating(tmp_path):
    pdf = tmp_path / "sample.pdf"
    file_rows = [
        {
            "file": "sample.pdf",
            "path": str(pdf),
            "source": "manual",
            "queue_status": "",
            "job_id": "",
            "device_id": "",
            "last_error": "",
            "action": "bereit",
        }
    ]
    queue_rows = [
        {
            "job_id": "abc",
            "pdf_path": str(tmp_path / "." / "sample.pdf"),
            "status": "PENDING",
            "updated_at": "u",
            "source": "test-app-manual",
            "worker_id": "",
            "attempts": 0,
            "last_error": "old",
        }
    ]

    merged = merge_file_rows_with_queue(file_rows, queue_rows)

    assert file_rows[0]["queue_status"] == ""
    assert merged[0]["queue_status"] == "PENDING"
    assert merged[0]["job_id"] == "abc"
    assert merged[0]["last_error"] == "old"


def test_merge_file_rows_with_queue_include_queue_only_creates_row(tmp_path):
    queued_pdf = tmp_path / "queued-only.pdf"
    queue_rows = [
        {
            "job_id": "job1",
            "pdf_path": str(queued_pdf),
            "status": "PENDING",
            "updated_at": "u",
            "source": "test-app-auto-watch",
            "worker_id": "",
            "attempts": 0,
            "last_error": "",
        }
    ]

    merged = merge_file_rows_with_queue([], queue_rows, include_queue_only=True)

    assert len(merged) == 1
    assert merged[0]["file"] == "queued-only.pdf"
    assert merged[0]["path"] == str(queued_pdf)
    assert merged[0]["source"] == "test-app-auto-watch"
    assert merged[0]["queue_status"] == "PENDING"
    assert merged[0]["job_id"] == "job1"
    assert merged[0]["action"] == "queued"


def test_merge_file_rows_with_queue_default_ignores_queue_only_rows(tmp_path):
    queued_pdf = tmp_path / "queued-only.pdf"
    queue_rows = [
        {
            "job_id": "job1",
            "pdf_path": str(queued_pdf),
            "status": "PENDING",
            "updated_at": "u",
            "source": "test-app-auto-watch",
            "worker_id": "",
            "attempts": 0,
            "last_error": "",
        }
    ]

    merged = merge_file_rows_with_queue([], queue_rows)

    assert merged == []


def test_merge_file_rows_with_queue_updates_existing_row(tmp_path):
    pdf = tmp_path / "sample.pdf"
    file_rows = [
        {
            "file": "sample.pdf",
            "path": str(pdf),
            "source": "manual",
            "queue_status": "",
            "job_id": "",
            "device_id": "",
            "last_error": "",
            "action": "bereit",
        }
    ]
    queue_rows = [
        {
            "job_id": "abc",
            "pdf_path": str(tmp_path / "." / "sample.pdf"),
            "status": "PENDING",
            "updated_at": "u",
            "source": "test-app-manual",
            "worker_id": "",
            "attempts": 0,
            "last_error": "old",
        }
    ]

    merged = merge_file_rows_with_queue(file_rows, queue_rows, include_queue_only=True)

    assert len(merged) == 1
    assert merged[0]["source"] == "manual"
    assert merged[0]["queue_status"] == "PENDING"
    assert merged[0]["job_id"] == "abc"
    assert merged[0]["last_error"] == "old"
    assert merged[0]["action"] == "bereit"
    enqueue = format_enqueue_result(
        {
            "job_id": "abc",
            "pdf_path": "C:/in/sample.pdf",
            "status": "PENDING",
            "updated_at": "u",
            "source": "test-app-manual",
            "worker_id": "",
            "attempts": 0,
            "last_error": "",
        }
    )
    assert "Queue: PENDING" in enqueue
    assert "sample.pdf" in enqueue
    assert "job_id=abc" in enqueue

    update = format_submit_row_update(
        {
            "job_id": "done1",
            "status": "SKIPPED",
            "details": {"reason": "already_done"},
        },
        "dev1",
    )
    assert update == {
        "job_id": "done1",
        "device_id": "dev1",
        "action": "PASS",
        "last_error": "Bereits verarbeitet (Job-State DONE). Force rerun moeglich.",
    }


def _failed_queue_job(job_id: str, pdf_path: str, last_error: str) -> dict[str, str]:
    return {
        "job_id": job_id,
        "pdf_path": pdf_path,
        "status": "FAILED",
        "updated_at": "u",
        "source": "test-app-manual",
        "worker_id": "",
        "attempts": 3,
        "last_error": last_error,
    }


def _write_job_state(tmp_path, job_id: str, *, error: str = "", steps: list | None = None) -> None:
    import json

    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)
    payload = {"job_id": job_id, "error": error, "steps": steps or []}
    (jobs_dir / f"{job_id}.json").write_text(json.dumps(payload), encoding="utf-8")


def test_build_rework_items_includes_no_assay_with_normalized_dump(tmp_path):
    pdf = tmp_path / "sample.pdf"
    dump = tmp_path / "jobs" / "job1_normalized.txt"
    dump.parent.mkdir(parents=True, exist_ok=True)
    dump.write_text("normalized text", encoding="utf-8")
    _write_job_state(
        tmp_path,
        "job1",
        error="no_assay_detected",
        steps=[{"step": "debug", "normalized_dump": str(dump)}],
    )

    items = build_rework_items(tmp_path, [_failed_queue_job("job1", str(pdf), "no_assay_detected")])

    assert len(items) == 1
    assert items[0]["error_label"] == "Assay nicht erkannt"
    assert items[0]["normalized_dump"] == str(dump)
    assert items[0]["context_label"] == "Normalisierter Text"


def test_build_rework_items_recognizes_ruleset_and_split_errors(tmp_path):
    pdf = tmp_path / "sample.pdf"
    _write_job_state(tmp_path, "job2", error="ruleset missing assay_name for (6bd7)")
    _write_job_state(tmp_path, "job3", error="content_split_failed: assay block empty")

    items = build_rework_items(
        tmp_path,
        [
            _failed_queue_job("job2", str(pdf), "ruleset missing assay_name for (6bd7)"),
            _failed_queue_job("job3", str(pdf), "content_split_failed: assay block empty"),
        ],
    )

    labels = {item["job_id"]: item["error_label"] for item in items}
    assert labels == {
        "job2": "Regelset unvollständig",
        "job3": "Aufteilung fehlgeschlagen",
    }


def test_build_rework_items_uses_state_error_for_max_attempts(tmp_path):
    pdf = tmp_path / "sample.pdf"
    _write_job_state(tmp_path, "job4", error="no_assay_detected")

    items = build_rework_items(tmp_path, [_failed_queue_job("job4", str(pdf), "max_attempts_exceeded")])

    assert len(items) == 1
    assert items[0]["error_label"] == "Assay nicht erkannt"
    assert items[0]["state_error"] == "no_assay_detected"


def test_build_rework_items_ignores_non_rule_relevant_failures(tmp_path):
    pdf = tmp_path / "sample.pdf"
    ignored = [
        _failed_queue_job("job5", str(pdf), "pdf_not_found"),
        _failed_queue_job("job6", str(pdf), "excel_write_failed: locked"),
        _failed_queue_job("job7", str(pdf), "sqlite_write_failed: busy"),
        _failed_queue_job("job8", str(pdf), "duplicate_candidate_pending"),
        _failed_queue_job("job9", str(pdf), "worker_submit_error: timeout"),
    ]

    items = build_rework_items(tmp_path, ignored)

    assert items == []


def test_build_rework_items_without_state_file_uses_queue_error_when_rule_relevant(tmp_path):
    pdf = tmp_path / "sample.pdf"

    items = build_rework_items(tmp_path, [_failed_queue_job("job10", str(pdf), "no_assay_detected")])

    assert len(items) == 1
    assert items[0]["state_path"] == ""
    assert items[0]["normalized_dump"] == ""


def test_build_rework_items_marks_missing_dump_files_in_detail(tmp_path):
    pdf = tmp_path / "sample.pdf"
    missing_dump = tmp_path / "jobs" / "job11_normalized.txt"
    _write_job_state(
        tmp_path,
        "job11",
        error="no_assay_detected",
        steps=[{"step": "debug", "normalized_dump": str(missing_dump)}],
    )

    items = build_rework_items(tmp_path, [_failed_queue_job("job11", str(pdf), "no_assay_detected")])
    detail = format_rework_item_detail(items[0])

    assert "nicht vorhanden" in detail
    assert items[0]["context_label"] == "Normalisierter Text (fehlend)"


def test_format_rework_item_summary_and_detail_are_readable(tmp_path):
    pdf = tmp_path / "sample.pdf"
    dump = tmp_path / "jobs" / "job12_normalized.txt"
    dump.parent.mkdir(parents=True, exist_ok=True)
    dump.write_text("text", encoding="utf-8")
    _write_job_state(
        tmp_path,
        "job12",
        error="no_assay_detected",
        steps=[{"step": "debug", "normalized_dump": str(dump)}],
    )
    item = build_rework_items(tmp_path, [_failed_queue_job("job12", str(pdf), "no_assay_detected")])[0]

    summary = format_rework_item_summary(item)
    detail = format_rework_item_detail(item)

    assert summary["file"] == "sample.pdf"
    assert summary["error_label"] == "Assay nicht erkannt"
    assert summary["queue_status"] == "Fehler"
    assert "Assay nicht erkannt" in detail
    assert "Normalized dump:" in detail


def _sample_rework_item(**overrides):
    item = {
        "item_id": "job1",
        "job_id": "job1",
        "file": "sample.pdf",
        "pdf_path": "/tmp/sample.pdf",
        "queue_status": "FAILED",
        "error_label": "Assay nicht erkannt",
        "queue_error": "no_assay_detected",
        "state_error": "no_assay_detected",
        "root_error": "no_assay_detected",
        "context_label": "Normalisierter Text",
        "state_path": "/tmp/jobs/job1.json",
        "normalized_dump": "/tmp/jobs/job1_normalized.txt",
        "block_dumps": {},
    }
    item.update(overrides)
    return item


def test_filter_rework_items_all_returns_every_item():
    items = [
        _sample_rework_item(item_id="job1", error_label="Assay nicht erkannt"),
        _sample_rework_item(item_id="job2", error_label="Regelset unvollständig"),
    ]

    filtered = filter_rework_items(items, "Alle")

    assert len(filtered) == 2


def test_filter_rework_items_by_error_label():
    items = [
        _sample_rework_item(item_id="job1", job_id="job1", error_label="Assay nicht erkannt"),
        _sample_rework_item(item_id="job2", job_id="job2", error_label="Regelset unvollständig"),
        _sample_rework_item(item_id="job3", job_id="job3", error_label="Aufteilung fehlgeschlagen"),
    ]

    filtered = filter_rework_items(items, "Regelset unvollständig")

    assert [item["job_id"] for item in filtered] == ["job2"]


def test_filter_rework_items_unknown_label_returns_empty_list():
    items = [_sample_rework_item()]

    assert filter_rework_items(items, "Unbekannt") == []


def test_format_rework_context_text_includes_header_and_line_numbers(tmp_path):
    dump = tmp_path / "job1_normalized.txt"
    dump.write_text("line one\nline two", encoding="utf-8")
    item = _sample_rework_item(
        pdf_path=str(tmp_path / "sample.pdf"),
        normalized_dump=str(dump),
    )

    text = format_rework_context_text(item, "line one\nline two", "Normalisierter Text", str(dump))

    assert "Kontexttyp: Normalisierter Text" in text
    assert "PDF-Pfad:" in text
    assert "Dump-Pfad:" in text
    assert "Fehlerklasse: Assay nicht erkannt" in text
    assert "Queue-Fehler: no_assay_detected" in text
    assert "State-Fehler: no_assay_detected" in text
    assert "Root-Cause: no_assay_detected" in text
    assert "0001 | line one" in text
    assert "0002 | line two" in text


def test_format_rework_context_text_missing_dump_is_readable(tmp_path):
    missing = tmp_path / "missing.txt"
    item = _sample_rework_item(normalized_dump=str(missing))

    text = format_rework_context_text(
        item,
        None,
        "Normalisierter Text (fehlend)",
        str(missing),
    )

    assert "Dump-Datei nicht vorhanden" in text
    assert str(missing) in text


def test_format_rework_item_detail_contains_paths_and_root_cause(tmp_path):
    pdf = tmp_path / "sample.pdf"
    dump = tmp_path / "jobs" / "job12_normalized.txt"
    dump.parent.mkdir(parents=True, exist_ok=True)
    dump.write_text("text", encoding="utf-8")
    _write_job_state(
        tmp_path,
        "job12",
        error="no_assay_detected",
        steps=[{"step": "debug", "normalized_dump": str(dump)}],
    )
    item = build_rework_items(tmp_path, [_failed_queue_job("job12", str(pdf), "no_assay_detected")])[0]
    detail = format_rework_item_detail(item)

    assert f"PDF-Pfad: {pdf}" in detail
    assert "Root-Cause:" in detail
    assert "Queue-Fehler:" in detail
    assert "State-Fehler:" in detail
    assert str(dump) in detail


def test_default_result_columns_and_row_formatting():
    from src.testui.helpers import (
        build_result_column_catalog,
        default_result_columns,
        format_result_run_row,
        normalize_visible_result_columns,
    )

    run = {
        "id": 1,
        "assay_key": "(1111)",
        "lot_id": "LOT-A",
        "device_id": "dev1",
        "pdf_path": "/tmp/a.pdf",
        "result_date": "2026-01-01",
        "payload": {"TEST": "1.2"},
    }
    catalog = build_result_column_catalog([run])
    visible = normalize_visible_result_columns(default_result_columns(), catalog)
    row = format_result_run_row(run, visible)
    assert row[0] == "2026-01-01"
    assert row[1] == "(1111)"
    assert row[2] == "LOT-A"
    assert "payload:TEST" in catalog
    assert "payload:TEST" not in visible
