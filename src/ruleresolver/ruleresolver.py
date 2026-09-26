from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict

from .model import RuleSet


class RuleResolverError(RuntimeError):
    pass


class RuleResolver:
    def resolve_ruleset(self, assay_key: str, rules_dir: str, rules_index_path: str) -> RuleSet:
        try:
            idx = json.loads(Path(rules_index_path).read_text(encoding="utf-8"))
        except Exception as e:
            raise RuleResolverError(f"Cannot read index.json: {e}") from e

        mapping: Dict[str, str] = {}
        for a in idx.get("assays", []):
            k = a.get("assay_key")
            f = a.get("ruleset_file")
            if k and f:
                mapping[k] = f

        if assay_key not in mapping:
            raise RuleResolverError(f"Unknown assay_key: {assay_key}")

        ruleset_file = mapping[assay_key]
        path = Path(rules_dir) / ruleset_file
        if not path.exists():
            raise RuleResolverError(f"RuleSet file not found: {path}")

        try:
            data: Dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            raise RuleResolverError(f"Cannot parse RuleSet JSON: {e}") from e

        if data.get("assay_key") != assay_key:
            raise RuleResolverError("RuleSet assay_key mismatch")

        for req in ("lot_rule", "extract_rules", "excel_rules"):
            if req not in data:
                raise RuleResolverError(f"RuleSet missing required section: {req}")

        _validate_runtime_ruleset(data)
        return RuleSet(assay_key=assay_key, ruleset_file=ruleset_file, data=data)


def _validate_runtime_ruleset(data: Dict[str, Any]) -> None:
    lot_rule = data.get("lot_rule")
    if not isinstance(lot_rule, dict):
        raise RuleResolverError("RuleSet lot_rule must be object")
    lot_regex = str(lot_rule.get("regex", "")).strip()
    if not lot_regex:
        raise RuleResolverError("RuleSet lot_rule.regex missing")
    try:
        re.compile(lot_regex)
    except re.error as e:
        raise RuleResolverError(f"RuleSet lot_rule.regex invalid: {e}") from e

    extract_rules = data.get("extract_rules")
    if not isinstance(extract_rules, dict):
        raise RuleResolverError("RuleSet extract_rules must be object")

    fields = extract_rules.get("fields")
    if not isinstance(fields, list) or not fields:
        raise RuleResolverError("RuleSet extract_rules.fields missing/empty")
    for idx, field in enumerate(fields):
        if not isinstance(field, dict):
            raise RuleResolverError(f"RuleSet field[{idx}] must be object")
        key = str(field.get("key", "")).strip()
        regex = str(field.get("regex", "")).strip()
        if not key or not regex:
            raise RuleResolverError(f"RuleSet field[{idx}] requires key+regex")
        try:
            re.compile(regex)
        except re.error as e:
            raise RuleResolverError(f"RuleSet field[{idx}].regex invalid: {e}") from e

        search_from = field.get("search_from")
        if search_from is not None:
            if not isinstance(search_from, dict):
                raise RuleResolverError(f"RuleSet field[{idx}].search_from must be object")
            if "after" in search_from and "line" in search_from:
                raise RuleResolverError(f"RuleSet field[{idx}].search_from requires either after or line")
            if "after" in search_from:
                marker = str(search_from.get("after", "")).strip()
                if not marker:
                    raise RuleResolverError(f"RuleSet field[{idx}].search_from.after empty")
                try:
                    re.compile(marker)
                except re.error as e:
                    raise RuleResolverError(f"RuleSet field[{idx}].search_from.after invalid: {e}") from e
            elif "line" in search_from:
                try:
                    if int(search_from.get("line")) < 0:
                        raise RuleResolverError(f"RuleSet field[{idx}].search_from.line must be >= 0")
                except Exception as e:
                    raise RuleResolverError(f"RuleSet field[{idx}].search_from.line must be int") from e
            else:
                raise RuleResolverError(f"RuleSet field[{idx}].search_from missing after/line")

    excel_rules = data.get("excel_rules")
    if not isinstance(excel_rules, dict):
        raise RuleResolverError("RuleSet excel_rules must be object")

    filename_template = str(excel_rules.get("excel_filename_template", "")).strip()
    if not filename_template:
        raise RuleResolverError("RuleSet excel_rules.excel_filename_template missing")
    try:
        filename_template.format(assay_key="a", assay_name="b")
    except Exception as e:
        raise RuleResolverError(f"RuleSet excel_filename_template invalid: {e}") from e

    sheet_template = str(excel_rules.get("sheetname_template", "")).strip()
    if not sheet_template:
        raise RuleResolverError("RuleSet excel_rules.sheetname_template missing")
    try:
        sheet_template.format(lot_id="L")
    except Exception as e:
        raise RuleResolverError(f"RuleSet sheetname_template invalid: {e}") from e
