"""Sicherer Clone eines aktiven Regelwerks in einen Ziel-Draft (AP-16C)."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List

from .candidates import _load_ruleset_data, read_candidate_fields
from .errors import RuleSuiteError
from .header_aliases import resolve_required_headers_from_source
from .json_io import _write_json_atomic
from .templates import draft_path_for_assay


def _extract_fields_and_mapping(data: Dict[str, Any]) -> tuple[List[Dict[str, Any]], Dict[str, str]]:
    extract_rules = data.get("extract_rules")
    raw_fields = extract_rules.get("fields", []) if isinstance(extract_rules, dict) else []
    if not isinstance(raw_fields, list):
        raw_fields = []
    fields = [deepcopy(field) for field in raw_fields if isinstance(field, dict)]

    excel_rules = data.get("excel_rules")
    raw_map = excel_rules.get("column_mapping", {}) if isinstance(excel_rules, dict) else {}
    if not isinstance(raw_map, dict):
        raw_map = {}
    column_mapping = {str(key): str(value) for key, value in raw_map.items()}
    return fields, column_mapping


def clone_ruleset_to_draft(
    project_root: str,
    source_assay_key: str,
    target_assay_key: str,
    target_assay_name: str,
    overwrite: bool = False,
    include_fields: bool = True,
) -> Dict[str, Any]:
    source_assay_key = source_assay_key.strip()
    target_assay_key = target_assay_key.strip()
    target_assay_name = target_assay_name.strip()
    if not source_assay_key or not target_assay_key or not target_assay_name:
        raise RuleSuiteError("source_assay_key, target_assay_key and target_assay_name are required")

    draft_path = Path(draft_path_for_assay(project_root, target_assay_key))
    existed = draft_path.exists()
    if existed and not overwrite:
        return {
            "status": "exists",
            "draft_path": str(draft_path),
            "source_assay_key": source_assay_key,
            "target_assay_key": target_assay_key,
            "target_assay_name": target_assay_name,
            "include_fields": include_fields,
        }

    source_data = _load_ruleset_data(project_root, source_assay_key)
    source_fields, source_column_mapping = _extract_fields_and_mapping(source_data)
    header = resolve_required_headers_from_source(source_fields, source_column_mapping)

    lot_rule = source_data.get("lot_rule")
    lot_rule = deepcopy(lot_rule) if isinstance(lot_rule, dict) else {"regex": ""}

    fields = [deepcopy(field) for field in header["fields"]]
    column_mapping = dict(header["column_mapping"])

    if include_fields:
        bundle = read_candidate_fields(project_root, source_assay_key=source_assay_key)
        for field in bundle["fields"]:
            key = str(field.get("key", "")).strip()
            if not key:
                continue
            fields.append(deepcopy(field))
            if key in bundle["column_mapping"]:
                column_mapping[key] = bundle["column_mapping"][key]
            elif key not in column_mapping:
                column_mapping[key] = key

    data: Dict[str, Any] = {
        "assay_name": target_assay_name,
        "assay_key": target_assay_key,
        "lot_rule": lot_rule,
        "extract_rules": {"fields": fields, "dedupe_fields": []},
        "excel_rules": {
            "excel_filename_template": "{assay_name}.xlsx",
            "sheetname_template": "{lot_id}",
            "column_mapping": column_mapping,
        },
    }
    draft_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json_atomic(draft_path, data)

    return {
        "status": "overwritten" if existed else "created",
        "draft_path": str(draft_path),
        "source_assay_key": source_assay_key,
        "target_assay_key": target_assay_key,
        "target_assay_name": target_assay_name,
        "include_fields": include_fields,
    }
