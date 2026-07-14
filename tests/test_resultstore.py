import json
import sqlite3
from pathlib import Path

import pytest

from src.resultstore.api import (
    get_result_run,
    get_result_store_status,
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
