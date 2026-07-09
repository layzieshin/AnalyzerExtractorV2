"""Ruleset-Verwaltung: Inventar aktiver Regelsets und Loeschen in den Papierkorb.

Loeschen entfernt den Eintrag aus rules/index.json und verschiebt die
Ruleset-Datei nach rules/trash/<name>.<timestamp>.json - nichts wird
endgueltig geloescht, der Vorgang bleibt manuell wiederherstellbar.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from .errors import RuleSuiteError
from .json_io import _read_json_object, _write_json_atomic
from .validation import _validate_draft_data

_PROTECTED_FILES = {"index.json", "template.json"}


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


def delete_ruleset(project_root: str, assay_key: str) -> Dict[str, Any]:
    """Deregister a ruleset from index.json and move its file to rules/trash/."""
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

    file_name = str(target_row.get("ruleset_file", "")).strip()
    if not file_name or file_name.lower() in _PROTECTED_FILES:
        raise RuleSuiteError(f"protected_or_invalid_ruleset_file: {file_name}")

    target = rules_dir / file_name
    trash_path: str | None = None
    if target.exists():
        trash_dir = rules_dir / "trash"
        trash_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        destination = trash_dir / f"{target.stem}.{timestamp}.json"
        counter = 1
        while destination.exists():
            destination = trash_dir / f"{target.stem}.{timestamp}_{counter}.json"
            counter += 1
        target.replace(destination)
        trash_path = str(destination)

    index["assays"] = [
        row
        for row in assays
        if not (isinstance(row, dict) and str(row.get("assay_key", "")).strip() == key)
    ]
    _write_json_atomic(index_path, index)

    return {"assay_key": key, "ruleset_file": file_name, "trash_path": trash_path}
