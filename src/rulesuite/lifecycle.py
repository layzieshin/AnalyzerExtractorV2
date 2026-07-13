"""Regelwerk-Lifecycle: inaktivieren und Inventar-Löschung (AP-16D)."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from .errors import RuleSuiteError
from .json_io import _read_json_object, _write_json_atomic
from .templates import draft_path_for_assay

_PROTECTED_FILES = {"index.json", "template.json"}


def _validate_ruleset_filename(file_name: str) -> str:
    name = file_name.strip()
    if not name:
        raise RuleSuiteError("protected_or_invalid_ruleset_file:")
    lowered = name.lower()
    if lowered in _PROTECTED_FILES:
        raise RuleSuiteError(f"protected_or_invalid_ruleset_file: {name}")
    if name != Path(name).name or ".." in name or "/" in name or "\\" in name:
        raise RuleSuiteError(f"protected_or_invalid_ruleset_file: {name}")
    return name


def _unique_destination(directory: Path, stem: str, suffix: str = ".json") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    destination = directory / f"{stem}.{timestamp}{suffix}"
    counter = 1
    while destination.exists():
        destination = directory / f"{stem}.{timestamp}_{counter}{suffix}"
        counter += 1
    return destination


def _inventory_base_dir(project_root: str, kind: str) -> Path:
    root = Path(project_root)
    if kind == "draft":
        return (root / "rules" / "drafts").resolve()
    if kind == "inactive":
        return (root / "rules" / "inactive").resolve()
    if kind == "active":
        return (root / "rules").resolve()
    raise RuleSuiteError(f"unsupported_inventory_kind: {kind}")


def _resolve_inventory_path(project_root: str, kind: str, path_or_key: str) -> Path:
    if kind == "active":
        raise RuleSuiteError("active_must_be_deactivated_first")

    base = _inventory_base_dir(project_root, kind)
    candidate = Path(path_or_key)
    if not candidate.is_absolute():
        candidate = base / path_or_key
    resolved = candidate.resolve()
    try:
        resolved.relative_to(base)
    except ValueError as exc:
        raise RuleSuiteError("path_outside_allowed_directory") from exc
    return resolved


def deactivate_ruleset(project_root: str, assay_key: str) -> Dict[str, Any]:
    key = assay_key.strip()
    if not key:
        raise RuleSuiteError("assay_key required")

    rules_dir = Path(project_root) / "rules"
    index_path = rules_dir / "index.json"
    index = _read_json_object(index_path)
    assays = index.get("assays", [])
    if not isinstance(assays, list):
        raise RuleSuiteError("index.assays must be list")

    target_row = next(
        (row for row in assays if isinstance(row, dict) and str(row.get("assay_key", "")).strip() == key),
        None,
    )
    if target_row is None:
        raise RuleSuiteError(f"assay_not_found: {key}")

    file_name = _validate_ruleset_filename(str(target_row.get("ruleset_file", "")))
    source = rules_dir / file_name
    inactive_path: str | None = None
    if source.exists():
        inactive_dir = rules_dir / "inactive"
        destination = _unique_destination(inactive_dir, source.stem)
        source.replace(destination)
        inactive_path = str(destination)

    index["assays"] = [
        row
        for row in assays
        if not (isinstance(row, dict) and str(row.get("assay_key", "")).strip() == key)
    ]
    _write_json_atomic(index_path, index)

    return {
        "assay_key": key,
        "ruleset_file": file_name,
        "inactive_path": inactive_path,
    }


def delete_inventory_item(project_root: str, kind: str, path_or_key: str) -> Dict[str, Any]:
    normalized_kind = str(kind or "").strip().lower()
    if normalized_kind == "active":
        raise RuleSuiteError("active_must_be_deactivated_first")

    source = _resolve_inventory_path(project_root, normalized_kind, path_or_key)
    if not source.exists():
        raise RuleSuiteError(f"inventory_item_not_found: {source}")

    trash_dir = Path(project_root) / "rules" / "trash"
    destination = _unique_destination(trash_dir, source.stem)
    source.replace(destination)

    return {
        "kind": normalized_kind,
        "source_path": str(source),
        "trash_path": str(destination),
    }


def open_inactive_as_draft(project_root: str, inactive_path: str) -> Dict[str, Any]:
    inactive_file = _resolve_inventory_path(project_root, "inactive", inactive_path)
    data = _read_json_object(inactive_file)
    assay_key = str(data.get("assay_key", "")).strip()
    assay_name = str(data.get("assay_name", "")).strip()
    if not assay_key:
        raise RuleSuiteError("inactive_missing_assay_key")

    draft_path = Path(draft_path_for_assay(project_root, assay_key))
    if draft_path.exists():
        return {
            "status": "exists",
            "draft_path": str(draft_path),
            "assay_key": assay_key,
            "assay_name": assay_name,
            "inactive_path": str(inactive_file),
        }

    draft_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json_atomic(draft_path, data)
    return {
        "status": "created",
        "draft_path": str(draft_path),
        "assay_key": assay_key,
        "assay_name": assay_name,
        "inactive_path": str(inactive_file),
    }


def delete_ruleset(project_root: str, assay_key: str) -> Dict[str, Any]:
    """Compatibility wrapper: deactivates instead of deleting active rules."""
    return deactivate_ruleset(project_root, assay_key)
