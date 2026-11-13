from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any


DEFAULT_DEVICE_ID = "DEFAULT_DEVICE"


def _inventory(store_spec: Mapping[str, Any] | None) -> dict[str, Any]:
    # Lazy to avoid ResultValidation -> JobController -> Runtime -> QC cycles.
    from src.qualitycontrol.api import get_inventory

    return get_inventory(store_spec)


def list_devices(project_root: str | Path, *, store_spec: Mapping[str, Any] | None = None) -> list[dict[str, object]]:
    inventory = _inventory(store_spec)
    return [dict(device) for device in inventory["snapshot"]["devices"] if device["active"]]


def get_default_device_id(project_root: str | Path, *, store_spec: Mapping[str, Any] | None = None) -> str:
    inventory = _inventory(store_spec)["snapshot"]
    active_ids = [str(device["device_id"]) for device in inventory["devices"] if device["active"]]
    stored_default = str(inventory["default_device_id"])
    if stored_default in active_ids:
        return stored_default
    return active_ids[0] if active_ids else DEFAULT_DEVICE_ID


def resolve_device_id(project_root: str | Path, selected_id: str | None = None, *,
                      store_spec: Mapping[str, Any] | None = None) -> str:
    selected = str(selected_id or "").strip()
    if selected:
        from src.qualitycontrol.api import validate_store_spec

        validate_store_spec(store_spec)
        return selected
    return get_default_device_id(project_root, store_spec=store_spec)


def get_device_config_status(project_root: str | Path, *, store_spec: Mapping[str, Any] | None = None) -> dict[str, object]:
    from src.qualitycontrol.api import get_status

    return get_status(store_spec)
