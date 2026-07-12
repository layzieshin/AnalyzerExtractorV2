import json
from pathlib import Path

from interfaces.cli import rules_matrix
from src.parser.model import ParsedDocument, ParsedPage


def _write_project(root: Path, explicit_dedupe: bool = True) -> Path:
    (root / "rules").mkdir(parents=True)
    (root / "input").mkdir(parents=True)
    (root / "input" / "sample.pdf").write_bytes(b"fake-pdf")

    (root / "rules" / "index.json").write_text(
        json.dumps({"assays": [{"assay_key": "(1111)", "ruleset_file": "AssayA.json"}]}),
        encoding="utf-8",
    )
    extract_rules = {
        "fields": [
            {"key": "plate_name", "regex": r"Plate:\s*(\w+)", "required": True},
            {"key": "test", "regex": r"Test:\s*(\w+)", "required": True},
            {"key": "date", "regex": r"Date:\s*([0-9\-]+)", "required": True},
            {"key": "time", "regex": r"Time:\s*([0-9:]+)", "required": True},
            {"key": "optional", "regex": r"Optional:\s*(\w+)", "required": False},
        ]
    }
    if explicit_dedupe:
        extract_rules["dedupe_fields"] = ["date", "time"]
    ruleset = {
        "assay_name": "Assay A",
        "assay_key": "(1111)",
        "lot_rule": {"regex": r"Lot:\s*(\w+)"},
        "extract_rules": extract_rules,
        "excel_rules": {
            "excel_filename_template": "{assay_name}.xlsx",
            "sheetname_template": "{lot_id}",
            "column_mapping": {
                "plate_name": "PLATE",
                "test": "TEST",
                "date": "DATE",
                "time": "TIME",
                "optional": "OPTIONAL",
            },
        },
    }
    (root / "rules" / "AssayA.json").write_text(json.dumps(ruleset), encoding="utf-8")
    return root / "input" / "sample.pdf"


def test_rules_matrix_preview_green_with_explicit_dedupe(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "proj"
    pdf = _write_project(root, explicit_dedupe=True)

    def fake_parse(_pdf_path: str) -> ParsedDocument:
        lines = [
            "Assay A",
            "(1111)",
            "Lot: LOT-A",
            "Plate: P1",
            "Test: Assay A.asy",
            "Date: 2026-07-09",
            "Time: 12:30:00",
            "Optional: X",
        ]
        return ParsedDocument(source_path=str(pdf), pages=[ParsedPage(page_number=1, lines=lines)], meta={"page_count": 1})

    monkeypatch.setattr(rules_matrix, "parse", fake_parse)

    report = rules_matrix.run_matrix(root, pdfs=[pdf], mode="preview", write_report=False)

    assert report["summary"] == {"green": 1, "yellow": 0, "red": 0}
    row = report["assays"][0]
    assert row["dedupe_policy"] == "explicit_legacy"
    assert row["pdf_results"][0]["criteria"]["lot_id"] == "green"


def test_rules_matrix_marks_v2_default_green(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "proj"
    pdf = _write_project(root, explicit_dedupe=False)

    def fake_parse(_pdf_path: str) -> ParsedDocument:
        lines = [
            "Assay A",
            "(1111)",
            "Lot: LOT-A",
            "Plate: P1",
            "Test: Assay A.asy",
            "Date: 2026-07-09",
            "Time: 12:30:00",
            "Optional: X",
        ]
        return ParsedDocument(source_path=str(pdf), pages=[ParsedPage(page_number=1, lines=lines)], meta={"page_count": 1})

    monkeypatch.setattr(rules_matrix, "parse", fake_parse)

    report = rules_matrix.run_matrix(root, pdfs=[pdf], mode="preview", write_report=False)

    assert report["summary"] == {"green": 1, "yellow": 0, "red": 0}
    assert report["assays"][0]["dedupe_policy"] == "v2_default"
    assert "dedupe_fallback" not in report["assays"][0]["issues"]


def test_rules_matrix_marks_missing_assay_red(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "proj"
    pdf = _write_project(root, explicit_dedupe=True)

    def fake_parse(_pdf_path: str) -> ParsedDocument:
        lines = ["Some other assay", "Lot: LOT-A", "Date: 2026-07-09", "Time: 12:30:00"]
        return ParsedDocument(source_path=str(pdf), pages=[ParsedPage(page_number=1, lines=lines)], meta={"page_count": 1})

    monkeypatch.setattr(rules_matrix, "parse", fake_parse)

    report = rules_matrix.run_matrix(root, pdfs=[pdf], mode="preview", write_report=False)

    assert report["summary"] == {"green": 0, "yellow": 0, "red": 1}
    assert report["assays"][0]["issues"] == ["not_detected_in_selected_pdfs"]


def test_rules_matrix_marks_missing_v2_dedupe_basis_red(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "proj"
    pdf = _write_project(root, explicit_dedupe=False)
    rules_path = root / "rules" / "AssayA.json"
    data = json.loads(rules_path.read_text(encoding="utf-8"))
    for field in data["extract_rules"]["fields"]:
        if field["key"] in {"plate_name", "test"}:
            field["required"] = False
    rules_path.write_text(json.dumps(data), encoding="utf-8")

    def fake_parse(_pdf_path: str) -> ParsedDocument:
        lines = ["Assay A", "(1111)", "Lot: LOT-A", "Date: 2026-07-09", "Time: 12:30:00"]
        return ParsedDocument(source_path=str(pdf), pages=[ParsedPage(page_number=1, lines=lines)], meta={"page_count": 1})

    monkeypatch.setattr(rules_matrix, "parse", fake_parse)

    report = rules_matrix.run_matrix(root, pdfs=[pdf], mode="preview", write_report=False)

    assert report["summary"] == {"green": 0, "yellow": 0, "red": 1}
    pdf_result = report["assays"][0]["pdf_results"][0]
    assert pdf_result["criteria"]["dedupe"] == "red"
    assert pdf_result["dedupe_policy"] == "missing"
    assert "dedupe_basis_missing:PLATTE" in pdf_result["issues"]
    assert "dedupe_basis_missing:TEST" in pdf_result["issues"]


def test_rules_matrix_marks_dedupe_fields_empty_red(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "proj"
    pdf = _write_project(root, explicit_dedupe=True)

    def fake_parse(_pdf_path: str) -> ParsedDocument:
        lines = ["Assay A", "(1111)", "Lot: LOT-A", "Plate: P1", "Test: Assay A.asy", "Date: 2026-07-09", "Time: 12:30:00"]
        return ParsedDocument(source_path=str(pdf), pages=[ParsedPage(page_number=1, lines=lines)], meta={"page_count": 1})

    def fake_extract_record(_block, _ruleset):
        raise RuntimeError("dedupe fields empty: ['date', 'time']")

    monkeypatch.setattr(rules_matrix, "parse", fake_parse)
    monkeypatch.setattr(rules_matrix, "extract_record", fake_extract_record)

    report = rules_matrix.run_matrix(root, pdfs=[pdf], mode="preview", write_report=False)

    assert report["summary"] == {"green": 0, "yellow": 0, "red": 1}
    pdf_result = report["assays"][0]["pdf_results"][0]
    assert pdf_result["criteria"]["dedupe"] == "red"
    assert any("extract_failed:dedupe fields empty" in issue for issue in pdf_result["issues"])


def test_rules_matrix_marks_optional_missing_yellow_without_required_yellow(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "proj"
    pdf = _write_project(root, explicit_dedupe=True)

    def fake_parse(_pdf_path: str) -> ParsedDocument:
        lines = ["Assay A", "(1111)", "Lot: LOT-A", "Plate: P1", "Test: Assay A.asy", "Date: 2026-07-09", "Time: 12:30:00"]
        return ParsedDocument(source_path=str(pdf), pages=[ParsedPage(page_number=1, lines=lines)], meta={"page_count": 1})

    monkeypatch.setattr(rules_matrix, "parse", fake_parse)

    report = rules_matrix.run_matrix(root, pdfs=[pdf], mode="preview", write_report=False)

    assert report["summary"] == {"green": 0, "yellow": 1, "red": 0}
    pdf_result = report["assays"][0]["pdf_results"][0]
    assert pdf_result["criteria"]["required_fields"] == "green"
    assert pdf_result["criteria"]["dedupe"] == "green"
    assert "optional" in pdf_result["optional_missing"]
    assert "optional_fields_missing" in pdf_result["issues"]
