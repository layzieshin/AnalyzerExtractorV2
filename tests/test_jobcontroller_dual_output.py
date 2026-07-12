import json
from pathlib import Path

from src.jobcontroller.api import submit
from src.parser.model import ParsedDocument, ParsedPage


def _write_duplicate_project(root: Path) -> None:
    (root / "rules").mkdir(parents=True)
    (root / "output" / "final").mkdir(parents=True)
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
            ]
        },
        "excel_rules": {
            "excel_filename_template": "{assay_name}.xlsx",
            "sheetname_template": "{lot_id}",
            "column_mapping": {},
        },
    }
    (root / "rules" / "AssayA.json").write_text(json.dumps(ruleset), encoding="utf-8")


def _same_dedupe_parse(pdf: Path) -> ParsedDocument:
    lines = [
        "Assay A",
        "(1111)",
        "Lot: LOTA",
        "Plate: PLATE1",
        "Test: TESTX",
        "Date: 2026-05-28",
        "Time: 12:00:00",
    ]
    return ParsedDocument(source_path=str(pdf), pages=[ParsedPage(page_number=1, lines=lines)], meta={"page_count": 1})


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
                {"key": "plate_name", "regex": r"Plate:\s*(\w+)", "required": True},
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
            "Plate: PLATE1",
            "Test: TESTX",
            "Date: 2026-05-28",
            "Time: 12:00:00",
        ]
        return ParsedDocument(source_path=str(pdf), pages=[ParsedPage(page_number=1, lines=lines)], meta={"page_count": 1})

    monkeypatch.setattr("src.parser.api.parse", fake_parse)

    sqlite_path = root / "output" / "final" / "res.sqlite3"
    result = submit(str(pdf), str(root), output_mode="both", sqlite_path=str(sqlite_path), device_id="dev1")

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
    assert item["device_id"] == "dev1"
    assert item["dedupe_version"] == "v2"
    assert item["dedupe_key"] == "v2|dev1|PLATE1|2026-05-28|12:00:00|TESTX"
    assert item["dedupe_basis"]["PLATTE"] == "PLATE1"
    assert len(item["pdf_sha256"]) == 64
    assert item["pdf_sha256"].startswith(result.job_id)
    assert len(item["assay_block_hash"]) == 64
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
                {"key": "plate_name", "regex": r"Plate:\s*(\w+)", "required": True},
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
                {"key": "plate_name", "regex": r"Plate:\s*(\w+)", "required": True},
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
            "Plate: PLATE1",
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


def test_submit_same_pdf_hash_still_skips_already_done(tmp_path: Path, monkeypatch):
    root = tmp_path / "proj"
    _write_duplicate_project(root)
    pdf = root / "input.pdf"
    pdf.write_bytes(b"same-pdf")

    monkeypatch.setattr("src.parser.api.parse", lambda path: _same_dedupe_parse(Path(path)))

    sqlite_path = root / "output" / "final" / "res.sqlite3"
    first = submit(str(pdf), str(root), output_mode="sqlite", sqlite_path=str(sqlite_path), device_id="dev1")
    second = submit(str(pdf), str(root), output_mode="sqlite", sqlite_path=str(sqlite_path), device_id="dev1")

    assert first.status == "DONE"
    assert second.status == "SKIPPED"
    assert second.details["reason"] == "already_done"


def test_submit_both_duplicate_uses_sqlite_ledger_before_excel(tmp_path: Path, monkeypatch):
    root = tmp_path / "proj"
    _write_duplicate_project(root)
    pdf1 = root / "input1.pdf"
    pdf2 = root / "input2.pdf"
    pdf1.write_bytes(b"first-pdf")
    pdf2.write_bytes(b"second-pdf")

    monkeypatch.setattr("src.parser.api.parse", lambda path: _same_dedupe_parse(Path(path)))

    sqlite_path = root / "output" / "final" / "res.sqlite3"
    first = submit(str(pdf1), str(root), output_mode="both", sqlite_path=str(sqlite_path), device_id="dev1")
    second = submit(str(pdf2), str(root), output_mode="both", sqlite_path=str(sqlite_path), device_id="dev1")

    assert first.status == "DONE"
    assert second.status == "DONE"
    first_item = first.details["writes"][0]
    second_item = second.details["writes"][0]
    assert first_item["duplicate_status"] == "none"
    assert any(out["sink"] == "sqlite" and out["status"] == "inserted" for out in first_item["outputs"])
    assert any(out["sink"] == "excel" and out["status"] == "created" for out in first_item["outputs"])
    assert second_item["duplicate_status"] == "pending"
    assert second_item["duplicate_candidate_id"] is not None
    assert second_item["existing_run_id"] is not None
    assert any(out["sink"] == "sqlite" and out["status"] == "duplicate_pending" for out in second_item["outputs"])
    assert any(
        out["sink"] == "excel" and out["status"] == "skipped_duplicate_pending"
        for out in second_item["outputs"]
    )


def test_submit_sqlite_only_duplicate_reports_pending(tmp_path: Path, monkeypatch):
    root = tmp_path / "proj"
    _write_duplicate_project(root)
    pdf1 = root / "input1.pdf"
    pdf2 = root / "input2.pdf"
    pdf1.write_bytes(b"first-pdf")
    pdf2.write_bytes(b"second-pdf")

    monkeypatch.setattr("src.parser.api.parse", lambda path: _same_dedupe_parse(Path(path)))

    sqlite_path = root / "output" / "final" / "res.sqlite3"
    first = submit(str(pdf1), str(root), output_mode="sqlite", sqlite_path=str(sqlite_path), device_id="dev1")
    second = submit(str(pdf2), str(root), output_mode="sqlite", sqlite_path=str(sqlite_path), device_id="dev1")

    assert first.status == "DONE"
    assert second.status == "DONE"
    item = second.details["writes"][0]
    assert item["duplicate_status"] == "pending"
    assert item["duplicate_candidate_id"] is not None
    assert not (root / "output" / "final" / "Assay_A.xlsx").exists()


def test_submit_excel_only_duplicate_behavior_unchanged(tmp_path: Path, monkeypatch):
    root = tmp_path / "proj"
    _write_duplicate_project(root)
    pdf1 = root / "input1.pdf"
    pdf2 = root / "input2.pdf"
    pdf1.write_bytes(b"first-pdf")
    pdf2.write_bytes(b"second-pdf")

    monkeypatch.setattr("src.parser.api.parse", lambda path: _same_dedupe_parse(Path(path)))

    first = submit(str(pdf1), str(root), output_mode="excel", device_id="dev1")
    second = submit(str(pdf2), str(root), output_mode="excel", device_id="dev1")

    assert first.status == "DONE"
    assert second.status == "DONE"
    item = second.details["writes"][0]
    assert item["duplicate_status"] == "none"
    assert item["outputs"] == [
        {
            "sink": "excel",
            "excel_path": str(root / "output" / "final" / "Assay_A.xlsx"),
            "sheet": "LOTA",
            "status": "skipped",
        }
    ]
