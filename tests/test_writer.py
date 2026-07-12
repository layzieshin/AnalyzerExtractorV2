from pathlib import Path

import pytest
from openpyxl import load_workbook

from src.extractor.model import AssayRecord
from src.ruleresolver.model import RuleSet
from src.writer.api import write_record
from src.writer.writer import WriterError


def _ruleset() -> RuleSet:
    return RuleSet(
        assay_key="(1111)",
        ruleset_file="A.json",
        data={
            "assay_name": "Assay A",
            "assay_key": "(1111)",
            "lot_rule": {"regex": "x"},
            "extract_rules": {"fields": []},
            "excel_rules": {
                "excel_filename_template": "{assay_name}.xlsx",
                "sheetname_template": "{lot_id}",
                "column_mapping": {},
            },
        },
    )


def test_writer_created_then_skipped_on_same_dedupe(tmp_path: Path):
    out = tmp_path / "final"
    rec = AssayRecord(
        assay_key="(1111)",
        lot_id="LOT1",
        dedupe_key="K1",
        data={"date": "2026-01-01", "time": "10:00:00"},
        device_id="dev1",
        dedupe_version="v2",
    )
    r1 = write_record(rec, _ruleset(), str(out))
    r2 = write_record(rec, _ruleset(), str(out))
    assert r1.status == "created"
    assert r2.status == "skipped"
    wb = load_workbook(r1.excel_path)
    headers = [cell.value for cell in wb[r1.sheet_name][1]]
    assert headers[:5] == ["assay_key", "device_id", "lot_id", "dedupe_key", "dedupe_version"]


def test_writer_lock_file_blocks_write(tmp_path: Path):
    out = tmp_path / "final"
    out.mkdir(parents=True)
    (out / ".excel_writer.lock").write_text("", encoding="utf-8")
    rec = AssayRecord(assay_key="(1111)", lot_id="LOT1", dedupe_key="K1", data={})
    with pytest.raises(WriterError):
        write_record(rec, _ruleset(), str(out))
