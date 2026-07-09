"""Draft-/Ruleset-Validierung.

Bewusst ohne Imports aus ruleresolver oder anderen Projektpaketen gehalten,
damit keine zirkulaeren Importe entstehen (ruleresolver.validator nutzt
_validate_draft_data fuer Integritaetschecks).
"""
from __future__ import annotations

import re
from typing import Any, Dict, List


def _validate_draft_data(data: Dict[str, Any]) -> Dict[str, Any]:
    errors: List[str] = []

    assay_key = str(data.get("assay_key", "")).strip()
    assay_name = str(data.get("assay_name", "")).strip()
    if not assay_key:
        errors.append("assay_key missing")
    if not assay_name:
        errors.append("assay_name missing")

    lot_rule = data.get("lot_rule")
    if not isinstance(lot_rule, dict):
        errors.append("lot_rule must be object")
    else:
        lot_regex = str(lot_rule.get("regex", ""))
        if not lot_regex:
            errors.append("lot_rule.regex missing")
        else:
            _try_compile(lot_regex, "lot_rule.regex", errors)

    extract_rules = data.get("extract_rules")
    if not isinstance(extract_rules, dict):
        errors.append("extract_rules must be object")
        fields: List[Any] = []
        dedupe = None
    else:
        fields = extract_rules.get("fields", [])
        if not isinstance(fields, list):
            errors.append("extract_rules.fields must be list")
            fields = []
        dedupe = extract_rules.get("dedupe_fields")

    field_keys: List[str] = []
    for idx, f in enumerate(fields):
        if not isinstance(f, dict):
            errors.append(f"field[{idx}] must be object")
            continue
        key = str(f.get("key", "")).strip()
        regex = str(f.get("regex", "")).strip()
        if not key:
            errors.append(f"field[{idx}].key missing")
        else:
            field_keys.append(key)
        if not regex:
            errors.append(f"field[{idx}].regex missing")
        else:
            _try_compile(regex, f"field[{idx}].regex", errors)

        search_from = f.get("search_from")
        if search_from is not None:
            if not isinstance(search_from, dict):
                errors.append(f"field[{idx}].search_from must be object")
            else:
                has_after = "after" in search_from
                has_line = "line" in search_from
                if has_after and has_line:
                    errors.append(f"field[{idx}].search_from requires either after or line")
                elif not has_after and not has_line:
                    errors.append(f"field[{idx}].search_from missing after/line")
                elif has_after and not str(search_from.get("after", "")).strip():
                    errors.append(f"field[{idx}].search_from.after empty")
                elif has_after:
                    _try_compile(str(search_from.get("after", "")).strip(), f"field[{idx}].search_from.after", errors)
                elif has_line:
                    try:
                        line_idx = int(search_from.get("line"))
                        if line_idx < 0:
                            errors.append(f"field[{idx}].search_from.line must be >= 0")
                    except Exception:
                        errors.append(f"field[{idx}].search_from.line must be int")

    seen = set()
    duplicates = set()
    for key in field_keys:
        if key in seen:
            duplicates.add(key)
        seen.add(key)
    if duplicates:
        errors.append(f"duplicate field keys: {sorted(duplicates)}")

    if not field_keys:
        errors.append("extract_rules.fields must be non-empty")

    if dedupe is not None:
        if not isinstance(dedupe, list):
            errors.append("extract_rules.dedupe_fields must be list")
        else:
            unknown = [str(k) for k in dedupe if str(k) not in seen]
            if unknown:
                errors.append(f"dedupe_fields unknown keys: {unknown}")

    excel = data.get("excel_rules")
    if not isinstance(excel, dict):
        errors.append("excel_rules must be object")
    else:
        filename_template = str(excel.get("excel_filename_template", ""))
        if not filename_template:
            errors.append("excel_rules.excel_filename_template missing")
        else:
            _validate_template(
                filename_template,
                "excel_rules.excel_filename_template",
                {"assay_key": "a", "assay_name": "b"},
                errors,
            )

        sheet_template = str(excel.get("sheetname_template", ""))
        if not sheet_template:
            errors.append("excel_rules.sheetname_template missing")
        else:
            _validate_template(
                sheet_template,
                "excel_rules.sheetname_template",
                {"lot_id": "LOT"},
                errors,
            )

        col_map = excel.get("column_mapping", {})
        if not isinstance(col_map, dict):
            errors.append("excel_rules.column_mapping must be object")
        else:
            unknown_cols = [str(k) for k in col_map.keys() if str(k) not in seen]
            if unknown_cols:
                errors.append(f"column_mapping unknown keys: {unknown_cols}")

    return {"ok": not errors, "errors": errors}


def _try_compile(regex: str, label: str, errors: List[str]) -> None:
    try:
        re.compile(regex)
    except re.error as e:
        errors.append(f"{label} invalid regex: {e}")


def _validate_template(template: str, label: str, values: Dict[str, str], errors: List[str]) -> None:
    try:
        template.format(**values)
    except Exception as e:
        errors.append(f"{label} invalid template: {e}")
