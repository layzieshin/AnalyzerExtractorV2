import json
import sqlite3
from pathlib import Path

import pytest

from src.resultstore.api import (
    compute_report_id,
    get_report_runs,
    get_result_run,
    get_result_store_status,
    list_report_summaries,
    list_result_assays,
    list_result_charges,
    list_result_runs,
)


def _store_spec(path: Path) -> dict[str, str]:
    return {"driver": "sqlite", "path": str(path)}


def _create_runs_db(path: Path, *, with_assay_key: bool = True, with_lot_id: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    try:
        cols = ["id INTEGER PRIMARY KEY AUTOINCREMENT"]
        if with_assay_key:
            cols.append("assay_key TEXT")
        if with_lot_id:
            cols.append("lot_id TEXT")
        cols.extend(
            [
                "job_id TEXT",
                "pdf_path TEXT",
                "dedupe_key TEXT",
                "device_id TEXT",
                "payload_json TEXT",
                "created_at TEXT",
            ]
        )
        conn.execute(f"CREATE TABLE runs ({', '.join(cols)})")
        if with_assay_key and with_lot_id:
            conn.execute(
                """
                INSERT INTO runs (job_id, pdf_path, assay_key, lot_id, dedupe_key, device_id, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "job1",
                    "/tmp/a.pdf",
                    "(1111)",
                    "LOT-A",
                    "K1",
                    "dev1",
                    json.dumps({"DATUM": "2026-01-01", "TEST": "1.2"}),
                    "2026-01-01T10:00:00Z",
                ),
            )
            conn.execute(
                """
                INSERT INTO runs (job_id, pdf_path, assay_key, lot_id, dedupe_key, device_id, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "job2",
                    "/tmp/b.pdf",
                    "(1111)",
                    "LOT-B",
                    "K2",
                    "dev2",
                    json.dumps({"date": "2026-01-02"}),
                    "2026-01-02T10:00:00Z",
                ),
            )
            conn.execute(
                """
                INSERT INTO runs (job_id, pdf_path, assay_key, lot_id, dedupe_key, device_id, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "job3",
                    "/tmp/c.pdf",
                    "(2222)",
                    "LOT-C",
                    "K3",
                    "dev3",
                    "{invalid",
                    "2026-01-03T10:00:00Z",
                ),
            )
        conn.commit()
    finally:
        conn.close()


def test_missing_db_is_not_created(tmp_path: Path):
    db = tmp_path / "missing.sqlite3"
    status = get_result_store_status(_store_spec(db))
    assert status["available"] is False
    assert not db.exists()


def test_empty_db_without_runs_table(tmp_path: Path):
    db = tmp_path / "empty.sqlite3"
    conn = sqlite3.connect(str(db))
    conn.close()
    status = get_result_store_status(_store_spec(db))
    assert status["available"] is False
    assert list_result_assays(_store_spec(db)) == []


def test_list_assays_and_charges(tmp_path: Path):
    db = tmp_path / "runs.sqlite3"
    _create_runs_db(db)
    assays = list_result_assays(_store_spec(db))
    assert [row["assay_key"] for row in assays] == ["(1111)", "(2222)"]
    charges = list_result_charges(_store_spec(db), "(1111)")
    assert [row["lot_id"] for row in charges] == ["LOT-A", "LOT-B"]


def test_list_runs_filter_and_decode(tmp_path: Path):
    db = tmp_path / "runs.sqlite3"
    _create_runs_db(db)
    spec = _store_spec(db)

    all_runs = list_result_runs(spec, assay_key="(1111)")
    assert all_runs["total_returned"] == 2
    assert all_runs["truncated"] is False
    assert all_runs["runs"][0]["result_date"] in {"2026-01-01", "2026-01-02"}

    charge_runs = list_result_runs(spec, assay_key="(1111)", charge="LOT-A")
    assert charge_runs["total_returned"] == 1
    assert charge_runs["runs"][0]["lot_id"] == "LOT-A"

    broken = list_result_runs(spec, assay_key="(2222)")
    assert broken["runs"][0]["payload_parse_error"]


def test_get_result_run(tmp_path: Path):
    db = tmp_path / "runs.sqlite3"
    _create_runs_db(db)
    run = get_result_run(_store_spec(db), 1)
    assert run is not None
    assert run["assay_key"] == "(1111)"


def test_old_db_without_assay_key_column(tmp_path: Path):
    db = tmp_path / "old.sqlite3"
    _create_runs_db(db, with_assay_key=False, with_lot_id=True)
    status = get_result_store_status(_store_spec(db))
    assert "assay_key" in status["missing_core_columns"]
    assert list_result_assays(_store_spec(db)) == []


def test_old_db_without_lot_id_column(tmp_path: Path):
    db = tmp_path / "old.sqlite3"
    _create_runs_db(db, with_assay_key=True, with_lot_id=False)
    status = get_result_store_status(_store_spec(db))
    assert "lot_id" in status["missing_core_columns"]
    assert list_result_charges(_store_spec(db), "(1111)") == []


def test_list_runs_truncated(tmp_path: Path):
    db = tmp_path / "many.sqlite3"
    _create_runs_db(db)
    conn = sqlite3.connect(str(db))
    try:
        for idx in range(600):
            conn.execute(
                """
                INSERT INTO runs (job_id, pdf_path, assay_key, lot_id, dedupe_key, device_id, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"job{idx}",
                    f"/tmp/{idx}.pdf",
                    "(1111)",
                    "LOT-A",
                    f"K{idx}",
                    "dev1",
                    "{}",
                    "2026-01-01T10:00:00Z",
                ),
            )
        conn.commit()
    finally:
        conn.close()

    result = list_result_runs(_store_spec(db), assay_key="(1111)", limit=500)
    assert result["truncated"] is True
    assert result["total_returned"] == 500
    assert result["offset"] == 0

    second_page = list_result_runs(_store_spec(db), assay_key="(1111)", limit=500, offset=500)
    assert second_page["truncated"] is False
    assert second_page["total_returned"] == 102
    assert second_page["offset"] == 500
    assert {row["id"] for row in result["runs"]}.isdisjoint(
        {row["id"] for row in second_page["runs"]}
    )


def test_local_db_still_readable(tmp_path: Path):
    db = tmp_path / "runs.sqlite3"
    _create_runs_db(db)
    status = get_result_store_status(_store_spec(db))
    assert status["available"] is True
    assert status["message"] == "Datenbank bereit."


def test_unc_path_uses_direct_connect_not_uri(tmp_path: Path, monkeypatch):
    db = tmp_path / "runs.sqlite3"
    _create_runs_db(db)
    unc_path = Path(f"//medistar/share/{db.name}")
    calls: list[dict[str, object]] = []
    real_connect = sqlite3.connect
    real_is_file = Path.is_file

    def _fake_is_file(self: Path) -> bool:
        if str(self).startswith("\\\\medistar\\") or self.as_posix().startswith("//medistar/"):
            return True
        return real_is_file(self)

    def _fake_connect(target, *args, **kwargs):
        calls.append({"target": target, "uri": bool(kwargs.get("uri"))})
        if kwargs.get("uri"):
            raise sqlite3.OperationalError("invalid uri authority: medistar")
        if "medistar" in str(target):
            return real_connect(str(db))
        return real_connect(target)

    monkeypatch.setattr(Path, "is_file", _fake_is_file)
    monkeypatch.setattr(sqlite3, "connect", _fake_connect)
    monkeypatch.setattr(
        "src.resultstore.sqlite_store._is_unc_or_network_path",
        lambda _path: True,
    )

    status = get_result_store_status({"driver": "sqlite", "path": str(unc_path)})

    assert status["available"] is True
    assert calls
    assert all(not call["uri"] for call in calls)
    assert all("file://medistar" not in str(call["target"]) for call in calls)


def test_uri_invalid_authority_falls_back_to_direct(tmp_path: Path, monkeypatch):
    db = tmp_path / "runs.sqlite3"
    _create_runs_db(db)
    calls: list[dict[str, object]] = []
    real_connect = sqlite3.connect

    def _fake_connect(target, *args, **kwargs):
        calls.append({"target": target, "uri": bool(kwargs.get("uri"))})
        if kwargs.get("uri"):
            raise sqlite3.OperationalError("invalid uri authority: medistar")
        return real_connect(str(db))

    monkeypatch.setattr(sqlite3, "connect", _fake_connect)
    monkeypatch.setattr(
        "src.resultstore.sqlite_store._is_unc_or_network_path",
        lambda _path: False,
    )

    status = get_result_store_status(_store_spec(db))

    assert status["available"] is True
    assert len(calls) == 2
    assert calls[0]["uri"] is True
    assert calls[1]["uri"] is False


def test_direct_connect_sets_query_only(tmp_path: Path, monkeypatch):
    db = tmp_path / "runs.sqlite3"
    _create_runs_db(db)
    executed: list[str] = []
    real_connect = sqlite3.connect
    real_is_file = Path.is_file

    def _fake_is_file(self: Path) -> bool:
        if str(self).startswith("\\\\medistar\\") or self.as_posix().startswith("//medistar/"):
            return True
        return real_is_file(self)

    class _Conn:
        def __init__(self, inner: sqlite3.Connection) -> None:
            self._inner = inner

        def execute(self, sql: str, params=()):
            executed.append(sql)
            return self._inner.execute(sql, params)

        def __enter__(self):
            return self._inner.__enter__()

        def __exit__(self, *args):
            return self._inner.__exit__(*args)

    def _fake_connect(target, *args, **kwargs):
        if kwargs.get("uri"):
            raise sqlite3.OperationalError("invalid uri authority: medistar")
        connect_target = str(db) if "medistar" in str(target) else str(target)
        return _Conn(real_connect(connect_target))

    monkeypatch.setattr(Path, "is_file", _fake_is_file)
    monkeypatch.setattr(sqlite3, "connect", _fake_connect)
    monkeypatch.setattr(
        "src.resultstore.sqlite_store._is_unc_or_network_path",
        lambda _path: True,
    )

    get_result_store_status({"driver": "sqlite", "path": "//medistar/share/runs.sqlite3"})

    assert any("query_only" in sql for sql in executed)


def test_list_result_assays_after_uri_fallback(tmp_path: Path, monkeypatch):
    db = tmp_path / "runs.sqlite3"
    _create_runs_db(db)
    real_connect = sqlite3.connect

    def _fake_connect(target, *args, **kwargs):
        if kwargs.get("uri"):
            raise sqlite3.OperationalError("invalid uri authority: medistar")
        return real_connect(str(db))

    monkeypatch.setattr(sqlite3, "connect", _fake_connect)
    monkeypatch.setattr(
        "src.resultstore.sqlite_store._is_unc_or_network_path",
        lambda _path: False,
    )

    assays = list_result_assays(_store_spec(db))
    assert [row["assay_key"] for row in assays] == ["(1111)", "(2222)"]


def test_list_report_summaries_groups_by_job_id(tmp_path: Path):
    db = tmp_path / "runs.sqlite3"
    _create_runs_db(db)
    conn = sqlite3.connect(str(db))
    conn.execute("UPDATE runs SET job_id = 'job1' WHERE id = 2")
    conn.commit()
    conn.close()
    summaries = list_report_summaries(_store_spec(db), limit=10)
    job_reports = [row for row in summaries["reports"] if row["job_id"] == "job1"]
    assert len(job_reports) == 1
    assert job_reports[0]["run_count"] == 2


def test_get_report_runs_returns_all_occurrences(tmp_path: Path):
    db = tmp_path / "runs.sqlite3"
    _create_runs_db(db)
    conn = sqlite3.connect(str(db))
    for idx in range(22):
        conn.execute(
            """
            INSERT INTO runs (job_id, pdf_path, assay_key, lot_id, dedupe_key, device_id, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "job1",
                "/tmp/a.pdf",
                "(1111)",
                f"LOT-{idx}",
                f"K{idx}",
                "dev1",
                "{}",
                f"2026-04-{idx + 1:02d}T10:00:00Z",
            ),
        )
    conn.commit()
    conn.close()
    detail = get_report_runs(_store_spec(db), "job1")
    assert detail is not None
    assert len(detail["runs"]) == 23


def test_compute_report_id_uses_path_and_created_at_for_legacy(tmp_path: Path):
    pdf_path = str((tmp_path / "legacy.pdf").resolve(strict=False))
    by_time = compute_report_id("", pdf_path=pdf_path, created_at="2026-01-01T10:00:00Z")
    by_row = compute_report_id("", pdf_path=pdf_path, run_id=7)
    assert by_time != by_row
    assert by_time == compute_report_id("", pdf_path=pdf_path, created_at="2026-01-01T10:00:00+00:00")
    assert by_time == compute_report_id("", pdf_path=pdf_path, created_at="2026-01-01T10:00:00")


def test_compute_report_id_matches_list_report_summaries_for_legacy_cluster(tmp_path: Path):
    db = tmp_path / "legacy-id.sqlite3"
    _create_legacy_only_db(db)
    conn = sqlite3.connect(str(db))
    _insert_legacy_run(
        conn,
        pdf_path="/tmp/canonical-id.pdf",
        created_at="2026-01-01T10:00:00Z",
    )
    conn.commit()
    conn.close()
    spec = _store_spec(db)
    summaries = list_report_summaries(spec, limit=10)
    assert summaries["total_returned"] == 1
    listed_id = summaries["reports"][0]["report_id"]
    pdf_path = str(Path("/tmp/canonical-id.pdf").resolve(strict=False))
    computed_id = compute_report_id("", pdf_path=pdf_path, created_at="2026-01-01T10:00:00+00:00")
    assert computed_id == listed_id
    detail = get_report_runs(spec, listed_id)
    assert detail is not None
    assert detail["run_count"] == 1
    assert len(detail["runs"]) == 1


def test_report_summary_canonical_bounds_for_mixed_timestamp_formats(tmp_path: Path):
    db = tmp_path / "canonical-bounds.sqlite3"
    _create_legacy_only_db(db)
    conn = sqlite3.connect(str(db))
    cluster_path = "/tmp/canonical-bounds-cluster.pdf"
    _insert_legacy_run(conn, pdf_path=cluster_path, created_at="2026-01-01T10:00:00+02:00")
    _insert_legacy_run(conn, pdf_path=cluster_path, created_at="2026-01-01T08:00:02Z")
    _insert_legacy_run(conn, pdf_path=cluster_path, created_at="2026-01-01T08:00:00")
    _insert_legacy_run(
        conn,
        pdf_path="/tmp/canonical-bounds-newer.pdf",
        created_at="2026-01-01T09:00:00Z",
    )
    _insert_legacy_run(
        conn,
        pdf_path="/tmp/canonical-bounds-job.pdf",
        created_at="2026-01-01T10:00:00+02:00",
        job_id="mixed-job",
    )
    _insert_legacy_run(
        conn,
        pdf_path="/tmp/canonical-bounds-job.pdf",
        created_at="2026-01-01T08:00:02Z",
        job_id="mixed-job",
    )
    _insert_legacy_run(
        conn,
        pdf_path="/tmp/canonical-bounds-job.pdf",
        created_at="not-a-timestamp",
        job_id="mixed-job",
    )
    conn.commit()
    conn.close()
    spec = _store_spec(db)
    summaries = list_report_summaries(spec, limit=50)
    legacy_reports = [row for row in summaries["reports"] if not row.get("job_id")]
    assert len(legacy_reports) == 2
    clustered = next(row for row in legacy_reports if row["run_count"] == 3)
    assert clustered["earliest_created_at"] == "2026-01-01T08:00:00+00:00"
    assert clustered["latest_created_at"] == "2026-01-01T08:00:02+00:00"
    detail = get_report_runs(spec, clustered["report_id"])
    assert detail is not None
    assert detail["earliest_created_at"] == clustered["earliest_created_at"]
    assert detail["latest_created_at"] == clustered["latest_created_at"]
    assert legacy_reports[0]["latest_created_at"] == "2026-01-01T09:00:00+00:00"
    assert legacy_reports[0]["report_id"] != clustered["report_id"]
    assert legacy_reports[1]["report_id"] == clustered["report_id"]
    mixed_job = next(row for row in summaries["reports"] if row.get("job_id") == "mixed-job")
    assert mixed_job["run_count"] == 3
    assert mixed_job["earliest_created_at"] == "2026-01-01T08:00:00+00:00"
    assert mixed_job["latest_created_at"] == "2026-01-01T08:00:02+00:00"


def test_legacy_timestamp_formats_cluster_without_type_error(tmp_path: Path):
    db = tmp_path / "mixed-ts.sqlite3"
    _create_legacy_only_db(db)
    conn = sqlite3.connect(str(db))
    pdf_path = "/tmp/mixed-ts.pdf"
    _insert_legacy_run(conn, pdf_path=pdf_path, created_at="2026-01-01T10:00:00Z")
    _insert_legacy_run(conn, pdf_path=pdf_path, created_at="2026-01-01T10:00:02+00:00")
    _insert_legacy_run(conn, pdf_path=pdf_path, created_at="2026-01-01T10:00:04")
    _insert_legacy_run(conn, pdf_path=pdf_path, created_at="")
    _insert_legacy_run(conn, pdf_path=pdf_path, created_at="not-a-timestamp")
    _insert_legacy_run(conn, pdf_path=pdf_path, created_at="2026-01-01T10:00:20Z")
    conn.commit()
    conn.close()
    spec = _store_spec(db)
    summaries = list_report_summaries(spec, limit=50)
    legacy_reports = [row for row in summaries["reports"] if not row.get("job_id")]
    assert len(legacy_reports) == 4
    clustered = next(row for row in legacy_reports if row["run_count"] == 3)
    uncertain = [row for row in legacy_reports if row["run_count"] == 1]
    assert len(uncertain) == 3
    assert uncertain[0]["report_id"] != uncertain[1]["report_id"]
    detail = get_report_runs(spec, clustered["report_id"])
    assert detail is not None
    assert len(detail["runs"]) == 3


def _create_legacy_only_db(path: Path) -> None:
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
                created_at TEXT,
                pdf_sha256 TEXT
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def _insert_legacy_run(
    conn: sqlite3.Connection,
    *,
    pdf_path: str,
    created_at: str,
    pdf_sha256: str = "same-sha",
    job_id: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO runs (job_id, pdf_path, assay_key, lot_id, dedupe_key, device_id, payload_json, created_at, pdf_sha256)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            job_id,
            pdf_path,
            "(1111)",
            "LOT-A",
            "K1",
            "dev1",
            "{}",
            created_at,
            pdf_sha256,
        ),
    )


def test_legacy_same_path_within_window_groups(tmp_path: Path):
    db = tmp_path / "legacy.sqlite3"
    _create_legacy_only_db(db)
    conn = sqlite3.connect(str(db))
    _insert_legacy_run(
        conn,
        pdf_path="/tmp/legacy.pdf",
        created_at="2026-01-01T10:00:00Z",
    )
    _insert_legacy_run(
        conn,
        pdf_path="/tmp/legacy.pdf",
        created_at="2026-01-01T10:00:03Z",
    )
    conn.commit()
    conn.close()
    summaries = list_report_summaries(_store_spec(db), limit=50)
    legacy_reports = [row for row in summaries["reports"] if not row.get("job_id")]
    assert len(legacy_reports) == 1
    assert legacy_reports[0]["run_count"] == 2


def test_legacy_same_path_outside_window_splits(tmp_path: Path):
    db = tmp_path / "legacy.sqlite3"
    _create_legacy_only_db(db)
    conn = sqlite3.connect(str(db))
    _insert_legacy_run(
        conn,
        pdf_path="/tmp/legacy.pdf",
        created_at="2026-01-01T10:00:00Z",
    )
    _insert_legacy_run(
        conn,
        pdf_path="/tmp/legacy.pdf",
        created_at="2026-01-01T10:00:10Z",
    )
    conn.commit()
    conn.close()
    summaries = list_report_summaries(_store_spec(db), limit=50)
    legacy_reports = [row for row in summaries["reports"] if not row.get("job_id")]
    assert len(legacy_reports) == 2


def test_legacy_same_sha_different_paths_do_not_merge(tmp_path: Path):
    db = tmp_path / "legacy.sqlite3"
    _create_legacy_only_db(db)
    conn = sqlite3.connect(str(db))
    _insert_legacy_run(
        conn,
        pdf_path="/tmp/a.pdf",
        created_at="2026-01-01T10:00:00Z",
        pdf_sha256="shared",
    )
    _insert_legacy_run(
        conn,
        pdf_path="/tmp/b.pdf",
        created_at="2026-01-01T10:00:01Z",
        pdf_sha256="shared",
    )
    conn.commit()
    conn.close()
    summaries = list_report_summaries(_store_spec(db), limit=50)
    legacy_reports = [row for row in summaries["reports"] if not row.get("job_id")]
    assert len(legacy_reports) == 2


def test_get_report_runs_returns_exact_legacy_cluster(tmp_path: Path):
    db = tmp_path / "legacy.sqlite3"
    _create_legacy_only_db(db)
    conn = sqlite3.connect(str(db))
    _insert_legacy_run(
        conn,
        pdf_path="/tmp/cluster.pdf",
        created_at="2026-01-01T10:00:00Z",
    )
    _insert_legacy_run(
        conn,
        pdf_path="/tmp/cluster.pdf",
        created_at="2026-01-01T10:00:02Z",
    )
    _insert_legacy_run(
        conn,
        pdf_path="/tmp/cluster.pdf",
        created_at="2026-01-01T10:00:20Z",
    )
    conn.commit()
    conn.close()
    summaries = list_report_summaries(_store_spec(db), limit=50)
    legacy_reports = [row for row in summaries["reports"] if not row.get("job_id")]
    assert len(legacy_reports) == 2
    first_id = legacy_reports[0]["report_id"]
    detail = get_report_runs(_store_spec(db), first_id)
    assert detail is not None
    assert len(detail["runs"]) == legacy_reports[0]["run_count"]


def test_schema_without_job_id_treats_rows_as_legacy(tmp_path: Path):
    db = tmp_path / "no-job-id.sqlite3"
    conn = sqlite3.connect(str(db))
    conn.execute(
        """
        CREATE TABLE runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    conn.execute(
        """
        INSERT INTO runs (pdf_path, assay_key, lot_id, dedupe_key, device_id, payload_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "/tmp/legacy.pdf",
            "(1111)",
            "LOT-A",
            "K1",
            "dev1",
            "{}",
            "2026-01-01T10:00:00Z",
        ),
    )
    conn.commit()
    conn.close()
    summaries = list_report_summaries(_store_spec(db), limit=10)
    assert summaries["total_returned"] == 1
    assert summaries["reports"][0]["run_count"] == 1


def test_legacy_uncertain_rows_without_id_column_stay_separate(tmp_path: Path):
    db = tmp_path / "no-id-uncertain.sqlite3"
    conn = sqlite3.connect(str(db))
    conn.execute(
        """
        CREATE TABLE runs (
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
    for created_at in ("", "invalid", None):
        conn.execute(
            """
            INSERT INTO runs (pdf_path, assay_key, lot_id, dedupe_key, device_id, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "/tmp/uncertain.pdf",
                "(1111)",
                "LOT-A",
                "K1",
                "dev1",
                "{}",
                created_at,
            ),
        )
    conn.commit()
    conn.close()
    spec = _store_spec(db)
    summaries = list_report_summaries(spec, limit=10)
    assert summaries["total_returned"] == 3
    report_ids = {row["report_id"] for row in summaries["reports"]}
    assert len(report_ids) == 3
    for row in summaries["reports"]:
        assert row["run_count"] == 1
        detail = get_report_runs(spec, row["report_id"])
        assert detail is not None
        assert len(detail["runs"]) == 1
        assert "id" not in detail["runs"][0] or detail["runs"][0]["id"] is None


def test_schema_missing_pdf_path_or_created_at_returns_empty_legacy_reports(tmp_path: Path):
    db = tmp_path / "missing-columns.sqlite3"
    conn = sqlite3.connect(str(db))
    conn.execute(
        """
        CREATE TABLE runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT,
            assay_key TEXT,
            lot_id TEXT,
            dedupe_key TEXT,
            device_id TEXT,
            payload_json TEXT
        )
        """
    )
    conn.execute(
        """
        INSERT INTO runs (job_id, assay_key, lot_id, dedupe_key, device_id, payload_json)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("job-only", "(1111)", "LOT-A", "K1", "dev1", "{}"),
    )
    conn.commit()
    conn.close()
    status = get_result_store_status(_store_spec(db))
    assert any("pdf_path" in warning for warning in status["schema_warnings"])
    summaries = list_report_summaries(_store_spec(db), limit=10)
    assert summaries["total_returned"] == 1
    assert summaries["reports"][0]["job_id"] == "job-only"
    detail = get_report_runs(_store_spec(db), "job-only")
    assert detail is not None
    assert detail["run_count"] == 1
