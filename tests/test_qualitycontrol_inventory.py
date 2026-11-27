"""QC inventory acceptance uses synthetic temporary databases only."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from src.qualitycontrol.api import (
    MutationContext, QCConfigurationError, QCConflictError, QCStoreError,
    get_inventory, get_status, legacy_device_source, migrate_legacy_devices, save_inventory,
)
from src.runtime.api import list_devices, resolve_device_id


def _context(request: str = "one") -> MutationContext:
    return MutationContext(" RR ", request, "Geräteprüfung")


def _spec(path: Path) -> dict[str, str]:
    return {"driver": "sqlite", "path": str(path)}


def _legacy(root: Path, devices=None) -> dict:
    path = root / "config" / "devices.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"default_device_id": "device-a", "devices": devices or [
        {"device_id": "device-a", "display_name": "Gerät A", "serial_number": "SN1", "active": True},
    ]}), encoding="utf-8")
    return legacy_device_source(root)


def _migrate(root: Path, spec: dict, request="one") -> dict:
    source = legacy_device_source(root)
    return migrate_legacy_devices(spec, root, expected_source_sha256=source["sha256"], context=_context(request))


def _seed_runs(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE runs (id INTEGER PRIMARY KEY, assay_key TEXT, lot_id TEXT, device_id TEXT, payload_json TEXT)")
        conn.execute("INSERT INTO runs VALUES (1, 'A', 'L', 'historic-only', '{}')")


def test_no_write_browsing_missing_and_existing_database(tmp_path: Path) -> None:
    spec = _spec(tmp_path / "nested" / "selected.sqlite3")
    assert get_status(spec)["status"] == "migration_required"
    assert get_inventory(spec, include_history=True)["history"] == []
    assert not list(tmp_path.iterdir())
    path = tmp_path / "existing.sqlite3"
    _seed_runs(path)
    before = path.read_bytes(), path.stat().st_mtime_ns
    assert get_inventory(_spec(path))["version_id"] == 0
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before
    assert not list(tmp_path.glob("*-journal"))


def test_migration_keeps_source_bytes_ids_default_and_history(tmp_path: Path) -> None:
    source = _legacy(tmp_path)
    path = tmp_path / "selected.sqlite3"
    _seed_runs(path)
    before_source = Path(source["path"]).read_bytes(), Path(source["path"]).stat().st_mtime_ns
    record = _migrate(tmp_path, _spec(path))
    devices = {item["device_id"]: item for item in record["snapshot"]["devices"]}
    assert record["snapshot"]["default_device_id"] == "device-a"
    assert not devices["device-a"]["incomplete"]
    assert devices["historic-only"]["incomplete"] and devices["historic-only"]["display_name"] == ""
    assert all(not devices["historic-only"][key] for key in ("serial_number", "lnr", "eva"))
    assert (Path(source["path"]).read_bytes(), Path(source["path"]).stat().st_mtime_ns) == before_source
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT device_id FROM runs").fetchall() == [("historic-only",)]
        assert len(conn.execute("SELECT name FROM sqlite_master WHERE name LIKE 'qc_%' AND type='table'").fetchall()) == 5
        assert conn.execute("SELECT version, source_sha256 FROM qc_schema_migrations").fetchone() == (1, source["sha256"])


def test_migration_idempotency_and_single_authority(tmp_path: Path) -> None:
    source = _legacy(tmp_path)
    spec = _spec(tmp_path / "selected.sqlite3")
    first = _migrate(tmp_path, spec)
    assert _migrate(tmp_path, spec) == first
    assert _migrate(tmp_path, spec, "fresh-request") == first
    Path(source["path"]).write_text('{"devices":[]}', encoding="utf-8")
    assert list_devices(tmp_path, store_spec=spec)[0]["display_name"] == "Gerät A"
    assert resolve_device_id(tmp_path, store_spec=spec) == "device-a"
    assert len(get_inventory(spec, include_history=True)["history"]) == 1


def test_wrong_hash_and_transaction_failure_do_not_publish_schema(tmp_path: Path, monkeypatch) -> None:
    import src.qualitycontrol.store as store

    source = _legacy(tmp_path)
    path = tmp_path / "selected.sqlite3"
    _seed_runs(path)
    spec = _spec(path)
    with pytest.raises(QCConflictError):
        migrate_legacy_devices(spec, tmp_path, expected_source_sha256="0" * 64, context=_context())
    before = path.read_bytes()

    def fail(*_args, **_kwargs):
        raise RuntimeError("synthetic interruption")

    monkeypatch.setattr(store, "_append_inventory", fail)
    with pytest.raises(RuntimeError, match="interruption"):
        migrate_legacy_devices(spec, tmp_path, expected_source_sha256=source["sha256"], context=_context())
    assert path.read_bytes() == before
    with sqlite3.connect(path) as conn:
        assert not conn.execute("SELECT name FROM sqlite_master WHERE name LIKE 'qc_%'").fetchall()


def test_store_override_is_explicit_and_never_uses_default_db(tmp_path: Path) -> None:
    _legacy(tmp_path)
    spec = _spec(tmp_path / "chosen.sqlite3")
    _migrate(tmp_path, spec)
    assert get_inventory(_spec(tmp_path / "other.sqlite3"))["version_id"] == 0
    assert not (tmp_path / "output").exists()
    with pytest.raises(QCStoreError):
        get_inventory({"driver": "sqlite"})


def test_inventory_append_preserves_ids_and_stale_request_is_rejected(tmp_path: Path) -> None:
    _legacy(tmp_path)
    spec = _spec(tmp_path / "selected.sqlite3")
    first = _migrate(tmp_path, spec)
    payload = first["snapshot"]
    payload["devices"][0]["display_name"] = "Umbenannt"
    second = save_inventory(spec, payload, expected_version_id=first["version_id"], context=_context("edit"))
    assert second["predecessor_id"] == first["version_id"]
    history = get_inventory(spec, include_history=True)["history"]
    assert history[0]["snapshot"]["devices"][0]["display_name"] == "Gerät A"
    assert save_inventory(spec, payload, expected_version_id=first["version_id"], context=_context("edit")) == second
    with pytest.raises(QCConflictError):
        save_inventory(spec, payload, expected_version_id=first["version_id"], context=_context("stale"))
    payload["devices"].append({"device_id": "new", "display_name": "Neu", "lnr": "LNR1"})
    payload["default_device_id"] = "new"
    with pytest.raises(QCConfigurationError, match="Historische"):
        save_inventory(spec, {**payload, "devices": [payload["devices"][-1]]}, expected_version_id=second["version_id"], context=_context("drop"))


def test_partial_or_unknown_schema_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "partial.sqlite3"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE qc_inventory_versions (version_id INTEGER)")
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(QCStoreError, match="unvollständig"):
        get_status(_spec(path))
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_new_incomplete_device_cannot_claim_legacy_and_reason_is_optional(tmp_path: Path) -> None:
    spec = _spec(tmp_path / "new.sqlite3")
    value = {"default_device_id": "new", "devices": [{"device_id": "new", "display_name": "Neu", "legacy": True}]}
    with pytest.raises(QCConfigurationError, match="Neue Geräte"):
        save_inventory(spec, value, expected_version_id=0, context=MutationContext("RR", "new"))
    value["devices"][0]["lnr"] = "L1"
    assert save_inventory(spec, value, expected_version_id=0, context=MutationContext("RR", "complete"))["reason"]


def test_disappearing_existing_database_is_never_recreated(tmp_path: Path, monkeypatch) -> None:
    import gc
    import src.qualitycontrol.store as store

    _legacy(tmp_path)
    spec = _spec(tmp_path / "chosen.sqlite3")
    _migrate(tmp_path, spec)
    # ResultStore's compatibility readers release sqlite objects on collection.
    # Finish those unrelated reads before exercising the open-time file race.
    gc.collect()
    original = store._connect_uri

    def disappearing(path, mode):
        path.unlink()
        return original(path, mode)

    monkeypatch.setattr(store, "_connect_uri", disappearing)
    with pytest.raises(QCStoreError):
        with store.write_connection(spec):
            pytest.fail("must not create an empty database")
    assert not Path(spec["path"]).exists()


def test_explicit_historical_device_resolution_does_not_read_corrupt_store(tmp_path: Path) -> None:
    path = tmp_path / "corrupt.sqlite3"
    path.write_bytes(b"synthetic invalid sqlite")
    before = path.read_bytes(), path.stat().st_mtime_ns
    assert resolve_device_id(tmp_path, "historical-id", store_spec=_spec(path)) == "historical-id"
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


def test_submit_keeps_done_skip_and_returns_controlled_failure_for_bad_inventory(tmp_path: Path) -> None:
    from src.jobcontroller.api import submit

    pdf = tmp_path / "synthetic.pdf"
    pdf.write_bytes(b"synthetic pdf source")
    database = tmp_path / "corrupt.sqlite3"
    database.write_bytes(b"synthetic invalid sqlite")
    failed = submit(str(pdf), str(tmp_path), sqlite_path=str(database))
    assert failed.status == "FAILED" and "device_configuration_unreadable" in failed.details["error"]
    assert not (tmp_path / "jobs").exists()
    job_id = hashlib.sha256(pdf.read_bytes()).hexdigest()[:16]
    (tmp_path / "jobs").mkdir()
    state = tmp_path / "jobs" / f"{job_id}.json"
    state.write_text(json.dumps({"job_id": job_id, "status": "DONE", "steps": []}), encoding="utf-8")
    before = state.read_bytes(), state.stat().st_mtime_ns
    skipped = submit(str(pdf), str(tmp_path), sqlite_path=str(database))
    assert skipped.status == "SKIPPED" and skipped.details["reason"] == "already_done"
    assert (state.read_bytes(), state.stat().st_mtime_ns) == before
