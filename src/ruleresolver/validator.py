from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple


class RulesIntegrityError(RuntimeError):
    pass


IGNORED_RULESET_FILES = {"template.json"}


def validate_rules_integrity(rules_dir: str, index_path: str) -> Dict[str, Any]:
    rules_root = Path(rules_dir)
    idx = _load_json_no_dupes(Path(index_path))
    assays = idx.get("assays", [])
    if not isinstance(assays, list):
        raise RulesIntegrityError("index.assays must be a list")

    mapped_files: Dict[str, str] = {}
    for row in assays:
        if not isinstance(row, dict):
            raise RulesIntegrityError("index.assays entries must be objects")
        key = str(row.get("assay_key", "")).strip()
        file_name = str(row.get("ruleset_file", "")).strip()
        if not key or not file_name:
            raise RulesIntegrityError("index entry requires assay_key + ruleset_file")
        if key in mapped_files:
            raise RulesIntegrityError(f"duplicate assay_key in index: {key}")
        mapped_files[key] = file_name

    missing_files: List[str] = []
    key_mismatches: List[Tuple[str, str]] = []
    duplicate_key_files: List[str] = []
    content_errors: List[Dict[str, Any]] = []
    from src.rulesuite.validation import _validate_draft_data

    for key, file_name in mapped_files.items():
        path = rules_root / file_name
        if not path.exists():
            missing_files.append(file_name)
            continue
        try:
            data = _load_json_no_dupes(path)
        except RulesIntegrityError:
            duplicate_key_files.append(file_name)
            continue
        if str(data.get("assay_key", "")).strip() != key:
            key_mismatches.append((key, file_name))
        check = _validate_draft_data(data)
        if not check["ok"]:
            content_errors.append({"ruleset_file": file_name, "errors": check["errors"]})

    indexed_names = set(mapped_files.values())
    orphan_files = sorted(
        p.name
        for p in rules_root.glob("*.json")
        if p.name != Path(index_path).name
        and p.name not in indexed_names
        and p.name not in IGNORED_RULESET_FILES
    )

    return {
        "missing_files": sorted(missing_files),
        "key_mismatches": [{"assay_key": k, "ruleset_file": f} for k, f in key_mismatches],
        "duplicate_json_key_files": sorted(duplicate_key_files),
        "content_errors": content_errors,
        "orphan_rulesets": orphan_files,
    }


def _load_json_no_dupes(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    dupes: List[str] = []

    def hook(pairs: List[Tuple[str, Any]]) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        seen: set[str] = set()
        for k, v in pairs:
            if k in seen:
                dupes.append(k)
            seen.add(k)
            out[k] = v
        return out

    data = json.loads(text, object_pairs_hook=hook)
    if dupes:
        raise RulesIntegrityError(f"duplicate_json_keys:{path.name}:{sorted(set(dupes))}")
    if not isinstance(data, dict):
        raise RulesIntegrityError(f"json_root_not_object:{path.name}")
    return data
