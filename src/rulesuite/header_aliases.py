"""Legacy-Header-Alias-Aufloesung fuer Ruleset-Quellen (guided similar-Modus)."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Tuple

from .required_fields import REQUIRED_HEADER_FIELD_KEYS

LEGACY_HEADER_ALIASES: Dict[str, str] = {
    "date": "DATUM",
    "time": "ZEIT",
    "user": "ANWENDER",
    "plate_name": "PLATTE",
    "lot_id": "CHARGE",
}

LEGACY_HEADER_ALIAS_KEYS = frozenset(LEGACY_HEADER_ALIASES.keys())

CANONICAL_TO_LEGACY: Dict[str, str] = {v: k for k, v in LEGACY_HEADER_ALIASES.items()}


def excluded_candidate_keys_for_ruleset_source() -> frozenset[str]:
    return frozenset(REQUIRED_HEADER_FIELD_KEYS) | LEGACY_HEADER_ALIAS_KEYS


def resolve_required_headers_from_source(
    source_fields: List[Dict[str, Any]],
    source_column_mapping: Dict[str, str],
) -> Dict[str, Any]:
    """Map source header fields to canonical REQUIRED_HEADER_FIELD_KEYS."""
    field_by_key: Dict[str, Dict[str, Any]] = {}
    for field in source_fields:
        if not isinstance(field, dict):
            continue
        key = str(field.get("key", "")).strip()
        if key:
            field_by_key[key] = field

    fields: List[Dict[str, Any]] = []
    column_mapping: Dict[str, str] = {}

    for canonical in REQUIRED_HEADER_FIELD_KEYS:
        source_key, field = _pick_source_header_field(canonical, field_by_key)
        if field is not None:
            copied = deepcopy(field)
            copied["key"] = canonical
            copied["required"] = True
            fields.append(copied)
            column_mapping[canonical] = _column_name_for_key(source_key or canonical, source_column_mapping, canonical)
        else:
            fields.append({"key": canonical, "regex": "", "required": True})
            column_mapping[canonical] = _column_name_for_key(canonical, source_column_mapping, canonical)

    return {"fields": fields, "column_mapping": column_mapping}


def _pick_source_header_field(
    canonical: str,
    field_by_key: Dict[str, Dict[str, Any]],
) -> Tuple[str | None, Dict[str, Any] | None]:
    if canonical in field_by_key:
        return canonical, field_by_key[canonical]
    legacy = CANONICAL_TO_LEGACY.get(canonical)
    if legacy and legacy in field_by_key:
        return legacy, field_by_key[legacy]
    return None, None


def _column_name_for_key(source_key: str, source_column_mapping: Dict[str, str], canonical: str) -> str:
    if source_key in source_column_mapping:
        return str(source_column_mapping[source_key])
    if canonical in source_column_mapping:
        return str(source_column_mapping[canonical])
    return canonical
