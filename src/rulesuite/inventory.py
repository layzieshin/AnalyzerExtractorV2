"""Read-only Inventar aktiver Regelwerke, Drafts, Historie und Trash (AP-16C, Phase 7)."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from .json_io import _read_json_object
from .manage import list_rulesets
from .validation import _validate_draft_data

_INVENTORY_KINDS = frozenset({"all", "active", "draft", "inactive", "history", "trash"})


def list_rulesuite_inventory(project_root: str, kind: str = "all") -> List[Dict[str, Any]]:
    normalized_kind = str(kind or "all").strip().lower()
    if normalized_kind not in _INVENTORY_KINDS:
        normalized_kind = "all"

    rows: List[Dict[str, Any]] = []
    root = Path(project_root)

    if normalized_kind in ("all", "active"):
        for row in list_rulesets(project_root):
            ruleset_file = str(row.get("ruleset_file", "")).strip()
            rows.append(
                {
                    "kind": "active",
                    "display_type": "Aktiv",
                    "assay_key": str(row.get("assay_key", "")).strip(),
                    "assay_name": str(row.get("assay_name", "")).strip(),
                    "path": str(root / "rules" / ruleset_file),
                    "ruleset_file": ruleset_file,
                    "field_count": int(row.get("field_count", 0) or 0),
                    "valid": bool(row.get("valid")),
                    "error": row.get("error"),
                    "modified_at": "",
                    "sha256": "",
                    "read_only": False,
                }
            )

    if normalized_kind in ("all", "draft"):
        draft_dir = root / "rules" / "drafts"
        if draft_dir.is_dir():
            for draft_path in sorted(draft_dir.glob("*.draft.json")):
                entry: Dict[str, Any] = {
                    "kind": "draft",
                    "display_type": "Draft",
                    "assay_key": "",
                    "assay_name": "",
                    "path": str(draft_path),
                    "ruleset_file": "",
                    "field_count": 0,
                    "valid": False,
                    "error": None,
                    "modified_at": "",
                    "sha256": "",
                    "read_only": False,
                }
                try:
                    data = _read_json_object(draft_path)
                    entry["assay_key"] = str(data.get("assay_key", "")).strip()
                    entry["assay_name"] = str(data.get("assay_name", "")).strip()
                    extract_rules = data.get("extract_rules")
                    fields = extract_rules.get("fields", []) if isinstance(extract_rules, dict) else []
                    entry["field_count"] = len(fields) if isinstance(fields, list) else 0
                    entry["valid"] = bool(_validate_draft_data(data).get("ok"))
                except Exception as exc:
                    entry["error"] = str(exc)
                rows.append(entry)

    if normalized_kind in ("all", "inactive"):
        inactive_dir = root / "rules" / "inactive"
        if inactive_dir.is_dir():
            for inactive_path in sorted(inactive_dir.glob("*.json")):
                entry: Dict[str, Any] = {
                    "kind": "inactive",
                    "display_type": "Inaktiv",
                    "assay_key": "",
                    "assay_name": "",
                    "path": str(inactive_path),
                    "ruleset_file": "",
                    "field_count": 0,
                    "valid": False,
                    "error": None,
                    "modified_at": "",
                    "sha256": "",
                    "read_only": False,
                }
                try:
                    data = _read_json_object(inactive_path)
                    entry["assay_key"] = str(data.get("assay_key", "")).strip()
                    entry["assay_name"] = str(data.get("assay_name", "")).strip()
                    extract_rules = data.get("extract_rules")
                    fields = extract_rules.get("fields", []) if isinstance(extract_rules, dict) else []
                    entry["field_count"] = len(fields) if isinstance(fields, list) else 0
                    entry["valid"] = bool(_validate_draft_data(data).get("ok"))
                except Exception as exc:
                    entry["error"] = str(exc)
                rows.append(entry)

    if normalized_kind in ("all", "history"):
        rows.extend(
            _list_readonly_archive(
                root / "rules" / "history",
                kind="history",
                display_type="Historie",
            )
        )

    if normalized_kind in ("all", "trash"):
        rows.extend(
            _list_readonly_archive(
                root / "rules" / "trash",
                kind="trash",
                display_type="Trash",
            )
        )

    return rows


def _list_readonly_archive(directory: Path, *, kind: str, display_type: str) -> List[Dict[str, Any]]:
    if not directory.is_dir():
        return []
    rows: List[Dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        if not path.is_file():
            continue
        rows.append(_readonly_archive_row(path, kind=kind, display_type=display_type))
    return rows


def _readonly_archive_row(path: Path, *, kind: str, display_type: str) -> Dict[str, Any]:
    entry: Dict[str, Any] = {
        "kind": kind,
        "display_type": display_type,
        "assay_key": "",
        "assay_name": "",
        "path": str(path),
        "ruleset_file": path.name,
        "field_count": 0,
        "valid": False,
        "error": None,
        "modified_at": "",
        "sha256": "",
        "read_only": True,
    }
    try:
        entry["modified_at"] = _modified_at_iso(path)
        entry["sha256"] = _file_sha256(path)
    except Exception as exc:
        entry["error"] = str(exc)
    try:
        data = _read_json_object(path)
        entry["assay_key"] = str(data.get("assay_key", "")).strip()
        entry["assay_name"] = str(data.get("assay_name", "")).strip()
        extract_rules = data.get("extract_rules")
        fields = extract_rules.get("fields", []) if isinstance(extract_rules, dict) else []
        entry["field_count"] = len(fields) if isinstance(fields, list) else 0
        entry["valid"] = bool(_validate_draft_data(data).get("ok"))
    except Exception as exc:
        entry["error"] = str(exc)
    return entry


def _modified_at_iso(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
