from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.application.api import SettingsLoadError, SettingsValidationError, create_desktop_services


def test_settings_env_fallback_and_both_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ARE_OUTPUT_MODE", raising=False)
    services = create_desktop_services(tmp_path)
    settings = services.settings.load()

    assert settings.output_mode == "both"
    assert settings.sqlite_path.endswith("results.sqlite3")
    assert settings.watch_dir.endswith("input\\watch") or settings.watch_dir.endswith("input/watch")


def test_settings_persist_only_allowed_fields(tmp_path: Path) -> None:
    services = create_desktop_services(tmp_path)
    loaded = services.settings.load()
    custom = loaded.__class__(
        output_mode="sqlite",
        sqlite_path=str(tmp_path / "custom.sqlite3"),
        watch_enabled=True,
        watch_input_path=str(tmp_path / "watch"),
        watch_backup_path=str(tmp_path / "backup"),
        device_id="analyzer_i_1",
    )
    services.settings.save(custom)

    path = services.settings.settings_path()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["output_mode"] == "sqlite"
    assert payload["device_id"] == "analyzer_i_1"
    assert payload["watch_enabled"] is True
    assert payload["watch_input_path"] == str(tmp_path / "watch")
    assert payload["watch_backup_path"] == str(tmp_path / "backup")
    assert "watch_dir" not in payload

    reloaded = create_desktop_services(tmp_path).settings.load()
    assert reloaded.output_mode == "sqlite"
    assert reloaded.sqlite_path == str(tmp_path / "custom.sqlite3")
    assert reloaded.watch_enabled is True


def test_invalid_json_is_not_silently_overwritten(tmp_path: Path) -> None:
    services = create_desktop_services(tmp_path)
    path = services.settings.settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(SettingsLoadError):
        services.settings.load()


def test_load_rejects_invalid_persisted_output_mode(tmp_path: Path) -> None:
    services = create_desktop_services(tmp_path)
    path = services.settings.settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "output_mode": "invalid",
                "sqlite_path": str(tmp_path / "runs.sqlite3"),
                "watch_input_path": str(tmp_path / "watch"),
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(SettingsValidationError, match="invalid_output_mode"):
        services.settings.load()


def test_load_rejects_empty_sqlite_path(tmp_path: Path) -> None:
    services = create_desktop_services(tmp_path)
    path = services.settings.settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "output_mode": "both",
                "sqlite_path": "   ",
                "watch_input_path": str(tmp_path / "watch"),
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(SettingsValidationError, match="sqlite_path_required"):
        services.settings.load()


def test_load_rejects_wrong_json_value_types(tmp_path: Path) -> None:
    services = create_desktop_services(tmp_path)
    path = services.settings.settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "output_mode": 123,
                "sqlite_path": str(tmp_path / "runs.sqlite3"),
                "watch_input_path": str(tmp_path / "watch"),
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(SettingsValidationError, match="invalid_output_mode_type"):
        services.settings.load()


def test_create_desktop_services_fails_on_invalid_persisted_settings(tmp_path: Path) -> None:
    path = tmp_path / "storage" / "desktop_settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "output_mode": "both",
                "sqlite_path": "",
                "watch_input_path": str(tmp_path / "watch"),
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(SettingsValidationError):
        create_desktop_services(tmp_path)


def test_validate_rejects_invalid_output_mode(tmp_path: Path) -> None:
    services = create_desktop_services(tmp_path)
    loaded = services.settings.load()
    invalid = loaded.__class__(
        output_mode="invalid",
        sqlite_path=loaded.sqlite_path,
        watch_input_path=loaded.watch_input_path,
        device_id=loaded.device_id,
    )
    with pytest.raises(SettingsValidationError):
        services.settings.validate(invalid)


def test_desktop_settings_legacy_positional_and_watch_dir_keyword(tmp_path: Path) -> None:
    from src.application.models import DesktopSettings

    legacy = DesktopSettings("both", str(tmp_path / "db.sqlite3"), str(tmp_path / "watch"), "device-1")
    assert legacy.watch_dir == str(tmp_path / "watch")
    assert legacy.watch_input_path == str(tmp_path / "watch")
    assert legacy.device_id == "device-1"
    assert legacy.watch_enabled is False

    keyword = DesktopSettings(
        output_mode="sqlite",
        sqlite_path=str(tmp_path / "db.sqlite3"),
        watch_dir=str(tmp_path / "watch-kw"),
    )
    assert keyword.watch_dir == str(tmp_path / "watch-kw")

    with pytest.raises(ValueError, match="conflicting_watch_dir"):
        DesktopSettings(
            "both",
            str(tmp_path / "db.sqlite3"),
            "path-a",
            watch_input_path="path-b",
        )


def test_validate_watch_paths_rejects_settings_case_variant_child(tmp_path: Path) -> None:
    watch = tmp_path / "Watch"
    backup = tmp_path / "watch" / "backup"
    watch.mkdir()
    backup.mkdir(parents=True)
    services = create_desktop_services(tmp_path)
    loaded = services.settings.load()
    invalid = loaded.__class__(
        output_mode=loaded.output_mode,
        sqlite_path=loaded.sqlite_path,
        watch_enabled=True,
        watch_input_path=str(watch),
        watch_backup_path=str(backup),
        device_id=loaded.device_id,
    )
    with pytest.raises(SettingsValidationError, match="watch_backup_under_input"):
        services.settings.validate(invalid)


def test_validate_watch_paths_rejects_settings_case_variant_parent(tmp_path: Path) -> None:
    outer = tmp_path / "Outer"
    inner = outer / "inner"
    inner.mkdir(parents=True)
    services = create_desktop_services(tmp_path)
    loaded = services.settings.load()
    invalid = loaded.__class__(
        output_mode=loaded.output_mode,
        sqlite_path=loaded.sqlite_path,
        watch_enabled=True,
        watch_input_path=str(inner),
        watch_backup_path=str(outer),
        device_id=loaded.device_id,
    )
    with pytest.raises(SettingsValidationError, match="watch_input_under_backup"):
        services.settings.validate(invalid)


def test_atomic_save_replaces_file(tmp_path: Path) -> None:
    services = create_desktop_services(tmp_path)
    loaded = services.settings.load()
    path = services.settings.settings_path()
    services.settings.save(loaded)
    before = path.read_text(encoding="utf-8")

    updated = loaded.__class__(
        output_mode="excel",
        sqlite_path=loaded.sqlite_path,
        watch_input_path=loaded.watch_input_path,
        device_id=loaded.device_id,
    )
    services.settings.save(updated)
    after = path.read_text(encoding="utf-8")

    assert before != after
    assert json.loads(after)["output_mode"] == "excel"


def test_watch_enabled_false_persists_after_true(tmp_path: Path) -> None:
    services = create_desktop_services(tmp_path)
    loaded = services.settings.load()
    enabled = loaded.__class__(
        output_mode=loaded.output_mode,
        sqlite_path=loaded.sqlite_path,
        watch_enabled=True,
        watch_input_path=str(tmp_path / "watch"),
        watch_backup_path=str(tmp_path / "backup"),
        device_id=loaded.device_id,
    )
    services.settings.save(enabled)
    path = services.settings.settings_path()
    assert json.loads(path.read_text(encoding="utf-8"))["watch_enabled"] is True

    disabled = loaded.__class__(
        output_mode=loaded.output_mode,
        sqlite_path=loaded.sqlite_path,
        watch_enabled=False,
        watch_input_path=str(tmp_path / "watch"),
        watch_backup_path=str(tmp_path / "backup"),
        device_id=loaded.device_id,
    )
    services.settings.save(disabled)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["watch_enabled"] is False
    assert create_desktop_services(tmp_path).settings.load().watch_enabled is False


def test_watch_recursive_defaults_false_and_persists(tmp_path: Path) -> None:
    services = create_desktop_services(tmp_path)
    loaded = services.settings.load()
    assert loaded.watch_recursive is False

    updated = loaded.__class__(
        output_mode=loaded.output_mode,
        sqlite_path=loaded.sqlite_path,
        watch_enabled=True,
        watch_input_path=str(tmp_path / "watch"),
        watch_backup_path=str(tmp_path / "backup"),
        watch_recursive=True,
        device_id=loaded.device_id,
    )
    services.settings.save(updated)
    payload = json.loads(services.settings.settings_path().read_text(encoding="utf-8"))
    assert payload["watch_recursive"] is True
    assert create_desktop_services(tmp_path).settings.load().watch_recursive is True


def test_open_output_folder_uses_injected_opener(tmp_path: Path) -> None:
    services = create_desktop_services(tmp_path)
    opened: list[str] = []

    def fake_opener(path: str) -> None:
        opened.append(path)

    target = services.settings.open_output_folder(path_opener=fake_opener)
    assert opened == [target]
    assert target.endswith("output\\final") or target.endswith("output/final")


def test_get_watch_timing_reads_runtime_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARE_SCAN_INTERVAL_S", "4.5")
    monkeypatch.setenv("ARE_WATCH_STABLE_WINDOW_S", "1.75")
    services = create_desktop_services(tmp_path)
    timing = services.settings.get_watch_timing()
    assert timing.scan_interval_s == 4.5
    assert timing.stable_window_s == 1.75


@pytest.mark.parametrize(
    ("env_value", "expected"),
    [
        ("2.0", 2.0),
        ("0", 3.0),
        ("-1", 0.5),
        ("nan", 3.0),
        ("inf", 3.0),
    ],
)
def test_get_watch_timing_normalizes_scan_interval(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    env_value: str,
    expected: float,
) -> None:
    monkeypatch.setenv("ARE_SCAN_INTERVAL_S", env_value)
    timing = create_desktop_services(tmp_path).settings.get_watch_timing()
    assert timing.scan_interval_s == expected


@pytest.mark.parametrize(
    ("env_value", "expected"),
    [
        ("1.75", 1.75),
        ("0", 0.0),
        ("-2", 0.0),
        ("nan", 1.0),
        ("inf", 1.0),
    ],
)
def test_get_watch_timing_normalizes_stable_window(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    env_value: str,
    expected: float,
) -> None:
    monkeypatch.setenv("ARE_WATCH_STABLE_WINDOW_S", env_value)
    timing = create_desktop_services(tmp_path).settings.get_watch_timing()
    assert timing.stable_window_s == expected


def test_operator_initials_are_trimmed_and_persisted(tmp_path: Path) -> None:
    services = create_desktop_services(tmp_path)
    loaded = services.settings.load()
    assert loaded.operator_initials == ""

    saved = services.settings.save(
        loaded.__class__(
            output_mode=loaded.output_mode,
            sqlite_path=loaded.sqlite_path,
            watch_input_path=loaded.watch_input_path,
            device_id=loaded.device_id,
            operator_initials="  RR  ",
        )
    )
    assert saved.operator_initials == "RR"
    payload = json.loads(services.settings.settings_path().read_text(encoding="utf-8"))
    assert payload["operator_initials"] == "RR"

    reloaded = create_desktop_services(tmp_path).settings.load()
    assert reloaded.operator_initials == "RR"


def test_operator_initials_reject_non_string(tmp_path: Path) -> None:
    services = create_desktop_services(tmp_path)
    path = services.settings.settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "output_mode": "both",
                "sqlite_path": str(tmp_path / "runs.sqlite3"),
                "operator_initials": 12,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(SettingsValidationError, match="invalid_operator_initials_type"):
        services.settings.load()


def test_device_inventory_and_reload_use_runtime_api(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "devices.json").write_text(
        json.dumps(
            {
                "default_device_id": "analyzer_i_1",
                "devices": [
                    {"device_id": "analyzer_i_1", "display_name": "Analyzer 1", "active": True},
                    {"device_id": "analyzer_i_2", "display_name": "Analyzer 2", "active": False},
                ],
            }
        ),
        encoding="utf-8",
    )
    services = create_desktop_services(tmp_path)
    inventory = services.settings.get_device_inventory()
    assert inventory.status == "ok"
    assert inventory.default_device_id == "analyzer_i_1"
    assert len(inventory.devices) == 1
    assert inventory.devices[0].device_id == "analyzer_i_1"
    reloaded = services.settings.reload_device_inventory()
    assert reloaded.devices == inventory.devices
