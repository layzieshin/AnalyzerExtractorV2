from __future__ import annotations

import copy
import json
import os
from dataclasses import replace
from pathlib import Path
from typing import Any

from src.runtime.api import (
    VALID_OUTPUT_MODES,
    get_build_info as runtime_get_build_info,
    get_default_device_id,
    get_device_config_status,
    list_devices,
    load_runtime_config,
)
from src.qualitycontrol.api import (
    ConfigurationContext, MutationContext, QualityControlError, get_inventory as qc_get_inventory,
    legacy_device_source, list_profiles, list_profile_drafts, save_profile_draft, migrate_legacy_devices, save_inventory, save_profile,
)

from .errors import QualityControlApplicationError, SettingsLoadError, SettingsSaveError, SettingsValidationError
from .models import DesktopSettings, DeviceInventoryItem, DeviceInventoryStatus, QCAssayConfigurationItem, QCConfigurationState, WatchTimingSettings
from .presentation import normalize_scan_interval_s, normalize_stable_window_s
from .rules_controller import RuleSuiteController

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
        self._profile_editor_drafts: dict[tuple[str, str], dict[str, Any]] = {}

    @property
    def project_root(self) -> Path:
        return self._project_root

    def settings_path(self) -> Path:
        return self._project_root / "storage" / _SETTINGS_FILE_NAME

    def get_build_info(self) -> dict[str, object]:
        return runtime_get_build_info()

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
        return replace(merged, output_mode="sqlite")

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
        spec = {"driver": "sqlite", "path": self.load().sqlite_path}
        status = get_device_config_status(self._project_root, store_spec=spec)
        devices = tuple(
            DeviceInventoryItem(
                device_id=str(row.get("device_id") or ""),
                display_name=str(row.get("display_name") or row.get("device_id") or ""),
                active=bool(row.get("active", True)),
                serial_number=str(row.get("serial_number") or ""), lnr=str(row.get("lnr") or ""), eva=str(row.get("eva") or ""),
                incomplete=not bool(row.get("display_name")), legacy=bool(row.get("legacy")),
            )
            for row in list_devices(self._project_root, store_spec=spec)
        )
        return DeviceInventoryStatus(
            status=str(status.get("status") or ""),
            path=str(status.get("path") or ""),
            message=str(status.get("message") or ""),
            using_fallback=bool(status.get("using_fallback")),
            devices=devices,
            default_device_id=get_default_device_id(self._project_root, store_spec=spec),
        )

    def reload_device_inventory(self) -> DeviceInventoryStatus:
        return self.get_device_inventory()

    def _qc_store(self, expected_path: str | None = None) -> dict[str, str]:
        path = str(Path(self.load().sqlite_path).resolve())
        if expected_path and str(Path(expected_path).resolve()) != path:
            raise QualityControlApplicationError("Der Ergebnisspeicher wurde gewechselt. Bitte den Dialog schließen und neu laden.")
        return {"driver": "sqlite", "path": path}

    def get_qc_configuration(self) -> QCConfigurationState:
        spec = self._qc_store()
        try:
            inventory = qc_get_inventory(spec, include_history=True, include_unregistered=True)
            # Explicit editor draft only. These compatibility identities are
            # not registered or written merely by discovering/browsing them.
            inventory["snapshot"]["devices"].extend(inventory.get("unregistered_devices", []))
            profiles = tuple(list_profiles(spec))
            try:
                source = legacy_device_source(self._project_root)
                source_hash, message = source["sha256"], "Vorhandene Gerätedatei kann ausdrücklich übernommen werden."
            except QualityControlError as exc:
                source_hash, message = "", str(exc)
            return QCConfigurationState(spec["path"], inventory, profiles, source_hash, message,
                retained_drafts=tuple(list_profile_drafts(spec)))
        except QualityControlError as exc:
            raise QualityControlApplicationError(str(exc)) from exc

    def migrate_qc_devices(self, state: QCConfigurationState, operator_initials: str, request_id: str) -> dict[str, Any]:
        spec = self._qc_store(state.store_path)
        try:
            return migrate_legacy_devices(spec, self._project_root, expected_source_sha256=state.legacy_source_sha256,
                context=MutationContext(operator_initials, request_id))
        except QualityControlError as exc:
            raise QualityControlApplicationError(str(exc)) from exc

    def get_qc_assay_configuration(self) -> QCConfigurationState:
        """Read all active assays, plus every distinct existing profile binding."""
        state = self.get_qc_configuration()
        rules = RuleSuiteController(self._project_root)
        try:
            catalog = rules.list_inventory(kind="active")
        except Exception as exc:
            return replace(state, catalog_error=f"Der aktive Regelkatalog konnte nicht geladen werden. Bitte die Regelverwaltung prüfen und neu laden: {exc}")
        assays = tuple((item.assay_name or "Assayname fehlt", item.assay_key) for item in catalog if item.assay_key)
        fields, errors = {}, {}
        for _name, key in assays:
            try:
                fields[key] = tuple(rules.list_fields(key))
            except Exception as exc:
                # An unreadable rule remains visible, but provides no valid choices.
                fields[key] = ()
                errors[key] = f"Aktuelle Regelfelder nicht verfügbar: {exc}"
        devices = {row["device_id"]: row for row in state.inventory["snapshot"]["devices"]}
        rows = []

        def profile_row(name, key, record, *, active=True):
            value = record["snapshot"]
            device = devices.get(value["device_id"], {})
            issues = []
            if not active:
                issues.append("Die zugehörige Regel ist nicht aktiv.")
            if key in errors:
                issues.append(errors[key])
            if not device or not device.get("display_name") or not device.get("active", True):
                if value["device_id"]:
                    issues.append("Gerätebindung prüfen.")
            for control in value["controls"]:
                mapping = control.get("fields", {})
                modern = value.get("profile_schema_version") == 2
                invalid = [f"{role}: {mapping.get(role) or 'fehlt'}" for role in ("MIN", "MAX", "SOLL", "IST")
                           if (not mapping.get(role) and (not modern or role == "IST")) or (mapping.get(role) and mapping.get(role) not in fields.get(key, ()))]
                assigned = [field for field in mapping.values() if field]
                if len(set(assigned)) != len(assigned):
                    invalid.append("Zugeordnete Felder müssen verschieden sein")
                if invalid:
                    issues.append(f"{control['name']}: {', '.join(invalid)}")
            return QCAssayConfigurationItem(key, name, value["device_id"], device.get("display_name") or value["device_id"] or "Alle Geräte dieses Assays",
                record["profile_id"], value["name"], record["version_id"], len(value["controls"]),
                "Feldzuordnung prüfen" if issues else "Eingerichtet", tuple(issues))

        for name, key in assays:
            profiles = [record for record in state.profiles if record["snapshot"]["assay_key"] == key]
            rows.extend(profile_row(name, key, record) for record in profiles)
            if not profiles:
                rows.append(QCAssayConfigurationItem(key, name, issues=(errors[key],) if key in errors else ()))
        active_keys = {key for _name, key in assays}
        rows.extend(profile_row("Assay nicht aktiv", record["snapshot"]["assay_key"], record, active=False)
                    for record in state.profiles if record["snapshot"]["assay_key"] not in active_keys)
        names = dict((key, name) for name, key in assays)
        for draft in state.retained_drafts:
            value = draft["snapshot"]
            key = str(value.get("assay_key") or "")
            device_id = str(value.get("device_id") or "")
            rows.append(QCAssayConfigurationItem(key, names.get(key, "Assay nicht aktiv"), device_id,
                devices.get(device_id, {}).get("display_name", "") or "Alle Geräte dieses Assays", draft["profile_id"],
                str(value.get("name") or "Unbenannter Entwurf") + " (Entwurf)", draft["base_version_id"],
                len(value.get("controls") or []), "Entwurf fortsetzen", (), draft["draft_id"]))
        return replace(state, assays=assays, field_choices=fields, assay_rows=tuple(rows))

    def save_qc_inventory(self, state: QCConfigurationState, snapshot: dict[str, Any], operator_initials: str,
                          request_id: str) -> dict[str, Any]:
        spec = self._qc_store(state.store_path)
        try:
            return save_inventory(spec, snapshot, expected_version_id=state.inventory["version_id"],
                                  context=ConfigurationContext(request_id, operator_initials))
        except QualityControlError as exc:
            raise QualityControlApplicationError(str(exc)) from exc

    def save_qc_profile(self, state: QCConfigurationState, snapshot: dict[str, Any], *, expected_version_id: int,
                        operator_initials: str, request_id: str) -> dict[str, Any]:
        spec = self._qc_store(state.store_path)
        try:
            # Never trust the dialog's catalog: rules may have changed since opening.
            fields = RuleSuiteController(self._project_root).list_fields(str(snapshot.get("assay_key") or ""))
        except Exception as exc:
            raise QualityControlApplicationError(f"Aktuelle Regelfelder konnten nicht geladen werden. Bitte die Regel und Feldzuordnung prüfen: {exc}") from exc
        try:
            result = save_profile(spec, snapshot, expected_version_id=expected_version_id,
                expected_inventory_version_id=state.inventory["version_id"], context=ConfigurationContext(request_id, operator_initials),
                available_field_keys=fields, draft_id=str(snapshot.get("_draft_id") or ""))
            for key, draft in list(self._profile_editor_drafts.items()):
                if key[0] == spec["path"] and draft.get("profile_id") == result["profile_id"]:
                    del self._profile_editor_drafts[key]
            return result
        except QualityControlError as exc:
            raise QualityControlApplicationError(str(exc)) from exc

    def get_qc_profile_editor(self, state: QCConfigurationState, *, assay_key: str, profile_id: str = "", draft_id: str = "") -> dict[str, Any] | None:
        """Session text wins over stored heads; stale bases remain visible."""
        spec = self._qc_store(state.store_path)
        key = (spec["path"], "draft:" + draft_id if draft_id else profile_id or "new:" + assay_key)
        if key in self._profile_editor_drafts:
            return copy.deepcopy(self._profile_editor_drafts[key])
        retained = [row for row in state.retained_drafts if row["draft_id"] == draft_id] if draft_id else [row for row in state.retained_drafts if row["profile_id"] == profile_id] if profile_id else [
            row for row in state.retained_drafts if row["snapshot"].get("assay_key") == assay_key and not row["base_version_id"]]
        if len(retained) == 1:
            row = retained[0]
            draft = {"editor_key": key[1], "draft_id": row["draft_id"], "profile_id": row["profile_id"], "base_version_id": row["base_version_id"],
                     "draft_version_id": row["version_id"], "snapshot": copy.deepcopy(row["snapshot"])}
            self._profile_editor_drafts[key] = draft
            return copy.deepcopy(draft)
        return None

    def update_qc_profile_editor(self, state: QCConfigurationState, draft: dict[str, Any], *, editor_key: str) -> None:
        spec = self._qc_store(state.store_path)
        self._profile_editor_drafts[(spec["path"], editor_key)] = copy.deepcopy(draft)

    def retain_qc_profile_editor(self, state: QCConfigurationState, draft: dict[str, Any], *, editor_key: str, request_id: str) -> dict[str, Any]:
        spec = self._qc_store(state.store_path)
        try:
            record = save_profile_draft(spec, draft_id=draft["draft_id"], profile_id=draft["profile_id"],
                base_version_id=draft["base_version_id"], snapshot=draft["snapshot"], expected_version_id=draft.get("draft_version_id", 0),
                context=ConfigurationContext(request_id))
            updated = {**copy.deepcopy(draft), "editor_key": editor_key, "draft_version_id": record["version_id"]}
            self.update_qc_profile_editor(state, updated, editor_key=editor_key)
            return updated
        except QualityControlError as exc:
            raise QualityControlApplicationError(str(exc)) from exc

    def discard_qc_profile_editor(self, state: QCConfigurationState, draft: dict[str, Any], *, editor_key: str, request_id: str) -> None:
        spec = self._qc_store(state.store_path)
        if draft.get("draft_version_id"):
            try:
                save_profile_draft(spec, draft_id=draft["draft_id"], profile_id=draft["profile_id"], base_version_id=draft["base_version_id"],
                    snapshot=draft["snapshot"], expected_version_id=draft["draft_version_id"], context=ConfigurationContext(request_id), discard=True)
            except QualityControlError as exc:
                raise QualityControlApplicationError(str(exc)) from exc
        self._profile_editor_drafts.pop((spec["path"], editor_key), None)

    def open_output_folder(self, *, path_opener=None) -> str:
        from .desktop_actions import open_path

        target = self.canonical_output_dir()
        target.mkdir(parents=True, exist_ok=True)
        open_path(str(target), opener=path_opener)
        return str(target)

    def save(self, settings: DesktopSettings) -> DesktopSettings:
        self.validate(settings)
        settings = replace(settings, output_mode="sqlite")
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
