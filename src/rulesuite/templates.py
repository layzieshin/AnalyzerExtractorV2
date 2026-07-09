"""Header-Regeln aus rules/template.json und Draft-Erzeugung auf Template-Basis.

Die Header-Regeln (Kopffelder + lot_rule) sind in jedem Regelset gleich und
muessen daher bei jeder Neuanlage uebernommen werden - egal ob das Regelset
von einer Vorlage abgeleitet oder von Grund auf erstellt wird.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Dict

from .errors import RuleSuiteError
from .json_io import _read_json_object, _safe_key, _write_json_atomic
from .required_fields import REQUIRED_HEADER_FIELD_KEYS

HEADER_FIELD_KEYS = (
    "ANWENDER",
    "ZEIT",
    "DATUM",
    "PLATTE",
    "CHARGE",
    "Haltbarkeit",
    "VALIDATION",
    "FILE_NAME",
)


def read_required_header_rules(project_root: str) -> Dict[str, Any]:
    """Extract only the six required header fields from template.json."""
    template_path = Path(project_root) / "rules" / "template.json"
    if not template_path.exists():
        raise RuleSuiteError(f"template_not_found: {template_path}")
    data = _read_json_object(template_path)

    extract_rules = data.get("extract_rules")
    raw_fields = extract_rules.get("fields", []) if isinstance(extract_rules, dict) else []
    if not isinstance(raw_fields, list):
        raw_fields = []

    fields = []
    field_by_key: Dict[str, Dict[str, Any]] = {}
    for f in raw_fields:
        if not isinstance(f, dict):
            continue
        key = str(f.get("key", "")).strip()
        if key in REQUIRED_HEADER_FIELD_KEYS:
            field_by_key[key] = deepcopy(f)

    for key in REQUIRED_HEADER_FIELD_KEYS:
        if key in field_by_key:
            copied = deepcopy(field_by_key[key])
            copied["required"] = True
            fields.append(copied)
        else:
            fields.append({"key": key, "regex": "", "required": True})

    lot_rule = data.get("lot_rule")
    lot_rule = deepcopy(lot_rule) if isinstance(lot_rule, dict) else {"regex": ""}

    excel_rules = data.get("excel_rules")
    raw_map = excel_rules.get("column_mapping", {}) if isinstance(excel_rules, dict) else {}
    if not isinstance(raw_map, dict):
        raw_map = {}
    header_keys = {str(f.get("key", "")).strip() for f in fields}
    column_mapping = {str(k): str(v) for k, v in raw_map.items() if str(k).strip() in header_keys}
    for key in REQUIRED_HEADER_FIELD_KEYS:
        if key not in column_mapping:
            column_mapping[key] = key

    return {"fields": fields, "lot_rule": lot_rule, "column_mapping": column_mapping}


def read_header_rules(project_root: str) -> Dict[str, Any]:
    """Extract header fields, lot_rule and matching column_mapping from template.json."""
    template_path = Path(project_root) / "rules" / "template.json"
    if not template_path.exists():
        raise RuleSuiteError(f"template_not_found: {template_path}")
    data = _read_json_object(template_path)

    extract_rules = data.get("extract_rules")
    raw_fields = extract_rules.get("fields", []) if isinstance(extract_rules, dict) else []
    if not isinstance(raw_fields, list):
        raw_fields = []

    fields = []
    for f in raw_fields:
        if isinstance(f, dict) and str(f.get("key", "")).strip() in HEADER_FIELD_KEYS:
            fields.append(deepcopy(f))

    lot_rule = data.get("lot_rule")
    lot_rule = deepcopy(lot_rule) if isinstance(lot_rule, dict) else {"regex": ""}

    excel_rules = data.get("excel_rules")
    raw_map = excel_rules.get("column_mapping", {}) if isinstance(excel_rules, dict) else {}
    if not isinstance(raw_map, dict):
        raw_map = {}
    header_keys = {str(f.get("key", "")).strip() for f in fields}
    column_mapping = {str(k): str(v) for k, v in raw_map.items() if str(k).strip() in header_keys}

    return {"fields": fields, "lot_rule": lot_rule, "column_mapping": column_mapping}


def create_draft_from_template(project_root: str, assay_key: str, assay_name: str) -> Path:
    """Like create_blank_draft, but pre-filled with required header rules from template.json."""
    assay_key = assay_key.strip()
    assay_name = assay_name.strip()
    if not assay_key or not assay_name:
        raise RuleSuiteError("assay_key and assay_name are required")

    header = read_required_header_rules(project_root)

    draft_dir = Path(project_root) / "rules" / "drafts"
    draft_dir.mkdir(parents=True, exist_ok=True)
    draft_path = draft_dir / f"{_safe_key(assay_key)}.draft.json"

    data: Dict[str, Any] = {
        "assay_name": assay_name,
        "assay_key": assay_key,
        "lot_rule": header["lot_rule"],
        "extract_rules": {"fields": header["fields"], "dedupe_fields": []},
        "excel_rules": {
            "excel_filename_template": "{assay_name}.xlsx",
            "sheetname_template": "{lot_id}",
            "column_mapping": header["column_mapping"],
        },
    }
    _write_json_atomic(draft_path, data)
    return draft_path
