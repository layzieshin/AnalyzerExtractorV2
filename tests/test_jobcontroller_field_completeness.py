import json
from pathlib import Path

from src.jobcontroller.api import submit
from src.parser.model import ParsedDocument, ParsedPage


def test_empty_configured_field_fails_before_sinks(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "proj"
    (root / "rules").mkdir(parents=True)
    pdf = root / "input.pdf"
    pdf.write_bytes(b"empty-configured-field")
    index = {"assays": [{"assay_key": "(1111)", "ruleset_file": "AssayA.json"}]}
    (root / "rules" / "index.json").write_text(json.dumps(index), encoding="utf-8")
    ruleset = {
        "assay_name": "Assay A",
        "assay_key": "(1111)",
        "lot_rule": {"regex": r"Lot:\s*(\w+)"},
        "extract_rules": {
            "fields": [
                {"key": "plate_name", "regex": r"Plate:\s*(\w+)", "required": True},
                {"key": "test", "regex": r"Test:\s*(\w+)", "required": True},
                {"key": "date", "regex": r"Date:\s*([0-9\-]+)", "required": True},
                {"key": "time", "regex": r"Time:\s*([0-9:]+)", "required": True},
                {"key": "note", "regex": r"Note:\s*(.*)", "required": False},
            ]
        },
        "excel_rules": {
            "excel_filename_template": "{assay_name}.xlsx",
            "sheetname_template": "{lot_id}",
            "column_mapping": {},
        },
    }
    (root / "rules" / "AssayA.json").write_text(json.dumps(ruleset), encoding="utf-8")

    def fake_parse(_: str) -> ParsedDocument:
        lines = [
            "Assay A",
            "(1111)",
            "Lot: LOTA",
            "Plate: PLATE1",
            "Test: TESTX",
            "Date: 2026-05-28",
            "Time: 12:00:00",
            "Note:   ",
        ]
        return ParsedDocument(
            source_path=str(pdf),
            pages=[ParsedPage(page_number=1, lines=lines)],
            meta={"page_count": 1},
        )

    monkeypatch.setattr("src.parser.api.parse", fake_parse)
    sqlite_calls = {"count": 0}
    excel_calls = {"count": 0}

    def forbid_sqlite(*_args, **_kwargs):
        sqlite_calls["count"] += 1
        raise AssertionError("sqlite write must not run")

    def forbid_excel(*_args, **_kwargs):
        excel_calls["count"] += 1
        raise AssertionError("excel write must not run")

    monkeypatch.setattr("src.dbwriter.api.write_record_sqlite", forbid_sqlite)
    monkeypatch.setattr("src.writer.api.write_record", forbid_excel)

    result = submit(
        str(pdf),
        str(root),
        output_mode="both",
        sqlite_path=str(root / "output" / "final" / "res.sqlite3"),
    )
    assert result.status == "FAILED"
    assert result.details["error"] == "configured_fields_empty: note"
    assert sqlite_calls["count"] == 0
    assert excel_calls["count"] == 0

    state_path = root / "jobs" / f"{result.job_id}.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["status"] == "FAILED"
    assert state["error"] == "configured_fields_empty: note"
    assert state.get("export_retry_available") is not True
    assert "output_plan" not in state
    steps = {step["step"]: step for step in state["steps"]}
    normalized = Path(steps["debug"]["normalized_dump"])
    block = Path(steps["debug_blocks"]["block_dumps"]["(1111)"])
    assert normalized.is_file()
    assert "Lot: LOTA" in normalized.read_text(encoding="utf-8")
    assert block.is_file()
    assert "(1111)" in block.read_text(encoding="utf-8")
    assert not (root / "output" / "final" / "res.sqlite3").exists()
    assert list(root.rglob("*.xlsx")) == []
