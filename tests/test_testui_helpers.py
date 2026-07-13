from src.testui.helpers import (
    classify_job_outcome,
    format_assay_data_detail,
    format_assay_overview_rows,
    format_device_choice,
    format_duplicate_candidate_detail,
    format_duplicate_candidate_summary,
    format_duplicate_field_comparison,
    format_enqueue_result,
    format_job_result_summary,
    format_partial_writes_note,
    format_queue_job_row,
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


def test_enqueue_and_submit_presenters_are_compact():
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
