"""Regex-Werkzeuge der RuleSuite: Einzeltest, Batch-Check und Feld-Lokalisierung.

Alle Funktionen sind zustandslos und arbeiten auf bereits geladenen Daten
(Text + Feldliste); Draft-IO bleibt in der RuleSuite-Fassade.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List


def test_regex(
    text: str,
    regex: str,
    group: int = 1,
    search_from: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    lines = text.splitlines()
    search_text = text
    slice_offset = 0
    if search_from is not None:
        search_text, slice_offset, slice_error = _resolve_search_slice(text, lines, search_from)
        if slice_error:
            return {
                "matched": False,
                "value": None,
                "span": None,
                "context_snippet": "",
                "error": slice_error,
            }

    try:
        pattern = re.compile(regex)
    except re.error as e:
        return {
            "matched": False,
            "value": None,
            "span": None,
            "context_snippet": "",
            "error": f"invalid_regex: {e}",
        }

    m = pattern.search(search_text)
    if not m:
        return {
            "matched": False,
            "value": None,
            "span": None,
            "context_snippet": "",
            "error": None,
        }

    if group == 0:
        local_span = m.span(0)
        value = m.group(0)
    else:
        if group > (m.lastindex or 0):
            return {
                "matched": False,
                "value": None,
                "span": None,
                "context_snippet": "",
                "error": f"group_out_of_range: {group}",
            }
        local_span = m.span(group)
        value = m.group(group)

    span = [local_span[0] + slice_offset, local_span[1] + slice_offset]
    left = max(0, span[0] - 120)
    right = min(len(text), span[1] + 120)
    return {
        "matched": True,
        "value": value,
        "span": span,
        "context_snippet": text[left:right],
        "error": None,
    }


def batch_check_fields(fields: List[Any], assay_text: str, group: int = 1) -> Dict[str, Any]:
    results: List[Dict[str, Any]] = []
    hits = 0
    errors = 0
    for f in fields:
        if not isinstance(f, dict):
            continue
        key = str(f.get("key", "")).strip()
        regex = str(f.get("regex", "")).strip()
        required = bool(f.get("required", False))
        if not key or not regex:
            continue
        res = test_regex(assay_text, regex, group=group)
        if res.get("matched"):
            hits += 1
        if res.get("error"):
            errors += 1
        results.append(
            {
                "key": key,
                "required": required,
                "matched": bool(res.get("matched")),
                "value": res.get("value"),
                "error": res.get("error"),
            }
        )

    return {
        "total_fields": len(results),
        "hits": hits,
        "misses": len(results) - hits,
        "errors": errors,
        "results": results,
    }


def locate_fields(fields: List[Any], assay_text: str, group: int = 1) -> Dict[str, Any]:
    """Locate each field in assay_text, honoring search_from like the Extractor."""
    lines = assay_text.splitlines()
    results: List[Dict[str, Any]] = []
    hits = 0
    errors = 0

    for f in fields:
        if not isinstance(f, dict):
            continue
        key = str(f.get("key", "")).strip()
        regex = str(f.get("regex", "")).strip()
        required = bool(f.get("required", False))
        search_from = f.get("search_from") if isinstance(f.get("search_from"), dict) else None

        if not key or not regex:
            continue

        search_text, slice_offset, slice_error = _resolve_search_slice(assay_text, lines, search_from)
        if slice_error:
            errors += 1
            results.append(
                {
                    "key": key,
                    "regex": regex,
                    "required": required,
                    "search_from": search_from,
                    "matched": False,
                    "span": None,
                    "value": None,
                    "error": slice_error,
                }
            )
            continue

        try:
            pattern = re.compile(regex)
        except re.error as e:
            errors += 1
            results.append(
                {
                    "key": key,
                    "regex": regex,
                    "required": required,
                    "search_from": search_from,
                    "matched": False,
                    "span": None,
                    "value": None,
                    "error": f"invalid_regex: {e}",
                }
            )
            continue

        m = pattern.search(search_text)
        if not m:
            results.append(
                {
                    "key": key,
                    "regex": regex,
                    "required": required,
                    "search_from": search_from,
                    "matched": False,
                    "span": None,
                    "value": None,
                    "error": None,
                }
            )
            continue

        if group == 0:
            local_span = m.span(0)
            value = m.group(0)
        else:
            if group > (m.lastindex or 0):
                errors += 1
                results.append(
                    {
                        "key": key,
                        "regex": regex,
                        "required": required,
                        "search_from": search_from,
                        "matched": False,
                        "span": None,
                        "value": None,
                        "error": f"group_out_of_range: {group}",
                    }
                )
                continue
            local_span = m.span(group)
            value = m.group(group)

        full_span = [local_span[0] + slice_offset, local_span[1] + slice_offset]
        hits += 1
        results.append(
            {
                "key": key,
                "regex": regex,
                "required": required,
                "search_from": search_from,
                "matched": True,
                "span": full_span,
                "value": value.strip() if isinstance(value, str) else value,
                "error": None,
            }
        )

    return {
        "total_fields": len(results),
        "hits": hits,
        "misses": len(results) - hits,
        "errors": errors,
        "results": results,
    }


def _char_offset_for_line_start(lines: List[str], line_idx: int) -> int:
    if line_idx <= 0:
        return 0
    offset = 0
    for i in range(line_idx):
        offset += len(lines[i]) + 1
    return offset


def _resolve_search_slice(
    full_text: str,
    lines: List[str],
    search_from: Dict[str, Any] | None,
) -> tuple[str, int, str | None]:
    """Return (search_text, char_offset_in_full_text, error)."""
    if not isinstance(search_from, dict):
        return full_text, 0, None

    if "after" in search_from:
        marker = search_from["after"]
        try:
            for i, ln in enumerate(lines):
                if re.search(marker, ln):
                    start_line = i + 1
                    search_text = "\n".join(lines[start_line:])
                    return search_text, _char_offset_for_line_start(lines, start_line), None
        except re.error as e:
            return full_text, 0, f"search_from.after invalid regex: {e}"
        return full_text, 0, None

    if "line" in search_from:
        try:
            start = int(search_from["line"])
        except Exception:
            return full_text, 0, "search_from.line invalid int"
        if start < 0:
            return full_text, 0, "search_from.line must be >= 0"
        search_text = "\n".join(lines[start:])
        return search_text, _char_offset_for_line_start(lines, start), None

    return full_text, 0, None
