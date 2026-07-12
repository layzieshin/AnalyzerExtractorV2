from pathlib import Path
import sqlite3

from src.dbwriter.api import write_record_sqlite
from src.extractor.model import AssayRecord
from src.ruleresolver.model import RuleSet


def test_sqlite_writer_inserts_and_dedupes(tmp_path: Path):
    sqlite_path = tmp_path / "results.sqlite3"
    ruleset = RuleSet(
        assay_key="(1111)",
        ruleset_file="Test.json",
        data={"assay_name": "AssayA", "lot_rule": {}, "extract_rules": {}, "excel_rules": {}},
    )
    record = AssayRecord(
        assay_key="(1111)",
        lot_id="LOT1",
        dedupe_key="T|2026-01-01|10:00:00",
        data={"test": "T", "date": "2026-01-01", "time": "10:00:00"},
        device_id="dev1",
        dedupe_version="v2",
        dedupe_basis={"device_id": "dev1", "TEST": "T"},
    )

    r1 = write_record_sqlite(
        record,
        ruleset,
        str(sqlite_path),
        job_id="j1",
        pdf_path="a.pdf",
        pdf_sha256="a" * 64,
        assay_block_hash="b" * 64,
    )
    r2 = write_record_sqlite(record, ruleset, str(sqlite_path), job_id="j1", pdf_path="a.pdf")

    assert r1.status == "inserted"
    assert r2.status == "skipped"

    with sqlite3.connect(sqlite_path) as conn:
        row = conn.execute(
            "SELECT device_id, dedupe_version, dedupe_basis_json, pdf_sha256, assay_block_hash FROM runs"
        ).fetchone()
    assert row[0] == "dev1"
    assert row[1] == "v2"
    assert '"TEST": "T"' in row[2]
    assert row[3] == "a" * 64
    assert row[4] == "b" * 64


def test_sqlite_writer_migrates_existing_runs_table(tmp_path: Path):
    sqlite_path = tmp_path / "existing.sqlite3"
    with sqlite3.connect(sqlite_path) as conn:
        conn.execute(
            """
            CREATE TABLE runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                pdf_path TEXT NOT NULL,
                assay_key TEXT NOT NULL,
                lot_id TEXT NOT NULL,
                dedupe_key TEXT NOT NULL,
                ruleset_file TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(assay_key, dedupe_key)
            )
            """
        )

    ruleset = RuleSet(
        assay_key="(1111)",
        ruleset_file="Test.json",
        data={"assay_name": "AssayA", "lot_rule": {}, "extract_rules": {}, "excel_rules": {}},
    )
    record = AssayRecord(
        assay_key="(1111)",
        lot_id="LOT1",
        dedupe_key="K1",
        data={},
        device_id="dev1",
        dedupe_version="v2",
        dedupe_basis={"device_id": "dev1"},
    )
    write_record_sqlite(record, ruleset, str(sqlite_path))

    with sqlite3.connect(sqlite_path) as conn:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(runs)").fetchall()}
    assert {"device_id", "dedupe_version", "dedupe_basis_json", "pdf_sha256", "assay_block_hash"} <= cols
