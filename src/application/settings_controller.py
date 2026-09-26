from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from src.runtime.api import (
    VALID_OUTPUT_MODES,
    get_default_device_id,
    get_device_config_status,
    list_devices,
    load_runtime_config,
)

from .errors import SettingsLoadError, SettingsSaveError, SettingsValidationError
from .models import DesktopSettings, DeviceInventoryItem, DeviceInventoryStatus, WatchTimingSettings
from .presentation import normalize_scan_interval_s, normalize_stable_window_s

_SETTINGS_FILE_NAME = "desktop_settings.json"
_ALLOWED_KEYS = frozenset(
    {
        "output_mode",
        "sqlite_path",
        "watch_dir",
        "watch_input_path",
        "watch_backup_path",
        "watch_enabled",
        "watch_recursive",
        "device_id",
        "operator_initials",
    }
)


class SettingsController:
    def __init__(self, project_root: str | Path) -> None:
        self._project_root = Path(project_root).resolve()

    @property
    def project_root(self) -> Path:
        return self._project_root

    def settings_path(self) -> Path:
        return self._project_root / "storage" / _SETTINGS_FILE_NAME

    def load(self) -> DesktopSettings:
        runtime = load_runtime_config(self._project_root)
        settings = DesktopSettings(
            output_mode=runtime.output_mode,
            sqlite_path=str(runtime.sqlite_path or ""),
            watch_enabled=False,
            watch_input_path=str(runtime.watch_dir or ""),
            watch_backup_path="",
            watch_recursive=False,
            device_id=runtime.device_id,
            operator_initials="",
        )
        path = self.settings_path()
        if not path.is_file():
            return settings

        try:
            raw_text = path.read_text(encoding="utf-8")
            payload = json.loads(raw_text)
        except (OSError, json.JSONDecodeError) as exc:
            raise SettingsLoadError(f"invalid_desktop_settings_json: {exc}") from exc

        if not isinstance(payload, dict):
            raise SettingsLoadError("invalid_desktop_settings_json: root must be object")

        overrides = _read_settings_overrides(payload, base=settings)
        try:
            merged = DesktopSettings(
                output_mode=overrides["output_mode"],
                sqlite_path=overrides["sqlite_path"],
                watch_enabled=overrides["watch_enabled"],
                watch_input_path=overrides["watch_input_path"],
                watch_backup_path=overrides["watch_backup_path"],
                watch_recursive=overrides["watch_recursive"],
                device_id=overrides["device_id"],
                operator_initials=overrides["operator_initials"],
            )
        except ValueError as exc:
            raise SettingsValidationError(str(exc)) from exc
        self.validate(merged, require_watch_paths=merged.watch_enabled)
        return merged

    def validate(self, settings: DesktopSettings, *, require_watch_paths: bool | None = None) -> None:
        if settings.output_mode not in VALID_OUTPUT_MODES:
            raise SettingsValidationError(f"invalid_output_mode: {settings.output_mode}")
        if not str(settings.sqlite_path or "").strip():
            raise SettingsValidationError("sqlite_path_required")
        require_paths = settings.watch_enabled if require_watch_paths is None else require_watch_paths
        if require_paths:
            _validate_watch_paths(settings.watch_input_path, settings.watch_backup_path)

    def canonical_output_dir(self) -> Path:
        return self._project_root / "output" / "final"

    def get_watch_timing(self) -> WatchTimingSettings:
        runtime = load_runtime_config(self._project_root)
        return WatchTimingSettings(
            scan_interval_s=normalize_scan_interval_s(float(runtime.scan_interval_s or 3.0)),
            stable_window_s=normalize_stable_window_s(float(runtime.watch_stable_window_s)),
        )

    def get_device_inventory(self) -> DeviceInventoryStatus:
        status = get_device_config_status(self._project_root)
        devices = tuple(
            DeviceInventoryItem(
                device_id=str(row.get("device_id") or ""),
                display_name=str(row.get("display_name") or row.get("device_id") or ""),
                active=bool(row.get("active", True)),
            )
            for row in list_devices(self._project_root)
        )
        return DeviceInventoryStatus(
            status=str(status.get("status") or ""),
            path=str(status.get("path") or ""),
            message=str(status.get("message") or ""),
            using_fallback=bool(status.get("using_fallback")),
            devices=devices,
            default_device_id=get_default_device_id(self._project_root),
        )

    def reload_device_inventory(self) -> DeviceInventoryStatus:
        return self.get_device_inventory()

    def open_output_folder(self, *, path_opener=None) -> str:
        from .desktop_actions import open_path

        target = self.canonical_output_dir()
        target.mkdir(parents=True, exist_ok=True)
        open_path(str(target), opener=path_opener)
        return str(target)

    def save(self, settings: DesktopSettings) -> DesktopSettings:
        self.validate(settings)
        path = self.settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {
            "output_mode": settings.output_mode,
            "sqlite_path": settings.sqlite_path,
            "watch_enabled": settings.watch_enabled,
            "watch_input_path": settings.watch_input_path,
            "watch_backup_path": settings.watch_backup_path,
            "watch_recursive": settings.watch_recursive,
            "device_id": settings.device_id,
            "operator_initials": settings.operator_initials,
        }
        temp_path = path.with_suffix(path.suffix + ".tmp")
        try:
            temp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            os.replace(temp_path, path)
        except OSError as exc:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass
            raise SettingsSaveError(f"desktop_settings_save_failed: {exc}") from exc
        return settings


def _normalize_device_id(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise SettingsValidationError("invalid_device_id_type")
    text = value.strip()
    return text or None


def _normalize_watch_path_key(path: str | Path) -> str:
    normalized = os.path.normpath(str(path or ""))
    return os.path.normcase(str(Path(normalized).resolve(strict=False)))


def _validate_watch_paths(watch_input_path: str, watch_backup_path: str) -> None:
    if not str(watch_input_path or "").strip():
        raise SettingsValidationError("watch_input_path_required")
    if not str(watch_backup_path or "").strip():
        raise SettingsValidationError("watch_backup_path_required")
    input_path = Path(watch_input_path).resolve(strict=False)
    backup_path = Path(watch_backup_path).resolve(strict=False)
    if _normalize_watch_path_key(input_path) == _normalize_watch_path_key(backup_path):
        raise SettingsValidationError("watch_input_backup_same_path")
    if _path_is_contained(backup_path, input_path):
        raise SettingsValidationError("watch_backup_under_input")
    if _path_is_contained(input_path, backup_path):
        raise SettingsValidationError("watch_input_under_backup")


def _path_is_contained(inner: Path, outer: Path) -> bool:
    inner_key = _normalize_watch_path_key(inner)
    outer_key = _normalize_watch_path_key(outer)
    if inner_key == outer_key:
        return False
    prefix = outer_key + os.sep
    return inner_key.startswith(prefix)


def _read_settings_overrides(payload: dict[str, Any], *, base: DesktopSettings) -> dict[str, Any]:
    overrides: dict[str, Any] = {
        "output_mode": base.output_mode,
        "sqlite_path": base.sqlite_path,
        "watch_enabled": base.watch_enabled,
        "watch_input_path": base.watch_input_path,
        "watch_backup_path": base.watch_backup_path,
        "watch_recursive": base.watch_recursive,
        "device_id": base.device_id,
        "operator_initials": base.operator_initials,
    }
    watch_dir_value: str | None = None
    watch_input_value: str | None = None
    for key in _ALLOWED_KEYS:
        if key not in payload:
            continue
        value = payload[key]
        if key == "output_mode":
            if not isinstance(value, str):
                raise SettingsValidationError("invalid_output_mode_type")
            overrides["output_mode"] = value
        elif key == "sqlite_path":
            if not isinstance(value, str):
                raise SettingsValidationError("invalid_sqlite_path_type")
            overrides["sqlite_path"] = value
        elif key == "watch_dir":
            if not isinstance(value, str):
                raise SettingsValidationError("invalid_watch_input_path_type")
            watch_dir_value = value
        elif key == "watch_input_path":
            if not isinstance(value, str):
                raise SettingsValidationError("invalid_watch_input_path_type")
            watch_input_value = value
        elif key == "watch_backup_path":
            if not isinstance(value, str):
                raise SettingsValidationError("invalid_watch_backup_path_type")
            overrides["watch_backup_path"] = value
        elif key == "watch_enabled":
            if not isinstance(value, bool):
                raise SettingsValidationError("invalid_watch_enabled_type")
            overrides["watch_enabled"] = value
        elif key == "watch_recursive":
            if not isinstance(value, bool):
                raise SettingsValidationError("invalid_watch_recursive_type")
            overrides["watch_recursive"] = value
        elif key == "device_id":
            overrides["device_id"] = _normalize_device_id(value)
        elif key == "operator_initials":
            if value is None:
                overrides["operator_initials"] = ""
            elif not isinstance(value, str):
                raise SettingsValidationError("invalid_operator_initials_type")
            else:
                overrides["operator_initials"] = value
    if watch_dir_value is not None and watch_input_value is not None:
        if watch_dir_value.strip() != watch_input_value.strip():
            raise SettingsValidationError("conflicting_watch_dir_and_watch_input_path")
        overrides["watch_input_path"] = watch_input_value
    elif watch_dir_value is not None:
        overrides["watch_input_path"] = watch_dir_value
    elif watch_input_value is not None:
        overrides["watch_input_path"] = watch_input_value
    return overrides
