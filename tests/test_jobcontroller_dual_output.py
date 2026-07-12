import json
from pathlib import Path

from src.jobcontroller.api import submit
from src.parser.model import ParsedDocument, ParsedPage


def test_submit_writes_excel_and_sqlite(tmp_path: Path, monkeypatch):
    root = tmp_path / "proj"
    (root / "rules").mkdir(parents=True)
    (root / "output" / "final").mkdir(parents=True)
    pdf = root / "input.pdf"
    pdf.write_bytes(b"fake-pdf")

    index = {"assays": [{"assay_key": "(1111)", "ruleset_file": "AssayA.json"}]}
    (root / "rules" / "index.json").write_text(json.dumps(index), encoding="utf-8")
    ruleset = {
        "assay_name": "Assay A",
        "assay_key": "(1111)",
        "lot_rule": {"regex": r"Lot:\s*(\w+)"},
        "extract_rules": {
            "fields": [
                {"key": "test", "regex": r"Test:\s*(\w+)", "required": True},
                {"key": "date", "regex": r"Date:\s*([0-9\-]+)", "required": True},
                {"key": "time", "regex": r"Time:\s*([0-9:]+)", "required": True},
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
            "Test: TESTX",
            "Date: 2026-05-28",
            "Time: 12:00:00",
        ]
        return ParsedDocument(source_path=str(pdf), pages=[ParsedPage(page_number=1, lines=lines)], meta={"page_count": 1})

    monkeypatch.setattr("src.parser.api.parse", fake_parse)

    sqlite_path = root / "output" / "final" / "res.sqlite3"
    result = submit(str(pdf), str(root), output_mode="both", sqlite_path=str(sqlite_path))

    assert result.status == "DONE"
    assert (root / "output" / "final" / "Assay_A.xlsx").exists()
    assert sqlite_path.exists()

    writes = result.details.get("writes")
    assert isinstance(writes, list) and len(writes) == 1
    item = writes[0]
    assert item["assay_key"] == "(1111)"
    assert item["assay_name"] == "Assay A"
    assert item["ruleset_file"] == "AssayA.json"
    assert item["lot_id"] == "LOTA"
    assert item["dedupe_key"].startswith("(1111)|LOTA|")
    assert item["data"]["test"] == "TESTX"
    assert item["missing_required"] == []
    assert len(item["outputs"]) == 2


def test_submit_reports_missing_required_in_write_item(tmp_path: Path, monkeypatch):
    root = tmp_path / "proj"
    (root / "rules").mkdir(parents=True)
    (root / "output" / "final").mkdir(parents=True)
    pdf = root / "input.pdf"
    pdf.write_bytes(b"fake-pdf")

    index = {"assays": [{"assay_key": "(1111)", "ruleset_file": "AssayA.json"}]}
    (root / "rules" / "index.json").write_text(json.dumps(index), encoding="utf-8")
    ruleset = {
        "assay_name": "Assay A",
        "assay_key": "(1111)",
        "lot_rule": {"regex": r"Lot:\s*(\w+)"},
        "extract_rules": {
            "fields": [
                {"key": "test", "regex": r"Test:\s*(\w+)", "required": True},
                {"key": "date", "regex": r"Date:\s*([0-9\-]+)", "required": True},
                {"key": "optional", "regex": r"Opt:\s*(\w+)", "required": False},
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
        lines = ["Assay A", "(1111)", "Lot: LOTA", "Test: TESTX"]
        return ParsedDocument(source_path=str(pdf), pages=[ParsedPage(page_number=1, lines=lines)], meta={"page_count": 1})

    monkeypatch.setattr("src.parser.api.parse", fake_parse)

    result = submit(str(pdf), str(root), output_mode="sqlite", sqlite_path=str(root / "output" / "final" / "res.sqlite3"))
    assert result.status == "FAILED"
    assert "required field not found" in str(result.details.get("error", ""))


def test_submit_sqlite_only_skips_excel(tmp_path: Path, monkeypatch):
    root = tmp_path / "proj"
    (root / "rules").mkdir(parents=True)
    (root / "output" / "final").mkdir(parents=True)
    pdf = root / "input.pdf"
    pdf.write_bytes(b"fake-pdf")

    index = {"assays": [{"assay_key": "(1111)", "ruleset_file": "AssayA.json"}]}
    (root / "rules" / "index.json").write_text(json.dumps(index), encoding="utf-8")
    ruleset = {
        "assay_name": "Assay A",
        "assay_key": "(1111)",
        "lot_rule": {"regex": r"Lot:\s*(\w+)"},
        "extract_rules": {
            "fields": [
                {"key": "test", "regex": r"Test:\s*(\w+)", "required": True},
                {"key": "date", "regex": r"Date:\s*([0-9\-]+)", "required": True},
                {"key": "time", "regex": r"Time:\s*([0-9:]+)", "required": True},
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
            "Test: TESTX",
            "Date: 2026-05-28",
            "Time: 12:00:00",
        ]
        return ParsedDocument(source_path=str(pdf), pages=[ParsedPage(page_number=1, lines=lines)], meta={"page_count": 1})

    monkeypatch.setattr("src.parser.api.parse", fake_parse)

    sqlite_path = root / "output" / "final" / "res.sqlite3"
    result = submit(str(pdf), str(root), output_mode="sqlite", sqlite_path=str(sqlite_path))

    assert result.status == "DONE"
    assert not (root / "output" / "final" / "Assay_A.xlsx").exists()
    assert sqlite_path.exists()
