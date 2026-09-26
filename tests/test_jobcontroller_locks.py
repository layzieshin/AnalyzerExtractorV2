import json
import os
import time
from pathlib import Path

from src.jobcontroller.api import submit


def _hash_pdf_bytes(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()[:16]


def test_submit_skips_when_pipeline_lock_held(tmp_path: Path):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "locks").mkdir()
    (root / "jobs").mkdir()
    pdf = root / "locked.pdf"
    pdf.write_bytes(b"locked-pdf")

    job_id = _hash_pdf_bytes(b"locked-pdf")
    lock_path = root / "locks" / f"{job_id}.lock"
    lock_path.write_text("", encoding="utf-8")

    result = submit(str(pdf), str(root), lock_ttl_s=900.0)
    assert result.status == "SKIPPED"
    assert result.details.get("reason") == "locked"


def test_submit_reclaims_stale_pipeline_lock(tmp_path: Path, monkeypatch):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "locks").mkdir()
    (root / "jobs").mkdir()
    (root / "rules").mkdir()
    (root / "output" / "final").mkdir(parents=True)
    pdf = root / "stale.pdf"
    pdf.write_bytes(b"stale-pdf")

    job_id = _hash_pdf_bytes(b"stale-pdf")
    lock_path = root / "locks" / f"{job_id}.lock"
    lock_path.write_text("", encoding="utf-8")
    old = time.time() - 60.0
    os.utime(lock_path, (old, old))

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

    from src.parser.model import ParsedDocument, ParsedPage

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
        return ParsedDocument(
            source_path=str(pdf),
            pages=[ParsedPage(page_number=1, lines=lines)],
            meta={"page_count": 1},
        )

    monkeypatch.setattr("src.parser.api.parse", fake_parse)

    result = submit(str(pdf), str(root), output_mode="sqlite", lock_ttl_s=10.0)
    assert result.details.get("reason") != "locked"
    assert not lock_path.exists()
    state_path = root / "jobs" / f"{job_id}.json"
    assert state_path.exists()
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state.get("status") != "LOCKED" or len(state.get("steps", [])) > 0


def test_submit_releases_lock_on_pipeline_failure(tmp_path: Path, monkeypatch):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "jobs").mkdir()
    pdf = root / "fail.pdf"
    pdf.write_bytes(b"fail-pdf")

    job_id = _hash_pdf_bytes(b"fail-pdf")
    lock_path = root / "locks" / f"{job_id}.lock"

    def boom(_: str):
        raise RuntimeError("parse_failed")

    monkeypatch.setattr("src.parser.api.parse", boom)

    result = submit(str(pdf), str(root), lock_ttl_s=900.0)
    assert result.status == "FAILED"
    assert not lock_path.exists()
