from __future__ import annotations

import json
from pathlib import Path

from src.runtime.api import (
    get_default_device_id,
    get_device_config_status,
    list_devices,
    resolve_device_id,
)


def test_devices_fallback_when_config_missing(tmp_path: Path) -> None:
    assert list_devices(tmp_path) == [
        {"device_id": "DEFAULT_DEVICE", "display_name": "DEFAULT_DEVICE", "active": True}
    ]
    assert get_default_device_id(tmp_path) == "DEFAULT_DEVICE"
    status = get_device_config_status(tmp_path)
    assert status["status"] == "missing"
    assert status["using_fallback"] is True


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

    assert list_devices(tmp_path) == [
        {"device_id": "analyzer_i_1", "display_name": "Analyzer I", "active": True}
    ]
    assert get_default_device_id(tmp_path) == "analyzer_i_1"
    assert resolve_device_id(tmp_path, "analyzer_i_1") == "analyzer_i_1"
    assert resolve_device_id(tmp_path, "manual_device") == "manual_device"
    assert get_device_config_status(tmp_path)["status"] == "ok"


def test_devices_invalid_config_reports_fallback(tmp_path: Path) -> None:
    config = tmp_path / "config"
    config.mkdir()
    (config / "devices.json").write_text("{bad json", encoding="utf-8")

    assert list_devices(tmp_path)[0]["device_id"] == "DEFAULT_DEVICE"
    status = get_device_config_status(tmp_path)
    assert status["status"] == "invalid"
    assert status["using_fallback"] is True


def test_devices_invalid_default_uses_first_active_configured_device(tmp_path: Path) -> None:
    config = tmp_path / "config"
    config.mkdir()
    (config / "devices.json").write_text(
        json.dumps(
            {
                "default_device_id": "inactive",
                "devices": [
                    {"device_id": "dev_a", "display_name": "Device A", "active": True},
                    {"device_id": "inactive", "display_name": "Inactive", "active": False},
                ],
            }
        ),
        encoding="utf-8",
    )

    assert get_default_device_id(tmp_path) == "dev_a"
    assert resolve_device_id(tmp_path) == "dev_a"
