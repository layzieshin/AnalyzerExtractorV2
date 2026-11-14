from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.qualitycontrol.api import MutationContext, QCConfigurationError, QCStoreError, get_inventory, legacy_device_source, migrate_legacy_devices

from src.runtime.api import (
    get_default_device_id,
    get_device_config_status,
    list_devices,
    resolve_device_id,
)


def _spec(root: Path) -> dict[str, str]:
    return {"driver": "sqlite", "path": str(root / "selected.sqlite3")}


def _migrate(root: Path) -> None:
    source = legacy_device_source(root)
    migrate_legacy_devices(_spec(root), root, expected_source_sha256=source["sha256"],
                           context=MutationContext("RR", "migration", "Altgeräte übernehmen"))


def test_devices_sentinel_is_visible_readonly_and_requires_explicit_store(tmp_path: Path) -> None:
    with pytest.raises(QCStoreError, match="ausdrücklich"):
        list_devices(tmp_path)
    with pytest.raises(QCStoreError):
        resolve_device_id(tmp_path, "historical")
    devices = list_devices(tmp_path, store_spec=_spec(tmp_path))
    assert devices[0]["device_id"] == "DEFAULT_DEVICE" and devices[0]["incomplete"]
    assert get_default_device_id(tmp_path, store_spec=_spec(tmp_path)) == "DEFAULT_DEVICE"
    assert resolve_device_id(tmp_path, "historical", store_spec=_spec(tmp_path)) == "historical"
    status = get_device_config_status(tmp_path, store_spec=_spec(tmp_path))
    assert status["status"] == "migration_required"
    assert status["using_fallback"] is True
    assert not list(tmp_path.iterdir())


def test_devices_load_valid_config_and_resolve_selection(tmp_path: Path) -> None:
    config = tmp_path / "config"
    config.mkdir()
    (config / "devices.json").write_text(
        json.dumps(
            {
                "default_device_id": "analyzer_i_1",
                "devices": [
                    {"device_id": "analyzer_i_1", "display_name": "Analyzer I", "active": True},
                    {"device_id": "inactive", "display_name": "Inactive", "active": False},
                ],
            }
        ),
        encoding="utf-8",
    )

    _migrate(tmp_path)
    devices = list_devices(tmp_path, store_spec=_spec(tmp_path))
    assert [row["device_id"] for row in devices] == ["analyzer_i_1"]
    assert devices[0]["incomplete"] is False
    assert devices[0]["display_name"] == "Analyzer I"
    assert all(not devices[0][key] for key in ("serial_number", "lnr", "eva"))
    assert get_default_device_id(tmp_path, store_spec=_spec(tmp_path)) == "analyzer_i_1"
    assert resolve_device_id(tmp_path, "analyzer_i_1", store_spec=_spec(tmp_path)) == "analyzer_i_1"
    assert resolve_device_id(tmp_path, "manual_device", store_spec=_spec(tmp_path)) == "manual_device"
    assert get_device_config_status(tmp_path, store_spec=_spec(tmp_path))["status"] == "ok"


def test_devices_invalid_config_requires_explicit_clarification(tmp_path: Path) -> None:
    config = tmp_path / "config"
    config.mkdir()
    (config / "devices.json").write_text("{bad json", encoding="utf-8")

    with pytest.raises(QCConfigurationError, match="unlesbar"):
        _migrate(tmp_path)
    assert not Path(_spec(tmp_path)["path"]).exists()
    assert list_devices(tmp_path, store_spec=_spec(tmp_path))[0]["device_id"] == "DEFAULT_DEVICE"


@pytest.mark.parametrize("active_current, expected_auto", [(True, "dev_a"), (False, "DEFAULT_DEVICE")])
def test_devices_auto_selection_preserves_legacy_active_fallback_and_stored_default(tmp_path: Path, active_current, expected_auto) -> None:
    config = tmp_path / "config"
    config.mkdir()
    (config / "devices.json").write_text(
        json.dumps(
            {
                "default_device_id": "inactive",
                "devices": [
                    {"device_id": "dev_a", "display_name": "Device A", "active": active_current},
                    {"device_id": "inactive", "display_name": "Inactive", "active": False},
                ],
            }
        ),
        encoding="utf-8",
    )

    _migrate(tmp_path)
    source = config / "devices.json"
    store_path = Path(_spec(tmp_path)["path"])
    before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in (source, store_path)}
    # Pre-P4 automatic resolution selected the first active configured device,
    # or the DEFAULT_DEVICE sentinel when every configured device was inactive.
    assert get_default_device_id(tmp_path, store_spec=_spec(tmp_path)) == expected_auto
    assert resolve_device_id(tmp_path, store_spec=_spec(tmp_path)) == expected_auto
    assert resolve_device_id(tmp_path, "inactive", store_spec=_spec(tmp_path)) == "inactive"
    assert get_inventory(_spec(tmp_path))["snapshot"]["default_device_id"] == "inactive"
    assert [row["device_id"] for row in list_devices(tmp_path, store_spec=_spec(tmp_path))] == (["dev_a"] if active_current else [])
    for path, snapshot in before.items():
        assert (path.read_bytes(), path.stat().st_mtime_ns) == snapshot
