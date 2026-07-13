"""Header-Regeln aus rules/template.json und Draft-Erzeugung auf Template-Basis.

Die Header-Regeln (Kopffelder + lot_rule) sind in jedem Regelset gleich und
muessen daher bei jeder Neuanlage uebernommen werden - egal ob das Regelset
von einer Vorlage abgeleitet oder von Grund auf erstellt wird.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .errors import RuleSuiteError
from .header_aliases import resolve_required_headers_from_source
from .json_io import _read_json_object, _safe_key, _write_json_atomic
from .required_fields import REQUIRED_HEADER_FIELD_KEYS

HEADER_FIELD_KEYS = REQUIRED_HEADER_FIELD_KEYS


def _load_template_fields_and_mapping(project_root: str) -> Tuple[List[Dict[str, Any]], Dict[str, str], Any]:
    template_path = Path(project_root) / "rules" / "template.json"
    if not template_path.exists():
        raise RuleSuiteError(f"template_not_found: {template_path}")
    data = _read_json_object(template_path)

    extract_rules = data.get("extract_rules")
    raw_fields = extract_rules.get("fields", []) if isinstance(extract_rules, dict) else []
    if not isinstance(raw_fields, list):
        raw_fields = []

    excel_rules = data.get("excel_rules")
    raw_map = excel_rules.get("column_mapping", {}) if isinstance(excel_rules, dict) else {}
    if not isinstance(raw_map, dict):
        raw_map = {}
    column_mapping = {str(k): str(v) for k, v in raw_map.items()}

    fields = [f for f in raw_fields if isinstance(f, dict)]
    return fields, column_mapping, data.get("lot_rule")


def read_required_header_rules(project_root: str) -> Dict[str, Any]:
    """Extract the eight required canonical header fields from template.json."""
    raw_fields, raw_map, lot_rule_raw = _load_template_fields_and_mapping(project_root)
    header = resolve_required_headers_from_source(raw_fields, raw_map)
    lot_rule = deepcopy(lot_rule_raw) if isinstance(lot_rule_raw, dict) else {"regex": ""}
    return {
        "fields": header["fields"],
        "lot_rule": lot_rule,
        "column_mapping": header["column_mapping"],
    }


def read_header_rules(project_root: str) -> Dict[str, Any]:
    """Extract canonical header fields, lot_rule and column_mapping from template.json."""
    raw_fields, raw_map, lot_rule_raw = _load_template_fields_and_mapping(project_root)
    header = resolve_required_headers_from_source(raw_fields, raw_map)
    lot_rule = deepcopy(lot_rule_raw) if isinstance(lot_rule_raw, dict) else {"regex": ""}
    return {
        "fields": header["fields"],
        "lot_rule": lot_rule,
        "column_mapping": header["column_mapping"],
    }


def draft_path_for_assay(project_root: str, assay_key: str) -> str:
    assay_key = assay_key.strip()
    if not assay_key:
        raise RuleSuiteError("assay_key is required")
    draft_dir = Path(project_root) / "rules" / "drafts"
    return str(draft_dir / f"{_safe_key(assay_key)}.draft.json")


def create_draft_from_template_if_missing(
    project_root: str,
    assay_key: str,
    assay_name: str,
) -> Dict[str, str]:
    assay_key = assay_key.strip()
    assay_name = assay_name.strip()
    if not assay_key or not assay_name:
        raise RuleSuiteError("assay_key and assay_name are required")

    draft_path = Path(draft_path_for_assay(project_root, assay_key))
    if draft_path.exists():
        return {
            "status": "exists",
            "draft_path": str(draft_path),
            "assay_key": assay_key,
            "assay_name": assay_name,
        }

    created = create_draft_from_template(project_root, assay_key, assay_name)
    return {
        "status": "created",
        "draft_path": str(created),
        "assay_key": assay_key,
        "assay_name": assay_name,
    }


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
