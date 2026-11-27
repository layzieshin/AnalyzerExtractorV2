from pathlib import Path
import sqlite3

import pytest

from src.dbwriter.api import (
    discard_duplicate_candidate,
    get_duplicate_candidate,
    list_duplicate_candidates,
    write_record_sqlite,
)
from src.extractor.model import AssayRecord
from src.ruleresolver.model import RuleSet


def test_sqlite_writer_inserts_and_creates_duplicate_candidate(tmp_path: Path):
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
    duplicate = AssayRecord(
        assay_key="(1111)",
        lot_id="LOT1",
        dedupe_key="T|2026-01-01|10:00:00",
        data={"test": "T2", "date": "2026-01-01", "time": "10:00:00"},
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
    r2 = write_record_sqlite(
        duplicate,
        ruleset,
        str(sqlite_path),
        job_id="j2",
        pdf_path="b.pdf",
        pdf_sha256="c" * 64,
        assay_block_hash="d" * 64,
    )
    r3 = write_record_sqlite(
        duplicate,
        ruleset,
        str(sqlite_path),
        job_id="j2",
        pdf_path="b.pdf",
        pdf_sha256="c" * 64,
        assay_block_hash="d" * 64,
    )

    assert r1.status == "inserted"
    assert r1.run_id is not None
    assert r2.status == "duplicate_pending"
    assert r2.existing_run_id == r1.run_id
    assert r2.duplicate_candidate_id is not None
    assert r3.status == "duplicate_pending"
    assert r3.duplicate_candidate_id == r2.duplicate_candidate_id

    with sqlite3.connect(sqlite_path) as conn:
        row = conn.execute(
            "SELECT device_id, dedupe_version, dedupe_basis_json, pdf_sha256, assay_block_hash FROM runs"
        ).fetchone()
    assert row[0] == "dev1"
    assert row[1] == "v2"
    assert '"TEST": "T"' in row[2]
    assert row[3] == "a" * 64
    assert row[4] == "b" * 64

    candidates = list_duplicate_candidates(str(sqlite_path))
    assert len(candidates) == 1
    assert candidates[0]["candidate_id"] == r2.duplicate_candidate_id
    assert candidates[0]["existing_run_id"] == r1.run_id
    assert candidates[0]["pdf_sha256"] == "c" * 64

    detail = get_duplicate_candidate(str(sqlite_path), int(r2.duplicate_candidate_id))
    assert detail is not None
    assert detail["existing"]["run_id"] == r1.run_id
    assert detail["candidate"]["payload"]["test"] == "T2"
    comparison = {row["field"]: row for row in detail["field_comparison"]}
    assert comparison["test"]["existing"] == "T"
    assert comparison["test"]["candidate"] == "T2"
    assert comparison["test"]["same"] is False


def test_same_frozen_job_write_returns_real_run_id_without_duplicate_candidate(tmp_path: Path):
    sqlite_path = tmp_path / "results.sqlite3"
    ruleset = RuleSet(
        assay_key="(1111)",
        ruleset_file="Test.json",
        data={"assay_name": "AssayA", "excel_rules": {}},
    )
    record = AssayRecord(
        assay_key="(1111)", lot_id="LOT1", dedupe_key="K1",
        data={"value": "42"}, device_id="dev1", dedupe_version="v2",
    )
    kwargs = {
        "job_id": "job-1",
        "pdf_sha256": "a" * 64,
        "assay_block_hash": "b" * 64,
    }
    first = write_record_sqlite(record, ruleset, str(sqlite_path), **kwargs)
    resumed = write_record_sqlite(record, ruleset, str(sqlite_path), **kwargs)
    assert first.status == "inserted"
    assert resumed.status == "already_persisted"
    assert resumed.run_id == first.run_id
    assert resumed.existing_run_id is None
    assert list_duplicate_candidates(str(sqlite_path)) == []


def test_discard_duplicate_candidate_sets_deleted_and_writes_log(tmp_path: Path):
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
    duplicate = AssayRecord(
        assay_key="(1111)",
        lot_id="LOT1",
        dedupe_key="T|2026-01-01|10:00:00",
        data={"test": "T2", "date": "2026-01-01", "time": "10:00:00"},
        device_id="dev1",
        dedupe_version="v2",
        dedupe_basis={"device_id": "dev1", "TEST": "T"},
    )

    first = write_record_sqlite(record, ruleset, str(sqlite_path), job_id="j1", pdf_sha256="a")
    second = write_record_sqlite(duplicate, ruleset, str(sqlite_path), job_id="j2", pdf_sha256="b")
    assert first.status == "inserted"
    assert second.status == "duplicate_pending"
    candidate_id = int(second.duplicate_candidate_id)

    result = discard_duplicate_candidate(str(sqlite_path), candidate_id, decided_by="tester", note="false alarm")

    assert result["candidate_id"] == candidate_id
    assert result["status"] == "deleted"
    assert result["action"] == "discard"
    assert result["decision_by"] == "tester"
    assert result["decision_note"] == "false alarm"
    assert list_duplicate_candidates(str(sqlite_path), status="pending") == []
    deleted = list_duplicate_candidates(str(sqlite_path), status="deleted")
    assert len(deleted) == 1
    assert deleted[0]["candidate_id"] == candidate_id

    detail = get_duplicate_candidate(str(sqlite_path), candidate_id)
    assert detail is not None
    assert detail["candidate"]["status"] == "deleted"
    assert detail["candidate"]["decision_by"] == "tester"
    assert detail["candidate"]["decision_note"] == "false alarm"
    assert detail["existing"]["run_id"] == first.run_id

    with sqlite3.connect(sqlite_path) as conn:
        log_row = conn.execute(
            "SELECT candidate_id, action, decided_by, note FROM duplicate_decision_log"
        ).fetchone()
    assert log_row == (candidate_id, "discard", "tester", "false alarm")

    with pytest.raises(ValueError, match="candidate_not_pending"):
        discard_duplicate_candidate(str(sqlite_path), candidate_id)
    with pytest.raises(ValueError, match="candidate_not_found"):
        discard_duplicate_candidate(str(sqlite_path), candidate_id + 100)


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
    with sqlite3.connect(sqlite_path) as conn:
        duplicate_cols = {row[1] for row in conn.execute("PRAGMA table_info(duplicate_candidates)").fetchall()}
    assert {"existing_run_id", "candidate_payload_json", "candidate_meta_json", "detected_at"} <= duplicate_cols
    with sqlite3.connect(sqlite_path) as conn:
        log_cols = {row[1] for row in conn.execute("PRAGMA table_info(duplicate_decision_log)").fetchall()}
    assert {"candidate_id", "action", "decided_at", "decided_by", "note"} <= log_cols
