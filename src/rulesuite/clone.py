"""Sicherer Clone eines aktiven Regelwerks in einen Ziel-Draft (AP-16C)."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List

from .candidates import _load_ruleset_data
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


def _header_only_payload(
    source_data: Dict[str, Any],
    target_assay_key: str,
    target_assay_name: str,
) -> Dict[str, Any]:
    source_fields, source_column_mapping = _extract_fields_and_mapping(source_data)
    header = resolve_required_headers_from_source(source_fields, source_column_mapping)
    lot_rule = source_data.get("lot_rule")
    lot_rule = deepcopy(lot_rule) if isinstance(lot_rule, dict) else {"regex": ""}
    return {
        "assay_name": target_assay_name,
        "assay_key": target_assay_key,
        "lot_rule": lot_rule,
        "extract_rules": {"fields": [deepcopy(field) for field in header["fields"]], "dedupe_fields": []},
        "excel_rules": {
            "excel_filename_template": "{assay_name}.xlsx",
            "sheetname_template": "{lot_id}",
            "column_mapping": dict(header["column_mapping"]),
        },
    }


def _result(
    status: str,
    draft_path: Path,
    source_assay_key: str,
    target_assay_key: str,
    target_assay_name: str,
    include_fields: bool,
) -> Dict[str, Any]:
    return {
        "status": status,
        "draft_path": str(draft_path),
        "source_assay_key": source_assay_key,
        "target_assay_key": target_assay_key,
        "target_assay_name": target_assay_name,
        "include_fields": include_fields,
    }


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
    if draft_path.exists() and not overwrite:
        return _result("exists", draft_path, source_assay_key, target_assay_key, target_assay_name, include_fields)

    source_data = _load_ruleset_data(project_root, source_assay_key)
    if include_fields:
        data = deepcopy(source_data)
        data["assay_key"] = target_assay_key
        data["assay_name"] = target_assay_name
    else:
        data = _header_only_payload(source_data, target_assay_key, target_assay_name)

    if not overwrite:
        from .lifecycle import _publish_new_draft_exclusive

        written = _publish_new_draft_exclusive(draft_path, data)
        if written is None:
            return _result("exists", draft_path, source_assay_key, target_assay_key, target_assay_name, include_fields)
        return _result("created", draft_path, source_assay_key, target_assay_key, target_assay_name, include_fields)

    existed = draft_path.exists()
    draft_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json_atomic(draft_path, data)
    status = "overwritten" if existed else "created"
    return _result(status, draft_path, source_assay_key, target_assay_key, target_assay_name, include_fields)
