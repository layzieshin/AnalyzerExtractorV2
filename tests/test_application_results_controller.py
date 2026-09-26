from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from src.application.api import PathOpenError, ReportNotFoundError, ResultsController, create_desktop_services


def _create_runs_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    try:
        conn.execute(
            """
            CREATE TABLE runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT,
                pdf_path TEXT,
                assay_key TEXT,
                lot_id TEXT,
                dedupe_key TEXT,
                device_id TEXT,
                dedupe_version TEXT,
                dedupe_basis_json TEXT,
                pdf_sha256 TEXT,
                assay_block_hash TEXT,
                ruleset_file TEXT,
                payload_json TEXT,
                created_at TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO runs (
                job_id, pdf_path, assay_key, lot_id, dedupe_key, device_id,
                dedupe_version, dedupe_basis_json, pdf_sha256, assay_block_hash,
                ruleset_file, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "job1",
                "/tmp/a.pdf",
                "(1111)",
                "LOT-A",
                "K1",
                "dev1",
                "v1",
                json.dumps({"basis": "x"}),
                "sha",
                "block",
                "AssayA.json",
                json.dumps({"DATUM": "2026-01-01"}),
                "2026-01-01T10:00:00Z",
            ),
        )
        conn.execute(
            """
            INSERT INTO runs (
                job_id, pdf_path, assay_key, lot_id, dedupe_key, device_id,
                payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "job2",
                "/tmp/b.pdf",
                "(2222)",
                "LOT-B",
                "K2",
                "dev2",
                "{invalid",
                "2026-01-02T10:00:00Z",
            ),
        )
        conn.commit()
    finally:
        conn.close()


def test_missing_db_is_not_created(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    db = root / "missing.sqlite3"
    services = create_desktop_services(root)
    services.settings.save(
        services.settings.load().__class__(
            output_mode="both",
            sqlite_path=str(db),
            watch_input_path=str(root / "input" / "watch"),
            device_id=None,
        )
    )
    services = create_desktop_services(root)

    status = services.results.get_store_status()
    assert status.available is False
    assert not db.exists()


def test_results_read_only_list_and_detail(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    db = root / "runs.sqlite3"
    _create_runs_db(db)

    settings = create_desktop_services(root).settings
    settings.save(
        settings.load().__class__(
            output_mode="both",
            sqlite_path=str(db),
            watch_input_path=str(root / "input" / "watch"),
            device_id=None,
        )
    )
    services = create_desktop_services(root)

    status = services.results.get_store_status()
    assert status.available is True

    assays = services.results.list_assays()
    assert [item.assay_key for item in assays] == ["(1111)", "(2222)"]

    charges = services.results.list_charges("(1111)")
    assert charges[0].lot_id == "LOT-A"

    all_runs = services.results.list_runs(limit=1)
    assert all_runs.total_returned == 1
    assert all_runs.truncated is True

    detail = services.results.get_run_detail(2)
    assert detail is not None
    assert detail.payload_parse_error


def test_results_uses_updated_sqlite_path_without_service_rebuild(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    first_db = root / "first.sqlite3"
    second_db = root / "second.sqlite3"
    _create_runs_db(first_db)

    services = create_desktop_services(root)
    services.settings.save(
        services.settings.load().__class__(
            output_mode="both",
            sqlite_path=str(first_db),
            watch_input_path=str(root / "input" / "watch"),
            device_id=None,
        )
    )

    assert services.results.get_store_status().available is True
    assert len(services.results.list_assays()) == 2

    _create_runs_db(second_db)
    services.settings.save(
        services.settings.load().__class__(
            output_mode="both",
            sqlite_path=str(second_db),
            watch_input_path=str(root / "input" / "watch"),
            device_id=None,
        )
    )

    status = services.results.get_store_status()
    assert status.path == str(second_db)
    assert status.available is True
    assert len(services.results.list_assays()) == 2


def test_list_recent_reports_groups_runs_by_job_and_pdf(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    db = root / "runs.sqlite3"
    _create_runs_db(db)
    services = create_desktop_services(root)
    services.settings.save(
        services.settings.load().__class__(
            output_mode="both",
            sqlite_path=str(db),
            watch_input_path=str(root / "input" / "watch"),
            device_id=None,
        )
    )
    services = create_desktop_services(root)

    reports = services.results.list_recent_reports(limit=10)
    assert len(reports) == 2
    job1_report = next(item for item in reports if item.job_id == "job1")
    assert job1_report.run_count == 1
    assert job1_report.assay_count == 1


def test_report_id_legacy_fallback_without_job_id(tmp_path: Path) -> None:
    from src.resultstore.api import compute_report_id

    pdf_path = str((tmp_path / "legacy.pdf").resolve(strict=False))
    report_id = compute_report_id("", pdf_path=pdf_path, created_at="2026-01-01T10:00:00Z")
    assert report_id == compute_report_id("", pdf_path=pdf_path, created_at="2026-01-01T10:00:00+00:00")
    assert report_id == compute_report_id("", pdf_path=pdf_path, created_at="2026-01-01T10:00:00")


def test_get_report_detail_groups_assay_fields(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    db = root / "runs.sqlite3"
    _create_runs_db(db)
    services = create_desktop_services(root)
    services.settings.save(
        services.settings.load().__class__(
            output_mode="both",
            sqlite_path=str(db),
            watch_input_path=str(root / "input" / "watch"),
            device_id=None,
        )
    )
    services = create_desktop_services(root)
    report_id = next(item.report_id for item in services.results.list_recent_reports(limit=10) if item.job_id == "job1")

    detail = services.results.get_report_detail(report_id)
    assert detail is not None
    assert detail.assay_groups
    assay_group = next(group for group in detail.assay_groups if group.assay_key == "(1111)")
    assert assay_group.occurrences
    assert assay_group.occurrences[0].fields
    assert assay_group.occurrences[0].fields[0].field_key == "DATUM"


def test_open_report_pdf_uses_injected_opener(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    db = root / "runs.sqlite3"
    pdf = root / "current.pdf"
    pdf.write_bytes(b"pdf")
    _create_runs_db_with_pdf(db, str(pdf))
    services = create_desktop_services(root)
    services.settings.save(
        services.settings.load().__class__(
            output_mode="both",
            sqlite_path=str(db),
            watch_input_path=str(root / "input" / "watch"),
            device_id=None,
        )
    )
    opened: list[str] = []

    def fake_opener(path: str) -> None:
        opened.append(path)

    controller = ResultsController(root, settings_provider=services.settings.load, path_opener=fake_opener)
    report_id = controller.list_recent_reports(limit=1)[0].report_id
    opened_path = controller.open_report_pdf(report_id)
    assert opened == [str(pdf.resolve(strict=False))]
    assert opened_path == str(pdf.resolve(strict=False))


def test_open_report_pdf_raises_report_not_found(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    services = create_desktop_services(root)
    with pytest.raises(ReportNotFoundError):
        services.results.open_report_pdf("does-not-exist")


def _create_runs_db_with_pdf(path: Path, pdf_path: str, *, job_id: str = "job1") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    try:
        conn.execute(
            """
            CREATE TABLE runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT,
                pdf_path TEXT,
                assay_key TEXT,
                lot_id TEXT,
                dedupe_key TEXT,
                device_id TEXT,
                dedupe_version TEXT,
                dedupe_basis_json TEXT,
                pdf_sha256 TEXT,
                assay_block_hash TEXT,
                ruleset_file TEXT,
                payload_json TEXT,
                created_at TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO runs (
                job_id, pdf_path, assay_key, lot_id, dedupe_key, device_id,
                dedupe_version, dedupe_basis_json, pdf_sha256, assay_block_hash,
                ruleset_file, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                pdf_path,
                "(1111)",
                "LOT-A",
                "K1",
                "dev1",
                "v1",
                json.dumps({"basis": "x"}),
                "sha",
                "block",
                "AssayA.json",
                json.dumps({"DATUM": "2026-01-01"}),
                "2026-01-01T10:00:00Z",
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _configure_results_services(root: Path, db: Path):
    services = create_desktop_services(root)
    services.settings.save(
        services.settings.load().__class__(
            output_mode="both",
            sqlite_path=str(db),
            watch_input_path=str(root / "input" / "watch"),
            device_id=None,
        )
    )
    return create_desktop_services(root)


def test_one_job_with_different_pdf_paths_is_one_report(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    db = root / "runs.sqlite3"
    _create_runs_db(db)
    conn = sqlite3.connect(str(db))
    conn.execute(
        "UPDATE runs SET job_id = 'job1', pdf_path = '/tmp/other.pdf' WHERE id = 2"
    )
    conn.commit()
    conn.close()
    services = _configure_results_services(root, db)
    reports = services.results.list_recent_reports(limit=10)
    job_reports = [item for item in reports if item.job_id == "job1"]
    assert len(job_reports) == 1
    assert job_reports[0].run_count == 2


def test_report_detail_keeps_all_repeated_assay_occurrences(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    db = root / "runs.sqlite3"
    _create_runs_db(db)
    conn = sqlite3.connect(str(db))
    conn.execute(
        """
        INSERT INTO runs (
            job_id, pdf_path, assay_key, lot_id, dedupe_key, device_id,
            payload_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "job1",
            "/tmp/a.pdf",
            "(1111)",
            "LOT-C",
            "K3",
            "dev1",
            json.dumps({"DATUM": "2026-01-03"}),
            "2026-01-03T10:00:00Z",
        ),
    )
    conn.commit()
    conn.close()
    services = _configure_results_services(root, db)
    report_id = next(item.report_id for item in services.results.list_recent_reports(limit=10) if item.job_id == "job1")
    detail = services.results.get_report_detail(report_id)
    assert detail is not None
    group = next(group for group in detail.assay_groups if group.assay_key == "(1111)")
    assert len(group.occurrences) == 2
    lots = {item.lot_id for item in group.occurrences}
    assert lots == {"LOT-A", "LOT-C"}


def test_report_with_more_than_twenty_runs_stays_complete(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    db = root / "runs.sqlite3"
    _create_runs_db(db)
    conn = sqlite3.connect(str(db))
    for idx in range(25):
        conn.execute(
            """
            INSERT INTO runs (
                job_id, pdf_path, assay_key, lot_id, dedupe_key, device_id,
                payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "job-big",
                "/tmp/big.pdf",
                "(1111)",
                f"LOT-{idx}",
                f"K{idx}",
                "dev1",
                json.dumps({"idx": idx}),
                f"2026-02-{idx + 1:02d}T10:00:00Z",
            ),
        )
    conn.commit()
    conn.close()
    services = _configure_results_services(root, db)
    report_id = next(item.report_id for item in services.results.list_recent_reports(limit=50) if item.job_id == "job-big")
    detail = services.results.get_report_detail(report_id)
    assert detail is not None
    group = next(group for group in detail.assay_groups if group.assay_key == "(1111)")
    assert len(group.occurrences) == 25


def test_old_report_remains_addressable_beyond_recent_rows(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    db = root / "runs.sqlite3"
    _create_runs_db(db)
    conn = sqlite3.connect(str(db))
    conn.execute(
        """
        INSERT INTO runs (
            job_id, pdf_path, assay_key, lot_id, dedupe_key, device_id,
            payload_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "job-old",
            "/tmp/old.pdf",
            "(9999)",
            "LOT-OLD",
            "KOLD",
            "dev-old",
            json.dumps({"DATUM": "2020-01-01"}),
            "2020-01-01T10:00:00Z",
        ),
    )
    for idx in range(2100):
        conn.execute(
            """
            INSERT INTO runs (
                job_id, pdf_path, assay_key, lot_id, dedupe_key, device_id,
                payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"noise-{idx}",
                f"/tmp/noise-{idx}.pdf",
                "(2222)",
                "LOT-N",
                f"N{idx}",
                "dev-noise",
                "{}",
                f"2026-03-{idx % 28 + 1:02d}T10:00:00Z",
            ),
        )
    conn.commit()
    conn.close()
    services = _configure_results_services(root, db)
    detail = services.results.get_report_detail("job-old")
    assert detail is not None
    assert detail.job_id == "job-old"
    assert detail.assay_groups[0].assay_key == "(9999)"


def test_duplicate_field_comparison_preserves_falsy_values() -> None:
    from src.application.results_controller import _to_field_comparison

    rows = _to_field_comparison(
        [
            {"field": "count", "existing": 0, "candidate": 0, "same": True},
            {"field": "flag", "existing": False, "candidate": True, "same": False},
        ]
    )
    assert rows[0].existing_value == "0"
    assert rows[0].candidate_value == "0"
    assert rows[0].changed is False
    assert rows[1].existing_value == "False"
    assert rows[1].candidate_value == "True"
    assert rows[1].changed is True


def test_report_status_uses_queue_failed_not_done(tmp_path: Path) -> None:
    from src.jobqueue.api import claim_next_job, enqueue_pdf_job, mark_job_failed

    root = tmp_path / "proj"
    root.mkdir()
    db = root / "runs.sqlite3"
    pdf = root / "fail.pdf"
    pdf.write_bytes(b"fail")
    job = enqueue_pdf_job(str(root), str(pdf), source="test-app-manual")
    claimed = claim_next_job(str(root), "w-test")
    assert claimed is not None
    mark_job_failed(str(root), job.job_id, worker_id="w-test", error="validation_failed")
    _create_runs_db_with_pdf(db, str(pdf), job_id=job.job_id)
    services = _configure_results_services(root, db)
    report = services.results.list_recent_reports(limit=1)[0]
    assert report.display_status == "Verarbeitung fehlgeschlagen"


def test_report_status_ledger_failed_without_queue_is_not_done(tmp_path: Path) -> None:
    import json

    from src.ingestion.api import SOURCE_MANUAL, register_import
    from src.jobqueue.api import enqueue_pdf_job

    root = tmp_path / "proj"
    root.mkdir()
    db = root / "runs.sqlite3"
    pdf = root / "ledger-fail.pdf"
    pdf.write_bytes(b"ledger-fail")

    def enqueue(pdf_path: str, source: str, expected_sha256: str | None):
        return enqueue_pdf_job(str(root), pdf_path, source=source, expected_sha256=expected_sha256)

    record = register_import(
        root,
        str(pdf),
        source_kind=SOURCE_MANUAL,
        enqueue=enqueue,
        source_label="manual",
    ).record
    for queue_file in (root / "jobs" / "queue").glob("*.json"):
        queue_file.unlink()
    ledger_path = root / "storage" / "ingestion" / f"{record.ingestion_id}.json"
    payload = json.loads(ledger_path.read_text(encoding="utf-8"))
    payload["processing_status"] = "FAILED"
    ledger_path.write_text(json.dumps(payload), encoding="utf-8")
    _create_runs_db_with_pdf(db, str(pdf), job_id=record.processing_job_id)
    services = _configure_results_services(root, db)
    report = services.results.list_recent_reports(limit=1)[0]
    assert report.display_status == "Verarbeitung fehlgeschlagen"


def test_report_status_empty_job_id_legacy_without_queue_or_ledger_is_done(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    db = root / "runs.sqlite3"
    pdf = root / "legacy-done.pdf"
    pdf.write_bytes(b"legacy")
    _create_runs_db_with_pdf(db, str(pdf), job_id="")
    services = _configure_results_services(root, db)
    report = services.results.list_recent_reports(limit=1)[0]
    assert report.job_id == ""
    assert report.display_status == "Fertig"
    assert report.path_available is True


def test_report_status_job_id_without_queue_or_ledger_is_unknown(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    db = root / "runs.sqlite3"
    pdf = root / "orphan-job.pdf"
    pdf.write_bytes(b"orphan")
    _create_runs_db_with_pdf(db, str(pdf), job_id="orphan-job")
    services = _configure_results_services(root, db)
    report = services.results.list_recent_reports(limit=1)[0]
    assert report.job_id == "orphan-job"
    assert report.display_status == "Unbekannt"


def test_report_open_uses_archived_current_path(tmp_path: Path) -> None:
    import json

    from src.ingestion.api import SOURCE_MANUAL, register_import
    from src.jobqueue.api import enqueue_pdf_job

    root = tmp_path / "proj"
    root.mkdir()
    db = root / "runs.sqlite3"
    backup = root / "backup"
    backup.mkdir()
    pdf = root / "watch" / "archived.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"archived")

    def enqueue(pdf_path: str, source: str, expected_sha256: str | None):
        return enqueue_pdf_job(str(root), pdf_path, source=source, expected_sha256=expected_sha256)

    record = register_import(
        root,
        str(pdf),
        source_kind=SOURCE_MANUAL,
        enqueue=enqueue,
        source_label="manual",
    ).record
    archived = backup / "archived.pdf"
    archived.write_bytes(b"archived")
    ledger_path = root / "storage" / "ingestion" / f"{record.ingestion_id}.json"
    payload = json.loads(ledger_path.read_text(encoding="utf-8"))
    payload["current_path"] = str(archived)
    payload["archive_status"] = "ARCHIVED"
    ledger_path.write_text(json.dumps(payload), encoding="utf-8")
    pdf.unlink()
    _create_runs_db_with_pdf(db, str(pdf), job_id=record.processing_job_id)
    services = _configure_results_services(root, db)
    report = services.results.list_recent_reports(limit=1)[0]
    assert report.path_available is True
    assert Path(report.current_pdf_path).is_file()
    opened: list[str] = []

    def fake_opener(path: str) -> None:
        opened.append(path)

    controller = ResultsController(root, settings_provider=services.settings.load, path_opener=fake_opener)
    opened_path = controller.open_report_pdf(report.report_id)
    assert opened == [str(archived.resolve(strict=False))]


def test_report_ambiguous_path_blocks_open(tmp_path: Path) -> None:
    import uuid

    from src.application.api import PathOpenError
    from src.ingestion.api import SOURCE_MANUAL, register_import
    from src.ingestion.store import save_record, update_record
    from src.jobqueue.api import enqueue_pdf_job

    root = tmp_path / "proj"
    root.mkdir()
    db = root / "runs.sqlite3"
    pdf = root / "ambiguous.pdf"
    pdf.write_bytes(b"ambiguous")

    def enqueue(pdf_path: str, source: str, expected_sha256: str | None):
        return enqueue_pdf_job(str(root), pdf_path, source=source, expected_sha256=expected_sha256)

    first = register_import(
        root,
        str(pdf),
        source_kind=SOURCE_MANUAL,
        enqueue=enqueue,
        source_label="manual",
    ).record
    duplicate = update_record(first, ingestion_id=str(uuid.uuid4()))
    save_record(root, duplicate)
    _create_runs_db_with_pdf(db, str(pdf), job_id=first.processing_job_id)
    services = _configure_results_services(root, db)
    report = services.results.list_recent_reports(limit=1)[0]
    detail = services.results.get_report_detail(report.report_id)
    assert detail is not None
    assert detail.path_status == "ambiguous"
    assert detail.archive_status == ""
    with pytest.raises(PathOpenError, match="report_pdf_ambiguous"):
        services.results.open_report_pdf(report.report_id)


def _duplicate_ruleset() -> "RuleSet":
    from src.ruleresolver.model import RuleSet

    return RuleSet(
        assay_key="(1111)",
        ruleset_file="Test.json",
        data={"assay_name": "AssayA", "lot_rule": {}, "extract_rules": {}, "excel_rules": {}},
    )


def test_duplicate_controller_list_detail_and_discard(tmp_path: Path) -> None:
    from src.dbwriter.api import write_record_sqlite
    from src.extractor.model import AssayRecord

    root = tmp_path / "proj"
    root.mkdir()
    db = root / "results.sqlite3"
    ruleset = _duplicate_ruleset()
    record = AssayRecord(
        assay_key="(1111)",
        lot_id="LOT1",
        dedupe_key="T|2026-01-01|10:00:00",
        data={"test": "T", "date": "2026-01-01", "time": "10:00:00", "count": 0},
        device_id="dev1",
        dedupe_version="v2",
        dedupe_basis={"device_id": "dev1", "TEST": "T"},
    )
    duplicate = AssayRecord(
        assay_key="(1111)",
        lot_id="LOT1",
        dedupe_key="T|2026-01-01|10:00:00",
        data={"test": "T2", "date": "2026-01-01", "time": "10:00:00", "count": 0},
        device_id="dev1",
        dedupe_version="v2",
        dedupe_basis={"device_id": "dev1", "TEST": "T"},
    )
    first = write_record_sqlite(
        record,
        ruleset,
        str(db),
        job_id="j1",
        pdf_path="a.pdf",
        pdf_sha256="a" * 64,
        assay_block_hash="b" * 64,
    )
    second = write_record_sqlite(
        duplicate,
        ruleset,
        str(db),
        job_id="j2",
        pdf_path="b.pdf",
        pdf_sha256="c" * 64,
        assay_block_hash="d" * 64,
    )
    services = _configure_results_services(root, db)
    items = services.results.list_duplicate_candidates(status="pending")
    assert len(items) == 1
    item = items[0]
    assert item.dedupe_basis == {"device_id": "dev1", "TEST": "T"}
    assert item.pdf_sha256 == "c" * 64
    detail = services.results.get_duplicate_candidate_detail(int(second.duplicate_candidate_id))
    assert detail is not None
    assert detail.existing is not None
    assert detail.existing.run_id == int(first.run_id)
    assert detail.existing.job_id == "j1"
    assert detail.existing.dedupe_basis == {"device_id": "dev1", "TEST": "T"}
    assert detail.candidate.dedupe_basis == {"device_id": "dev1", "TEST": "T"}
    zero_field = next(row for row in detail.field_comparison if row.field_key == "count")
    assert zero_field.existing_value == "0"
    assert zero_field.candidate_value == "0"
    assert zero_field.changed is False
    result = services.results.discard_duplicate_candidate(int(second.duplicate_candidate_id), note="ignore")
    assert result.status == "deleted"
    assert services.results.list_duplicate_candidates(status="pending") == []


def _insert_same_job_runs(path: Path, *, count: int = 2) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    try:
        conn.execute(
            """
            CREATE TABLE runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT,
                pdf_path TEXT,
                assay_key TEXT,
                lot_id TEXT,
                dedupe_key TEXT,
                device_id TEXT,
                payload_json TEXT,
                created_at TEXT
            )
            """
        )
        for index in range(count):
            conn.execute(
                """
                INSERT INTO runs (
                    job_id, pdf_path, assay_key, lot_id, dedupe_key, device_id,
                    payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "job-shared",
                    "/tmp/shared.pdf",
                    f"(assay-{index})",
                    f"LOT-{index}",
                    f"K{index}",
                    "dev1",
                    json.dumps({"DATUM": "2026-01-01", "WERT": index}),
                    "2026-01-01T10:00:00Z",
                ),
            )
        conn.commit()
    finally:
        conn.close()


def _runs_table_snapshot(path: Path) -> tuple[list[tuple[object, ...]], list[tuple[object, ...]]]:
    conn = sqlite3.connect(str(path))
    try:
        columns = conn.execute("PRAGMA table_info(runs)").fetchall()
        rows = conn.execute("SELECT * FROM runs ORDER BY id").fetchall()
    finally:
        conn.close()
    return columns, rows


def test_report_validation_status_partial_then_complete_and_runs_stay_unchanged(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    db = root / "runs.sqlite3"
    _insert_same_job_runs(db)
    before = _runs_table_snapshot(db)
    services = _configure_results_services(root, db)

    reports = services.results.list_recent_reports()
    assert len(reports) == 1
    assert reports[0].validation_status == "Unvalidiert"
    assert reports[0].report_status == "Unvalidiert"
    assert reports[0].display_status == "Unbekannt"

    detail = services.results.get_report_detail(reports[0].report_id)
    assert detail is not None
    run_ids = [occurrence.run_id for group in detail.assay_groups for occurrence in group.occurrences]
    assert run_ids == [1, 2]

    services.results.validate_report_run(detail.report_id, 1, "  AB ", " ok ")
    partial = services.results.list_recent_reports()[0]
    assert partial.validation_status == "Teilweise validiert"
    assert partial.report_status == "Teilweise validiert"

    services.results.validate_report_run(detail.report_id, 2, "AB")
    complete = services.results.get_report_detail(detail.report_id)
    assert complete is not None
    assert complete.validation_status == "Validiert"
    assert complete.report_status == "Validiert"
    validated = [
        occurrence.current_validation.operator_initials
        for group in complete.assay_groups
        for occurrence in group.occurrences
        if occurrence.current_validation is not None
    ]
    assert validated == ["AB", "AB"]
    assert _runs_table_snapshot(db) == before


def test_open_validation_cases_are_per_assay_run_and_refresh_after_validation(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    db = root / "runs.sqlite3"
    _insert_same_job_runs(db)
    services = _configure_results_services(root, db)

    open_cases = services.results.list_open_validation_cases()
    assert [(item.run_id, item.assay_key) for item in open_cases] == [(2, "(assay-1)"), (1, "(assay-0)")]
    assert all(not item.validation_ambiguous for item in open_cases)

    services.results.validate_report_run(open_cases[0].report_id, open_cases[0].run_id, "AB")
    assert [item.run_id for item in services.results.list_open_validation_cases()] == [1]


def test_open_validation_cases_scan_beyond_first_500_runs(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    db = root / "runs.sqlite3"
    _insert_same_job_runs(db, count=501)
    with sqlite3.connect(str(db)) as conn:
        conn.execute(
            """
            CREATE TABLE run_validations (
                validation_id INTEGER PRIMARY KEY,
                run_id INTEGER NOT NULL,
                operator_initials TEXT NOT NULL,
                validated_at_utc TEXT NOT NULL,
                comment TEXT NOT NULL DEFAULT '',
                supersedes_validation_id INTEGER,
                created_at_utc TEXT
            )
            """
        )
        conn.executemany(
            """
            INSERT INTO run_validations (
                validation_id, run_id, operator_initials, validated_at_utc, comment,
                supersedes_validation_id, created_at_utc
            ) VALUES (?, ?, 'AB', '2026-01-01T10:00:00Z', '', NULL, '2026-01-01T10:00:00Z')
            """,
            ((run_id, run_id) for run_id in range(2, 502)),
        )
        conn.commit()
    services = _configure_results_services(root, db)

    open_cases = services.results.list_open_validation_cases()
    assert [item.run_id for item in open_cases] == [1]
    assert [item.run_id for item in services.results.list_open_validation_cases(limit=1)] == [1]


def test_open_validation_cases_exclude_payload_rework_and_include_ambiguous(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    db = root / "runs.sqlite3"
    _create_runs_db(db)
    services = _configure_results_services(root, db)

    assert [item.run_id for item in services.results.list_open_validation_cases()] == [1]
    with sqlite3.connect(str(db)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS run_validations (
                validation_id INTEGER PRIMARY KEY,
                run_id INTEGER NOT NULL,
                operator_initials TEXT NOT NULL,
                validated_at_utc TEXT NOT NULL,
                comment TEXT NOT NULL DEFAULT '',
                supersedes_validation_id INTEGER,
                created_at_utc TEXT
            )
            """
        )
        conn.executemany(
            """
            INSERT INTO run_validations (
                validation_id, run_id, operator_initials, validated_at_utc, comment,
                supersedes_validation_id, created_at_utc
            ) VALUES (?, 1, ?, '2026-01-01T10:00:00Z', '', NULL, '2026-01-01T10:00:00Z')
            """,
            ((1, "AB"), (2, "CD")),
        )
        conn.commit()

    ambiguous = services.results.list_open_validation_cases()
    assert len(ambiguous) == 1
    assert ambiguous[0].run_id == 1
    assert ambiguous[0].validation_ambiguous is True


def test_open_validation_cases_exclude_failed_processing(tmp_path: Path) -> None:
    from src.jobqueue.api import claim_next_job, enqueue_pdf_job, mark_job_failed

    root = tmp_path / "proj"
    root.mkdir()
    db = root / "runs.sqlite3"
    pdf = root / "fail.pdf"
    pdf.write_bytes(b"fail")
    job = enqueue_pdf_job(str(root), str(pdf), source="test-app-manual")
    assert claim_next_job(str(root), "w-test") is not None
    mark_job_failed(str(root), job.job_id, worker_id="w-test", error="configured_fields_empty: note")
    _create_runs_db_with_pdf(db, str(pdf), job_id=job.job_id)
    services = _configure_results_services(root, db)

    assert services.results.list_open_validation_cases() == []


@pytest.mark.parametrize("queue_status", ["PENDING", "PROCESSING"])
def test_open_validation_cases_exclude_nonterminal_processing(
    tmp_path: Path, queue_status: str
) -> None:
    from src.jobqueue.api import claim_next_job, enqueue_pdf_job

    root = tmp_path / "proj"
    root.mkdir()
    db = root / "runs.sqlite3"
    pdf = root / "partial.pdf"
    pdf.write_bytes(b"partial")
    job = enqueue_pdf_job(str(root), str(pdf), source="test-app-manual")
    if queue_status == "PROCESSING":
        assert claim_next_job(str(root), "w-test") is not None
    _create_runs_db_with_pdf(db, str(pdf), job_id=job.job_id)
    (root / "jobs" / f"{job.job_id}.json").write_text(
        json.dumps(
            {
                "job_id": job.job_id,
                "pdf_path": str(pdf),
                "status": "OUTPUT_PLANNED",
                "structured_status": "pending",
                "steps": [],
            }
        ),
        encoding="utf-8",
    )
    services = _configure_results_services(root, db)
    assert services.results.list_open_validation_cases() == []


def test_failed_processing_status_dominates_validation(tmp_path: Path) -> None:
    from src.jobqueue.api import claim_next_job, enqueue_pdf_job, mark_job_failed

    root = tmp_path / "proj"
    root.mkdir()
    db = root / "runs.sqlite3"
    pdf = root / "fail.pdf"
    pdf.write_bytes(b"fail")
    job = enqueue_pdf_job(str(root), str(pdf), source="test-app-manual")
    claimed = claim_next_job(str(root), "w-test")
    assert claimed is not None
    mark_job_failed(str(root), job.job_id, worker_id="w-test", error="validation_failed")
    _create_runs_db_with_pdf(db, str(pdf), job_id=job.job_id)
    services = _configure_results_services(root, db)
    report = services.results.list_recent_reports(limit=1)[0]
    services.results.validate_report_run(report.report_id, 1, "AB")
    refreshed = services.results.list_recent_reports(limit=1)[0]
    assert refreshed.display_status == "Verarbeitung fehlgeschlagen"
    assert refreshed.validation_status == "Validiert"
    assert refreshed.report_status == "Prüfung erforderlich"


def test_payload_parse_error_dominates_validation_status(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    db = root / "runs.sqlite3"
    _create_runs_db(db)
    services = _configure_results_services(root, db)
    reports = {item.job_id: item for item in services.results.list_recent_reports()}
    assert reports["job1"].report_status == "Unvalidiert"
    assert reports["job2"].report_status == "Prüfung erforderlich"
    assert reports["job2"].display_status == "Unbekannt"


def test_validate_does_not_cross_reports_or_overwrite(tmp_path: Path) -> None:
    from src.application.api import ValidationConflictError, ValidationInputError

    root = tmp_path / "proj"
    root.mkdir()
    db = root / "runs.sqlite3"
    _create_runs_db(db)
    services = _configure_results_services(root, db)
    reports = {item.job_id: item for item in services.results.list_recent_reports()}

    with pytest.raises(ValidationInputError, match="run_not_in_report"):
        services.results.validate_report_run(reports["job1"].report_id, 2, "AB")
    with pytest.raises(ValidationInputError, match="operator_initials_required"):
        services.results.validate_report_run(reports["job1"].report_id, 1, "  ")

    services.results.validate_report_run(reports["job1"].report_id, 1, "AB", "erste")
    with pytest.raises(ValidationConflictError, match="validation_already_exists"):
        services.results.validate_report_run(reports["job1"].report_id, 1, "CD", "still")

    corrected = services.results.correct_report_run(reports["job1"].report_id, 1, "CD", "korrektur")
    assert corrected.supersedes_validation_id is not None
    detail = services.results.get_report_detail(reports["job1"].report_id)
    assert detail is not None
    occurrence = detail.assay_groups[0].occurrences[0]
    assert occurrence.current_validation is not None
    assert occurrence.current_validation.operator_initials == "CD"
    assert [item.operator_initials for item in occurrence.validation_history] == ["AB", "CD"]
    assert occurrence.validation_history[0].comment == "erste"


def test_validation_is_persisted_before_excel_release_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.jobcontroller.api import JobResult

    root = tmp_path / "proj"
    root.mkdir()
    db = root / "runs.sqlite3"
    _create_runs_db(db)
    services = _configure_results_services(root, db)
    report = {item.job_id: item for item in services.results.list_recent_reports()}["job1"]

    def fail_release(_root, job_id, run_id, **kwargs):
        with sqlite3.connect(db) as conn:
            stored = conn.execute("SELECT operator_initials FROM run_validations WHERE run_id = 1").fetchone()
        assert stored == ("AB",)
        assert job_id == "job1"
        assert run_id == 1
        assert kwargs["correction"] is False
        return JobResult(job_id=job_id, pdf_path="", status="FAILED", details={"error": "excel_write_failed_after_validation:(1111):locked"})

    monkeypatch.setattr("src.application.results_controller.release_validated_run", fail_release)
    saved = services.results.validate_report_run(report.report_id, 1, "AB")
    assert saved.operator_initials == "AB"
    assert saved.excel_export_status == "failed"
    assert saved.excel_export_error.startswith("excel_write_failed_after_validation:")
    assert services.results.list_open_validation_cases() == []
