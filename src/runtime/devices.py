from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_DEVICE_ID = "DEFAULT_DEVICE"
_FALLBACK_DEVICE = {
    "device_id": DEFAULT_DEVICE_ID,
    "display_name": DEFAULT_DEVICE_ID,
    "active": True,
}


def list_devices(project_root: str | Path) -> list[dict[str, object]]:
    state = _load_device_config(project_root)
    if state["status"] != "ok":
        return [dict(_FALLBACK_DEVICE)]
    devices = state["devices"]
    return [dict(device) for device in devices if bool(device.get("active", True))]


def get_default_device_id(project_root: str | Path) -> str:
    state = _load_device_config(project_root)
    if state["status"] != "ok":
        return DEFAULT_DEVICE_ID
    default_id = str(state.get("default_device_id") or "").strip()
    active_devices = list_devices(project_root)
    active_ids = {str(device["device_id"]) for device in active_devices}
    if default_id in active_ids:
        return default_id
    return str(active_devices[0]["device_id"]) if active_devices else DEFAULT_DEVICE_ID


def resolve_device_id(project_root: str | Path, selected_id: str | None = None) -> str:
    selected = str(selected_id or "").strip()
    if selected:
        return selected
    return get_default_device_id(project_root)


def get_device_config_status(project_root: str | Path) -> dict[str, object]:
    state = _load_device_config(project_root)
    return {
        "status": state["status"],
        "path": str(state["path"]),
        "message": state["message"],
        "using_fallback": state["status"] != "ok",
    }


def _load_device_config(project_root: str | Path) -> dict[str, Any]:
    path = Path(project_root) / "config" / "devices.json"
    if not path.exists():
        return {
            "status": "missing",
            "path": path,
            "message": "config/devices.json not found; using DEFAULT_DEVICE",
            "devices": [dict(_FALLBACK_DEVICE)],
            "default_device_id": DEFAULT_DEVICE_ID,
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("root must be object")
        raw_devices = data.get("devices")
        if not isinstance(raw_devices, list):
            raise ValueError("devices must be list")

        devices: list[dict[str, object]] = []
        for raw in raw_devices:
            if not isinstance(raw, dict):
                continue
            device_id = str(raw.get("device_id", "")).strip()
            if not device_id:
                continue
            display_name = str(raw.get("display_name") or device_id).strip() or device_id
            active = bool(raw.get("active", True))
            devices.append({"device_id": device_id, "display_name": display_name, "active": active})
        if not devices:
            raise ValueError("no valid devices")
        default_id = str(data.get("default_device_id") or devices[0]["device_id"]).strip()
        return {
            "status": "ok",
            "path": path,
            "message": "device config loaded",
            "devices": devices,
            "default_device_id": default_id,
        }
    except Exception as exc:
        return {
            "status": "invalid",
            "path": path,
            "message": f"invalid devices config: {exc}; using DEFAULT_DEVICE",
            "devices": [dict(_FALLBACK_DEVICE)],
            "default_device_id": DEFAULT_DEVICE_ID,
        }
