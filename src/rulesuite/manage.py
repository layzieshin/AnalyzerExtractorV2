"""Ruleset-Verwaltung: Inventar aktiver Regelsets.

Aktive Regelwerke werden ueber AP-16D lifecycle.deactivate_ruleset inaktiviert;
direktes Loeschen aktiver Rules ist nicht mehr vorgesehen.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from .errors import RuleSuiteError
from .json_io import _read_json_object
from .validation import _validate_draft_data


def list_rulesets(project_root: str) -> List[Dict[str, Any]]:
    """Inventory of all registered rulesets with field count and validity."""
    rules_dir = Path(project_root) / "rules"
    index = _read_json_object(rules_dir / "index.json")
    assays = index.get("assays", [])
    if not isinstance(assays, list):
        raise RuleSuiteError("index.assays must be list")

    out: List[Dict[str, Any]] = []
    for row in assays:
        if not isinstance(row, dict):
            continue
        key = str(row.get("assay_key", "")).strip()
        file_name = str(row.get("ruleset_file", "")).strip()
        if not key or not file_name:
            continue

        entry: Dict[str, Any] = {
            "assay_key": key,
            "ruleset_file": file_name,
            "assay_name": "",
            "field_count": 0,
            "valid": False,
            "error": None,
        }
        path = rules_dir / file_name
        if not path.exists():
            entry["error"] = "file_missing"
        else:
            try:
                data = _read_json_object(path)
                entry["assay_name"] = str(data.get("assay_name", ""))
                extract_rules = data.get("extract_rules")
                fields = extract_rules.get("fields", []) if isinstance(extract_rules, dict) else []
                entry["field_count"] = len(fields) if isinstance(fields, list) else 0
                entry["valid"] = bool(_validate_draft_data(data).get("ok"))
            except Exception as e:
                entry["error"] = str(e)
        out.append(entry)
    return out
