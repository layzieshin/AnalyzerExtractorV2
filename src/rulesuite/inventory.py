"""Read-only Inventar aktiver Regelwerke und Drafts (AP-16C)."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from .json_io import _read_json_object
from .manage import list_rulesets
from .validation import _validate_draft_data

_INVENTORY_KINDS = frozenset({"all", "active", "draft", "inactive"})


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

    return rows
