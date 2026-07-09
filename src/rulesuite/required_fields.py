"""Pflichtfeld-Vertrag und strukturelle Prüfung für neue Assay-Drafts."""
from __future__ import annotations

from typing import Any, Dict, List

from pathlib import Path

from .json_io import _read_json_object
from .regex_tools import locate_fields

REQUIRED_HEADER_FIELD_KEYS = (
    "DATUM",
    "ZEIT",
    "ANWENDER",
    "PLATTE",
    "CHARGE",
    "VALIDATION",
)


def check_required_fields(draft_path: str, assay_text: str, group: int = 1) -> Dict[str, Any]:
    """Prüft den Pflichtfeld-Vertrag gegen vorhandene Draft-Regeln (keine Regex-Erzeugung)."""
    data = _read_json_object(Path(draft_path))
    extract_rules = data.get("extract_rules")
    raw_fields = extract_rules.get("fields", []) if isinstance(extract_rules, dict) else []
    if not isinstance(raw_fields, list):
        raw_fields = []

    field_by_key: Dict[str, Dict[str, Any]] = {}
    for field in raw_fields:
        if not isinstance(field, dict):
            continue
        key = str(field.get("key", "")).strip()
        if key:
            field_by_key[key] = field

    located: Dict[str, Dict[str, Any]] = {}
    if assay_text.strip():
        loc = locate_fields(list(field_by_key.values()), assay_text, group=group)
        for row in loc.get("results", []):
            if isinstance(row, dict) and row.get("key"):
                located[str(row["key"])] = row

    results: List[Dict[str, Any]] = []
    for key in REQUIRED_HEADER_FIELD_KEYS:
        field = field_by_key.get(key)
        if field is None:
            results.append(_result_row(key, required=True, status="missing_field"))
            continue

        regex = str(field.get("regex", "")).strip()
        search_from = field.get("search_from") if isinstance(field.get("search_from"), dict) else None
        has_regex = bool(regex)
        if not has_regex:
            results.append(
                _result_row(
                    key,
                    required=True,
                    status="missing_regex",
                    has_regex=False,
                    search_from=search_from,
                )
            )
            continue

        row = located.get(key)
        if row is None:
            results.append(
                _result_row(
                    key,
                    required=True,
                    status="miss",
                    has_regex=True,
                    search_from=search_from,
                )
            )
            continue

        if row.get("error"):
            results.append(
                _result_row(
                    key,
                    required=True,
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
                    required=True,
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
                    required=True,
                    status="miss",
                    has_regex=True,
                    matched=False,
                    search_from=search_from,
                )
            )

    confirmed = sum(1 for row in results if row["status"] == "confirmed")
    return {
        "required_keys": list(REQUIRED_HEADER_FIELD_KEYS),
        "total": len(REQUIRED_HEADER_FIELD_KEYS),
        "confirmed": confirmed,
        "all_confirmed": confirmed == len(REQUIRED_HEADER_FIELD_KEYS),
        "results": results,
    }


def _result_row(
    key: str,
    *,
    required: bool,
    status: str,
    has_regex: bool = False,
    matched: bool = False,
    value: Any = None,
    span: Any = None,
    error: Any = None,
    search_from: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    return {
        "key": key,
        "required": required,
        "has_regex": has_regex,
        "matched": matched,
        "value": value,
        "span": span,
        "error": error,
        "search_from": search_from,
        "status": status,
    }
