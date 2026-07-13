"""Kandidatenfelder aus Template oder Quell-Ruleset (AP-3)."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Set

from src.ruleresolver.api import resolve_ruleset

from .errors import RuleSuiteError
from .header_aliases import excluded_candidate_keys_for_ruleset_source, resolve_required_headers_from_source
from .json_io import _read_json_object, _safe_key, _write_json_atomic
from .regex_tools import locate_fields
from .required_fields import _result_row

_SEARCH_FROM_UNSET = object()


def _parse_candidate_source(candidate_source: Dict[str, Any]) -> tuple[str, str | None]:
    if not isinstance(candidate_source, dict):
        raise RuleSuiteError("candidate_source must be object")
    has_template = candidate_source.get("source") == "template"
    assay_key = candidate_source.get("source_assay_key")
    has_ruleset = isinstance(assay_key, str) and assay_key.strip()
    if has_template and has_ruleset:
        raise RuleSuiteError("candidate_source: specify either source='template' or source_assay_key")
    if has_template:
        return "template", None
    if has_ruleset:
        return "ruleset", assay_key.strip()
    raise RuleSuiteError("candidate_source: specify source='template' or source_assay_key")


def _load_ruleset_data(project_root: str, source_assay_key: str) -> Dict[str, Any]:
    root = Path(project_root)
    rs = resolve_ruleset(source_assay_key, str(root / "rules"), str(root / "rules" / "index.json"))
    return deepcopy(rs.data)


def _load_template_data(project_root: str) -> Dict[str, Any]:
    template_path = Path(project_root) / "rules" / "template.json"
    if not template_path.exists():
        raise RuleSuiteError(f"template_not_found: {template_path}")
    return _read_json_object(template_path)


def _extract_fields_and_mapping(data: Dict[str, Any]) -> tuple[List[Dict[str, Any]], Dict[str, str]]:
    extract_rules = data.get("extract_rules")
    raw_fields = extract_rules.get("fields", []) if isinstance(extract_rules, dict) else []
    if not isinstance(raw_fields, list):
        raw_fields = []
    fields = [deepcopy(f) for f in raw_fields if isinstance(f, dict)]

    excel_rules = data.get("excel_rules")
    raw_map = excel_rules.get("column_mapping", {}) if isinstance(excel_rules, dict) else {}
    if not isinstance(raw_map, dict):
        raw_map = {}
    column_mapping = {str(k): str(v) for k, v in raw_map.items()}
    return fields, column_mapping


def _candidate_excluded_keys(source_kind: str) -> Set[str]:
    del source_kind
    return set(excluded_candidate_keys_for_ruleset_source())


def _load_source_bundle(project_root: str, candidate_source: Dict[str, Any]) -> Dict[str, Any]:
    source_kind, assay_key = _parse_candidate_source(candidate_source)
    if source_kind == "template":
        data = _load_template_data(project_root)
        source_label: Dict[str, Any] = {"source": "template"}
    else:
        assert assay_key is not None
        data = _load_ruleset_data(project_root, assay_key)
        source_label = {"source_assay_key": assay_key}

    fields, column_mapping = _extract_fields_and_mapping(data)
    lot_rule = data.get("lot_rule")
    lot_rule = deepcopy(lot_rule) if isinstance(lot_rule, dict) else {"regex": ""}
    return {
        "source": source_label,
        "fields": fields,
        "column_mapping": column_mapping,
        "lot_rule": lot_rule,
        "source_kind": source_kind,
    }


def _build_candidate_source(*, source: str | None = None, source_assay_key: str | None = None) -> Dict[str, Any]:
    if source == "template" and not source_assay_key:
        return {"source": "template"}
    if source_assay_key and source != "template":
        return {"source_assay_key": source_assay_key.strip()}
    raise RuleSuiteError("specify source='template' or source_assay_key")


def bundle_kwargs_from_source(candidate_source: Dict[str, Any]) -> Dict[str, Any]:
    source_kind, assay_key = _parse_candidate_source(candidate_source)
    if source_kind == "template":
        return {"source": "template"}
    return {"source_assay_key": assay_key}


def read_candidate_fields(
    project_root: str,
    *,
    source: str | None = None,
    source_assay_key: str | None = None,
) -> Dict[str, Any]:
    candidate_source = _build_candidate_source(source=source, source_assay_key=source_assay_key)
    bundle = _load_source_bundle(project_root, candidate_source)
    excluded = _candidate_excluded_keys(bundle["source_kind"])

    candidates: List[Dict[str, Any]] = []
    col_subset: Dict[str, str] = {}
    for field in bundle["fields"]:
        key = str(field.get("key", "")).strip()
        if not key or key in excluded:
            continue
        candidates.append(deepcopy(field))
        if key in bundle["column_mapping"]:
            col_subset[key] = bundle["column_mapping"][key]

    return {
        "source": bundle["source"],
        "fields": candidates,
        "column_mapping": col_subset,
    }


def _draft_field_keys(draft_path: str) -> Set[str]:
    data = _read_json_object(Path(draft_path))
    extract_rules = data.get("extract_rules")
    raw_fields = extract_rules.get("fields", []) if isinstance(extract_rules, dict) else []
    if not isinstance(raw_fields, list):
        return set()
    return {str(f.get("key", "")).strip() for f in raw_fields if isinstance(f, dict) and str(f.get("key", "")).strip()}


def check_candidates(
    project_root: str,
    assay_text: str,
    draft_path: str,
    candidate_source: Dict[str, Any],
    *,
    dismissed_keys: tuple[str, ...] | list[str] = (),
    group: int = 1,
) -> Dict[str, Any]:
    bundle = read_candidate_fields(project_root, **bundle_kwargs_from_source(candidate_source))
    in_draft = _draft_field_keys(draft_path)
    dismissed = {str(k).strip() for k in dismissed_keys if str(k).strip()}

    active: List[Dict[str, Any]] = []
    for field in bundle["fields"]:
        key = str(field.get("key", "")).strip()
        if key and key not in in_draft and key not in dismissed:
            active.append(field)

    located: Dict[str, Dict[str, Any]] = {}
    if assay_text.strip() and active:
        loc = locate_fields(active, assay_text, group=group)
        for row in loc.get("results", []):
            if isinstance(row, dict) and row.get("key"):
                located[str(row["key"])] = row

    results: List[Dict[str, Any]] = []
    for field in active:
        key = str(field.get("key", "")).strip()
        regex = str(field.get("regex", "")).strip()
        search_from = field.get("search_from") if isinstance(field.get("search_from"), dict) else None
        required = bool(field.get("required", False))

        if not regex:
            results.append(
                _result_row(key, required=required, status="missing_regex", has_regex=False, search_from=search_from)
            )
            continue

        row = located.get(key)
        if row is None:
            results.append(
                _result_row(key, required=required, status="miss", has_regex=True, search_from=search_from)
            )
            continue

        if row.get("error"):
            results.append(
                _result_row(
                    key,
                    required=required,
                    status="error",
                    has_regex=True,
                    matched=False,
                    value=row.get("value"),
                    span=row.get("span"),
                    error=row.get("error"),
                    search_from=search_from,
                )
            )
            continue

        if row.get("matched"):
            results.append(
                _result_row(
                    key,
                    required=required,
                    status="confirmed",
                    has_regex=True,
                    matched=True,
                    value=row.get("value"),
                    span=row.get("span"),
                    search_from=search_from,
                )
            )
        else:
            results.append(
                _result_row(
                    key,
                    required=required,
                    status="miss",
                    has_regex=True,
                    matched=False,
                    search_from=search_from,
                )
            )

    confirmed = sum(1 for row in results if row["status"] == "confirmed")
    return {
        "source": bundle["source"],
        "total": len(active),
        "confirmed": confirmed,
        "results": results,
    }


def _find_candidate_field(bundle: Dict[str, Any], field_key: str) -> Dict[str, Any] | None:
    field_key = field_key.strip()
    excluded = _candidate_excluded_keys(bundle["source_kind"])
    if field_key in excluded:
        return None
    for field in bundle["fields"]:
        if str(field.get("key", "")).strip() == field_key:
            return field
    return None


def adopt_candidate_field(
    project_root: str,
    draft_path: str,
    field_key: str,
    candidate_source: Dict[str, Any],
    *,
    regex: str | None = None,
    required: bool | None = None,
    search_from: Dict[str, Any] | None = _SEARCH_FROM_UNSET,  # type: ignore[assignment]
) -> Path:
    field_key = field_key.strip()
    if not field_key:
        raise RuleSuiteError("field key required")

    path = Path(draft_path)
    data = _read_json_object(path)
    extract_rules = data.setdefault("extract_rules", {})
    fields = extract_rules.get("fields")
    if not isinstance(fields, list):
        fields = []
        extract_rules["fields"] = fields

    if any(str(f.get("key", "")).strip() == field_key for f in fields if isinstance(f, dict)):
        raise RuleSuiteError(f"field_exists: {field_key}")

    full_bundle = _load_source_bundle(project_root, candidate_source)
    source_field = _find_candidate_field(full_bundle, field_key)
    if source_field is None:
        raise RuleSuiteError(f"candidate_not_found: {field_key}")

    row = deepcopy(source_field)
    row["key"] = field_key

    if regex is not None:
        row["regex"] = regex
    if required is not None:
        row["required"] = bool(required)
    else:
        row["required"] = bool(source_field.get("required", False))

    if search_from is not _SEARCH_FROM_UNSET:
        if search_from:
            row["search_from"] = search_from
        else:
            row.pop("search_from", None)
    elif isinstance(source_field.get("search_from"), dict):
        row["search_from"] = deepcopy(source_field["search_from"])

    fields.append(row)

    col_map = data.setdefault("excel_rules", {}).setdefault("column_mapping", {})
    if not isinstance(col_map, dict):
        col_map = {}
        data["excel_rules"]["column_mapping"] = col_map
    if field_key in full_bundle["column_mapping"]:
        col_map[field_key] = full_bundle["column_mapping"][field_key]
    elif field_key not in col_map:
        col_map[field_key] = field_key

    _write_json_atomic(path, data)
    return path


def create_draft_from_ruleset(
    project_root: str,
    source_assay_key: str,
    new_assay_key: str,
    new_assay_name: str,
) -> Path:
    source_assay_key = source_assay_key.strip()
    new_assay_key = new_assay_key.strip()
    new_assay_name = new_assay_name.strip()
    if not source_assay_key or not new_assay_key or not new_assay_name:
        raise RuleSuiteError("source_assay_key, new_assay_key and new_assay_name are required")

    source_data = _load_ruleset_data(project_root, source_assay_key)
    source_fields, source_column_mapping = _extract_fields_and_mapping(source_data)
    header = resolve_required_headers_from_source(source_fields, source_column_mapping)

    lot_rule = source_data.get("lot_rule")
    lot_rule = deepcopy(lot_rule) if isinstance(lot_rule, dict) else {"regex": ""}

    draft_dir = Path(project_root) / "rules" / "drafts"
    draft_dir.mkdir(parents=True, exist_ok=True)
    draft_path = draft_dir / f"{_safe_key(new_assay_key)}.draft.json"

    data: Dict[str, Any] = {
        "assay_name": new_assay_name,
        "assay_key": new_assay_key,
        "lot_rule": lot_rule,
        "extract_rules": {"fields": header["fields"], "dedupe_fields": []},
        "excel_rules": {
            "excel_filename_template": "{assay_name}.xlsx",
            "sheetname_template": "{lot_id}",
            "column_mapping": header["column_mapping"],
        },
    }
    _write_json_atomic(draft_path, data)
    return draft_path


def adopt_candidate_fields(
    project_root: str,
    draft_path: str,
    candidate_source: Dict[str, Any],
    field_keys: List[str] | None = None,
    overwrite: bool = False,
) -> Dict[str, Any]:
    path = Path(draft_path)
    data = _read_json_object(path)
    extract_rules = data.setdefault("extract_rules", {})
    fields = extract_rules.get("fields")
    if not isinstance(fields, list):
        fields = []
        extract_rules["fields"] = fields

    existing_keys = {
        str(field.get("key", "")).strip()
        for field in fields
        if isinstance(field, dict) and str(field.get("key", "")).strip()
    }

    bundle = read_candidate_fields(project_root, **bundle_kwargs_from_source(candidate_source))
    full_bundle = _load_source_bundle(project_root, candidate_source)
    source_fields = bundle["fields"]

    wanted_keys: set[str] | None = None
    if field_keys is not None:
        wanted_keys = {str(key).strip() for key in field_keys if str(key).strip()}
        source_fields = [
            field
            for field in source_fields
            if str(field.get("key", "")).strip() in wanted_keys
        ]

    adopted: List[str] = []
    skipped_existing: List[str] = []
    missing: List[str] = []
    if wanted_keys is not None:
        found_keys = {str(field.get("key", "")).strip() for field in source_fields}
        missing = sorted(key for key in wanted_keys if key not in found_keys)

    col_map = data.setdefault("excel_rules", {}).setdefault("column_mapping", {})
    if not isinstance(col_map, dict):
        col_map = {}
        data["excel_rules"]["column_mapping"] = col_map

    for source_field in source_fields:
        key = str(source_field.get("key", "")).strip()
        if not key:
            continue
        if key in existing_keys:
            if overwrite:
                fields[:] = [
                    field
                    for field in fields
                    if not (isinstance(field, dict) and str(field.get("key", "")).strip() == key)
                ]
            else:
                skipped_existing.append(key)
                continue

        row = deepcopy(source_field)
        row["key"] = key
        row["required"] = bool(source_field.get("required", False))
        if isinstance(source_field.get("search_from"), dict):
            row["search_from"] = deepcopy(source_field["search_from"])
        else:
            row.pop("search_from", None)
        fields.append(row)
        existing_keys.add(key)

        if key in full_bundle["column_mapping"]:
            col_map[key] = full_bundle["column_mapping"][key]
        elif key not in col_map:
            col_map[key] = key
        adopted.append(key)

    _write_json_atomic(path, data)
    return {
        "adopted": adopted,
        "skipped_existing": skipped_existing,
        "missing": missing,
        "draft_path": str(path),
        "source": bundle["source"],
    }
