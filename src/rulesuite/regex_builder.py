"""Backend builder for regexes assembled from simple authoring fields."""
from __future__ import annotations

import re
from typing import Any, Dict, List

_VALUE_PATTERNS = {
    "text": r"(.+?)",
    "token": r"(\S+)",
    "decimal": r"(\d+(?:[\.,]\d+)?)",
    "range": r"(\d+(?:[\.,]\d+)?\s*-\s*\d+(?:[\.,]\d+)?)",
    "value_with_unit": r"(\d+(?:[\.,]\d+)?\s*[A-Za-z/%]+(?:/[A-Za-z]+)?)",
    "asy_filename": r"([^\\/]+\.asy)",
    "validation_status": r"(Validationskriterien\s+(?:nicht\s+)?erf(?:ü|ue)llt)",
}

_ANCHOR_TOKENS = {
    "S1",
    "S2",
    "S3",
    "S4",
    "S5",
    "S6",
    "PCQ1",
    "PCQ2",
    "NCQ1",
    "NCQ2",
}


def build_regex_from_builder_spec(spec: Dict[str, Any]) -> Dict[str, Any]:
    """Build a normal extraction regex from optional authoring fields.

    The returned regex is intended for the existing extractor. The builder spec
    itself is not runtime state and is not meant to be stored in rules JSON.
    """
    warnings: List[str] = []
    value_type = str(spec.get("value_type") or "auto").strip() or "auto"
    expected_value = str(spec.get("expected_value") or "").strip()
    capture, capture_type = _capture_for_value(value_type, expected_value, spec, warnings)

    prefix = _line_prefix(spec, warnings)
    left = _left_boundary(spec, warnings)
    right = _right_boundary(spec, warnings)
    regex = prefix + left + capture + right

    proposed_search_from = _proposed_search_from(spec, warnings)

    if not prefix and not left and not right:
        warnings.append("no_context")

    return {
        "regex": regex,
        "capture": capture,
        "value_type": capture_type,
        "warnings": warnings,
        "proposed_search_from": proposed_search_from,
    }


def suggest_builder_spec_from_selection(
    line_text: str,
    selected_text: str,
    selection_start: int | None = None,
    selection_end: int | None = None,
    *,
    line_index: int | None = None,
) -> Dict[str, Any]:
    selected = selected_text.strip()
    start, end = _resolve_selection_span(line_text, selected_text, selection_start, selection_end)
    spec: Dict[str, Any] = {
        "expected_value": selected,
        "value_type": _infer_value_type(selected),
        "line_contains": "",
        "line_contains_is_regex": False,
        "line_startswith": "",
        "line_startswith_is_regex": False,
        "left_marker": "",
        "left_marker_occurrence": "",
        "left_marker_is_regex": False,
        "right_marker": "",
        "right_marker_occurrence": "",
        "right_marker_is_regex": False,
        "match_index": "",
    }
    if line_index is not None and line_index >= 0:
        spec["line_index"] = str(line_index)

    if start is None or end is None:
        return {"spec": spec, "warnings": ["selection_not_found_in_line"]}

    anchor = _find_line_anchor(line_text[:start])
    if anchor:
        spec["line_contains"] = anchor

    left_marker = _nearest_left_marker(line_text[:start])
    right_marker = _nearest_right_marker(line_text[end:])
    if left_marker:
        spec["left_marker"] = left_marker
        spec["left_marker_occurrence"] = str(_count_literal_occurrences(line_text[:start], left_marker))
    if right_marker:
        spec["right_marker"] = right_marker
        right_count_before = _count_literal_occurrences(line_text[:start], right_marker)
        spec["right_marker_occurrence"] = str(right_count_before + 1)

    return {"spec": spec, "warnings": []}


def _capture_for_value(
    value_type: str,
    expected_value: str,
    spec: Dict[str, Any],
    warnings: List[str],
) -> tuple[str, str]:
    selected_type = _infer_value_type(expected_value) if value_type == "auto" else value_type
    capture = _VALUE_PATTERNS.get(selected_type, _VALUE_PATTERNS["text"])

    min_len = _positive_int(spec.get("value_min_len"))
    max_len = _positive_int(spec.get("value_max_len"))
    if min_len is None and max_len is None:
        return capture, selected_type
    if min_len is not None and max_len is not None and min_len > max_len:
        warnings.append("value_length_range_invalid")
        return capture, selected_type

    quantifier = _length_quantifier(min_len, max_len)
    if selected_type == "decimal":
        return rf"(?<![\d.,])((?=[\d.,]{quantifier}(?![\d.,]))\d+(?:[\.,]\d+)?)(?![\d.,])", selected_type
    if selected_type == "token":
        return rf"(?<!\S)(\S{quantifier})(?!\S)", selected_type
    if selected_type == "text":
        if not str(spec.get("left_marker") or "").strip() and not str(spec.get("right_marker") or "").strip():
            warnings.append("value_length_text_without_marker")
        return rf"(.{quantifier}?)", selected_type

    warnings.append("length_ignored_for_value_type")
    return capture, selected_type


def _proposed_search_from(spec: Dict[str, Any], warnings: List[str]) -> dict[str, object] | None:
    mode = str(spec.get("search_anchor_mode") or "").strip()
    if mode == "after":
        marker = str(spec.get("search_anchor") or "").strip()
        if not marker:
            warnings.append("search_anchor_missing")
            return None
        if bool(spec.get("search_anchor_is_regex")):
            return {"after": marker}
        return {"after": re.escape(marker)}
    if mode == "line":
        return _line_search_from(spec, warnings)
    if mode == "none":
        return None

    return _line_search_from(spec, warnings)


def _line_search_from(spec: Dict[str, Any], warnings: List[str]) -> dict[str, object] | None:
    line_index_raw = str(spec.get("line_index") or "").strip()
    if not line_index_raw:
        return None
    try:
        line_index = int(line_index_raw)
    except ValueError:
        warnings.append("line_index_invalid")
        return None
    if line_index < 0:
        warnings.append("line_index_negative")
        return None
    warnings.append("line_index_unstable_hint")
    return {"line": line_index}


def _length_quantifier(min_len: int | None, max_len: int | None) -> str:
    if min_len is not None and max_len is not None:
        return "{" + str(min_len) + "," + str(max_len) + "}"
    if min_len is not None:
        return "{" + str(min_len) + ",}"
    return "{1," + str(max_len) + "}"


def _infer_value_type(value: str) -> str:
    if re.fullmatch(r"\d+(?:[\.,]\d+)?\s*-\s*\d+(?:[\.,]\d+)?", value):
        return "range"
    if re.fullmatch(r"\d+(?:[\.,]\d+)?", value):
        return "decimal"
    if re.fullmatch(r"\d+(?:[\.,]\d+)?\s*[A-Za-z/%]+(?:/[A-Za-z]+)?", value):
        return "value_with_unit"
    if re.fullmatch(r"[^\\/]+\.asy", value, flags=re.IGNORECASE):
        return "asy_filename"
    if re.fullmatch(r"Validationskriterien\s+(?:nicht\s+)?erf(?:ü|ue)llt", value, flags=re.IGNORECASE):
        return "validation_status"
    if re.fullmatch(r"\S+", value):
        return "token"
    return "text"


def _line_prefix(spec: Dict[str, Any], warnings: List[str]) -> str:
    line_startswith = str(spec.get("line_startswith") or "").strip()
    if line_startswith:
        marker = _marker_regex(line_startswith, bool(spec.get("line_startswith_is_regex")))
        return rf"(?:^|\n){marker}[^\n]*?"

    line_contains = str(spec.get("line_contains") or "").strip()
    if line_contains:
        marker = _marker_regex(line_contains, bool(spec.get("line_contains_is_regex")))
        return marker + r"[^\n]*?"

    if str(spec.get("line_index") or "").strip():
        warnings.append("line_index_used_as_search_from_only")
    return ""


def _left_boundary(spec: Dict[str, Any], warnings: List[str]) -> str:
    marker = str(spec.get("left_marker") or "").strip()
    if not marker:
        return ""
    occurrence = _positive_int(spec.get("left_marker_occurrence"))
    if occurrence is None:
        occurrence = 1
        warnings.append("left_marker_occurrence_defaulted")
    marker_regex = _marker_regex(marker, bool(spec.get("left_marker_is_regex")))
    if occurrence <= 1:
        return marker_regex + r"\s*"
    return rf"(?:[^\n]*?{marker_regex})" + "{" + str(occurrence) + r"}\s*"


def _right_boundary(spec: Dict[str, Any], warnings: List[str]) -> str:
    marker = str(spec.get("right_marker") or "").strip()
    if not marker:
        return ""
    occurrence = _positive_int(spec.get("right_marker_occurrence"))
    if occurrence is None:
        occurrence = 1
        warnings.append("right_marker_occurrence_defaulted")

    left_marker = str(spec.get("left_marker") or "").strip()
    left_occurrence = _positive_int(spec.get("left_marker_occurrence"))
    remaining_occurrence = occurrence
    if left_marker and left_marker == marker and left_occurrence is not None:
        remaining_occurrence = max(1, occurrence - left_occurrence)

    marker_regex = _marker_regex(marker, bool(spec.get("right_marker_is_regex")))
    if remaining_occurrence <= 1:
        return r"\s*" + marker_regex
    return r"\s*" + rf"(?:[^\n]*?{marker_regex})" + "{" + str(remaining_occurrence) + "}"


def _marker_regex(marker: str, is_regex: bool) -> str:
    if is_regex:
        return marker
    escaped = re.escape(marker)
    if re.fullmatch(r"[A-Za-z0-9_]+", marker):
        return rf"\b{escaped}\b"
    return escaped


def _positive_int(value: object) -> int | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = int(raw)
    except ValueError:
        return None
    return parsed if parsed > 0 else None


def _resolve_selection_span(
    line_text: str,
    selected_text: str,
    selection_start: int | None,
    selection_end: int | None,
) -> tuple[int | None, int | None]:
    if selection_start is not None and selection_end is not None:
        if 0 <= selection_start <= selection_end <= len(line_text):
            return selection_start, selection_end
    idx = line_text.find(selected_text)
    if idx >= 0:
        return idx, idx + len(selected_text)
    selected = selected_text.strip()
    idx = line_text.find(selected)
    if selected and idx >= 0:
        return idx, idx + len(selected)
    return None, None


def _find_line_anchor(left_text: str) -> str:
    tokens = left_text.split()
    for token in reversed(tokens):
        clean = token.strip()
        if clean in _ANCHOR_TOKENS:
            return clean
        if clean.endswith(":"):
            return clean
    return ""


def _nearest_left_marker(left_text: str) -> str:
    for marker in ("ng/ml", "IU/ml", "RU/ml", "U/ml", "O.D."):
        if marker in left_text:
            return marker
    return ""


def _nearest_right_marker(right_text: str) -> str:
    stripped = right_text.lstrip()
    for marker in ("ng/ml", "IU/ml", "RU/ml", "U/ml", "O.D."):
        if stripped.startswith(marker):
            return marker
    return ""


def _count_literal_occurrences(text: str, marker: str) -> int:
    if not marker:
        return 0
    return text.count(marker)
