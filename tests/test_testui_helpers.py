from src.testui.helpers import (
    classify_job_outcome,
    format_assay_data_detail,
    format_assay_overview_rows,
    format_job_result_summary,
    format_partial_writes_note,
    format_rules_report,
    format_write_outputs,
    format_write_status_lines,
    humanize_job_error,
)


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
            "pdf_sha256": "a" * 64,
            "assay_block_hash": "b" * 64,
            "dedupe_basis": {"PLATTE": "P", "TEST": "A.asy"},
            "data": {"TEST": "A.asy"},
        }
    )
    assert "device_id: dev1" in text
    assert "dedupe_basis:" in text
    assert "PLATTE: P" in text


def test_format_write_status_lines_excel_and_sqlite():
    lines = format_write_status_lines(
        [
            {"sink": "excel", "status": "created", "excel_path": "a.xlsx", "sheet": "S1"},
            {"sink": "sqlite", "status": "skipped", "sqlite_path": "a.db", "table": "runs"},
            {"sink": "excel", "status": "failed", "error": "locked", "excel_path": "a.xlsx"},
        ]
    )
    assert any("Excel: created" in line for line in lines)
    assert any("uebersprungen" in line for line in lines)
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
