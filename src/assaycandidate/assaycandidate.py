from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Mapping

TEST_LINE_RE = re.compile(
    r"^Test:\s*(?:.+[\\/])?([^\\/]+\.asy)\s*\(([0-9a-fA-F]{4})\)",
    re.IGNORECASE,
)
VALIDATION_CONTEXT_RE = re.compile(
    r"Validationskriterien\s+(?:nicht\s+)?erf[uü]llt",
    re.IGNORECASE,
)


def find_assay_candidates(text: str) -> list[dict[str, str]]:
    test_candidates: list[dict[str, str]] = []
    seen_keys: set[str] = set()

    for line_no, line in enumerate(text.splitlines(), start=1):
        match = TEST_LINE_RE.search(line.strip())
        if not match:
            continue
        test_file = match.group(1).strip()
        raw_hex = match.group(2)
        raw_assay_key = f"({raw_hex})"
        assay_key = f"({raw_hex.lower()})"
        if assay_key in seen_keys:
            continue
        seen_keys.add(assay_key)
        assay_name_hint = _assay_name_hint_from_file(test_file)
        test_candidates.append(
            {
                "candidate_id": assay_key,
                "assay_key": assay_key,
                "raw_assay_key": raw_assay_key,
                "test_file": test_file,
                "assay_name_hint": assay_name_hint,
                "line_no": str(line_no),
                "line_text": line.rstrip(),
                "reason": "test_line",
                "confidence": "high",
            }
        )

    if test_candidates:
        return test_candidates

    for line_no, line in enumerate(text.splitlines(), start=1):
        if not VALIDATION_CONTEXT_RE.search(line):
            continue
        test_candidates.append(
            {
                "candidate_id": f"{line_no}:validation_context",
                "assay_key": "",
                "raw_assay_key": "",
                "test_file": "",
                "assay_name_hint": "",
                "line_no": str(line_no),
                "line_text": line.rstrip(),
                "reason": "validation_context",
                "confidence": "medium",
            }
        )
    return test_candidates


def annotate_assay_candidates(
    candidates: list[Mapping[str, str]],
    known_keys: set[str] | None,
) -> list[dict[str, str]]:
    annotated: list[dict[str, str]] = []
    for candidate in candidates:
        row = dict(candidate)
        assay_key = str(row.get("assay_key", "") or "").strip()
        if known_keys is None or not assay_key:
            row["known_status"] = "unchecked"
        elif assay_key in known_keys:
            row["known_status"] = "known"
        else:
            row["known_status"] = "unknown"
        annotated.append(row)
    return annotated


def load_known_assay_keys(rules_index_path: str) -> set[str] | None:
    try:
        payload = json.loads(Path(rules_index_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    assays = payload.get("assays")
    if not isinstance(assays, list):
        return None
    keys: set[str] = set()
    for entry in assays:
        if not isinstance(entry, dict):
            continue
        raw_key = entry.get("assay_key")
        if not isinstance(raw_key, str) or not raw_key.strip():
            continue
        keys.add(canonical_assay_key(raw_key))
    return keys


def canonical_assay_key(raw: str) -> str:
    stripped = raw.strip()
    match = re.fullmatch(r"\(([0-9a-fA-F]{4})\)", stripped)
    if match:
        return f"({match.group(1).lower()})"
    return stripped.lower()


def _assay_name_hint_from_file(test_file: str) -> str:
    if test_file.lower().endswith(".asy"):
        return test_file[:-4]
    return test_file
