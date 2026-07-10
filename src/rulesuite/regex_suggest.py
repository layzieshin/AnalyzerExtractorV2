"""Deterministic regex suggestions from an assay-text selection."""
from __future__ import annotations

import re
from typing import Any, Dict, List

_FIELD_ANCHORS = {
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

_LABEL_ANCHORS = {
    "Kit",
    "Datum:",
    "Zeit:",
    "Anwender:",
    "Plattenname:",
    "Test:",
}


def suggest_regex_from_selection(
    line_text: str,
    selected_text: str,
    selection_start: int | None = None,
    selection_end: int | None = None,
) -> Dict[str, Any]:
    selected = selected_text.strip()
    warnings: List[str] = []
    start, end = _resolve_selection_span(line_text, selected_text, selection_start, selection_end)
    capture, strategy = _capture_for_selection(selected)

    if start is None or end is None:
        warnings.append("selection_not_found_in_line")
        return {
            "regex": capture,
            "capture": capture,
            "strategy": strategy,
            "warnings": warnings,
        }

    left = line_text[:start]
    right = line_text[end:]
    if strategy == "asy_filename":
        left_regex, left_strategy = _asy_left_context_regex(left)
    else:
        left_regex, left_strategy = _left_context_regex(left)
    right_regex, right_strategy = _right_context_regex(right)
    if left_strategy:
        strategy = f"{left_strategy}+{strategy}"
    if right_strategy:
        strategy = f"{strategy}+{right_strategy}"

    return {
        "regex": left_regex + capture + right_regex,
        "capture": capture,
        "strategy": strategy,
        "warnings": warnings,
    }


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


def _capture_for_selection(selected: str) -> tuple[str, str]:
    if not selected:
        return r"(\S+)", "empty_fallback"
    if re.fullmatch(r"[<>]=?\s*\d+(?:[\.,]\d+)?", selected):
        return r"([<>]=?\s*\d+(?:[\.,]\d+)?)", "threshold"
    if re.fullmatch(r"\d+(?:[\.,]\d+)?\s*-\s*\d+(?:[\.,]\d+)?", selected):
        return r"(\d+(?:[\.,]\d+)?\s*-\s*\d+(?:[\.,]\d+)?)", "range"
    if re.fullmatch(r"\d{1,2}\.\d{1,2}\.\d{4}", selected):
        return r"(\d{1,2}\.\d{1,2}\.\d{4})", "date"
    if re.fullmatch(r"\d{1,2}:\d{2}(?::\d{2})?", selected):
        return r"(\d{1,2}:\d{2}(?::\d{2})?)", "time"
    if re.fullmatch(r"\d+(?:[\.,]\d+)?", selected):
        return r"(\d+(?:[\.,]\d+)?)", "decimal"
    if re.fullmatch(r"[^\\/]+\.asy", selected, flags=re.IGNORECASE):
        return r"([^\\/]+\.asy)", "asy_filename"
    if re.fullmatch(r"\d+(?:[\.,]\d+)?\s*[A-Za-z/%]+(?:/[A-Za-z]+)?", selected):
        return r"(\d+(?:[\.,]\d+)?\s*[A-Za-z/%]+(?:/[A-Za-z]+)?)", "value_with_unit"
    if re.fullmatch(r"[\w.\-/]+", selected):
        return r"(\S+)", "token"
    return f"({re.escape(selected)})", "literal_capture"


def _left_context_regex(left: str) -> tuple[str, str]:
    tokens = left.split()
    if not tokens:
        return "", ""

    anchor_idx = _last_anchor_index(tokens)
    if anchor_idx is None:
        anchor_idx = max(0, len(tokens) - 3)
        strategy = "left_window"
    else:
        strategy = "anchored_left"

    selected_tokens = tokens[anchor_idx:]
    parts: List[str] = []
    for token in selected_tokens:
        parts.append(_left_token_regex(token))
    return r"\s+".join(parts) + r"\s+", strategy


def _asy_left_context_regex(left: str) -> tuple[str, str]:
    if "Test:" in left:
        return r"Test:.*[\\/]", "test_path_left"
    if "\\" in left or "/" in left:
        return r".*[\\/]", "path_left"
    return _left_context_regex(left)


def _last_anchor_index(tokens: list[str]) -> int | None:
    for idx in range(len(tokens) - 1, -1, -1):
        token = tokens[idx]
        if token in _FIELD_ANCHORS or token in _LABEL_ANCHORS:
            return idx
    return None


def _left_token_regex(token: str) -> str:
    if token in _FIELD_ANCHORS:
        return rf"\b{re.escape(token)}"
    if token in _LABEL_ANCHORS:
        return re.escape(token)
    if re.fullmatch(r"\d{6}", token):
        return r"\d{6}"
    if re.fullmatch(r"\d{7,}", token):
        return r"\S+"
    if re.fullmatch(r"[A-Za-z]\d{6,}[A-Za-z]?", token):
        return r"\S+"
    return re.escape(token)


def _right_context_regex(right: str) -> tuple[str, str]:
    stripped = right.lstrip()
    if not stripped:
        return "", ""
    leading_ws = r"\s+" if right[: len(right) - len(stripped)] else ""

    unit_match = re.match(r"(O\.D\.|ng/ml|IU/ml|U/ml)", stripped, flags=re.IGNORECASE)
    if unit_match:
        return leading_ws + re.escape(unit_match.group(1)), "unit_right"

    return "", ""
