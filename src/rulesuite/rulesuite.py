"""RuleSuite-Fassade: Draft-Lifecycle, Feld-/Meta-Mutationen, Preview und Aktivierung.

Die Fachlogik ist nach Verantwortlichkeit in Submodule aufgeteilt:
- json_io: atomares JSON-Schreiben, sichere Datei-/Key-Namen
- validation: Draft-Validierung (bewusst ohne ruleresolver-Import)
- regex_tools: Regex-Test, Batch-Check, Feld-Lokalisierung
- diffing: rekursiver Struktur-Diff
"""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List

from src.assaychooser.api import detect_assays
from src.contentsplitter.api import AssayDescriptor, split_by_assay_name_and_key
from src.extractor.api import extract_record
from src.normalizer.api import normalize_lines
from src.parser.api import parse
from src.ruleresolver.api import RuleSet, resolve_ruleset

from . import regex_tools
from .diffing import collect_diffs
from .errors import RuleSuiteError
from .json_io import _read_json_object, _safe_filename, _safe_key, _write_json_atomic
from .validation import _validate_draft_data

__all__ = ["RuleSuite", "RuleSuiteError", "_validate_draft_data"]


class RuleSuite:
    def create_draft(self, project_root: str, assay_key: str) -> Path:
        root = Path(project_root)
        index_path = root / "rules" / "index.json"
        ruleset = resolve_ruleset(assay_key, str(root / "rules"), str(index_path))

        draft_dir = root / "rules" / "drafts"
        draft_dir.mkdir(parents=True, exist_ok=True)
        draft_path = draft_dir / f"{_safe_key(assay_key)}.draft.json"
        _write_json_atomic(draft_path, ruleset.data)
        return draft_path

    def create_blank_draft(self, project_root: str, assay_key: str, assay_name: str) -> Path:
        assay_key = assay_key.strip()
        assay_name = assay_name.strip()
        if not assay_key or not assay_name:
            raise RuleSuiteError("assay_key and assay_name are required")

        root = Path(project_root)
        draft_dir = root / "rules" / "drafts"
        draft_dir.mkdir(parents=True, exist_ok=True)
        draft_path = draft_dir / f"{_safe_key(assay_key)}.draft.json"

        data: Dict[str, Any] = {
            "assay_name": assay_name,
            "assay_key": assay_key,
            "lot_rule": {"regex": ""},
            "extract_rules": {"fields": [], "dedupe_fields": []},
            "excel_rules": {
                "excel_filename_template": "{assay_name}.xlsx",
                "sheetname_template": "{lot_id}",
                "column_mapping": {},
            },
        }
        _write_json_atomic(draft_path, data)
        return draft_path

    def derive_draft(
        self,
        project_root: str,
        source_assay_key: str,
        new_assay_key: str,
        new_assay_name: str,
    ) -> Path:
        new_assay_key = new_assay_key.strip()
        new_assay_name = new_assay_name.strip()
        if not new_assay_key or not new_assay_name:
            raise RuleSuiteError("new_assay_key and new_assay_name are required")

        root = Path(project_root)
        source = resolve_ruleset(source_assay_key, str(root / "rules"), str(root / "rules" / "index.json"))
        data = deepcopy(source.data)
        data["assay_key"] = new_assay_key
        data["assay_name"] = new_assay_name
        data.setdefault("excel_rules", {})["excel_filename_template"] = "{assay_name}.xlsx"

        draft_dir = root / "rules" / "drafts"
        draft_dir.mkdir(parents=True, exist_ok=True)
        draft_path = draft_dir / f"{_safe_key(new_assay_key)}.draft.json"
        _write_json_atomic(draft_path, data)
        return draft_path

    def load_draft(self, draft_path: str) -> Dict[str, Any]:
        path = Path(draft_path)
        if not path.exists():
            raise RuleSuiteError(f"draft_not_found: {path}")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            raise RuleSuiteError(f"draft_parse_failed: {e}") from e
        if not isinstance(data, dict):
            raise RuleSuiteError("draft_root_not_object")
        return data

    def save_draft(self, draft_path: str, data: Dict[str, Any]) -> Path:
        path = Path(draft_path)
        if not isinstance(data, dict):
            raise RuleSuiteError("draft_data_must_be_object")
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_json_atomic(path, data)
        return path

    def set_field_regex(self, draft_path: str, field_key: str, regex: str) -> Path:
        return self.update_field(draft_path, field_key=field_key, regex=regex)

    def add_field(
        self,
        draft_path: str,
        key: str,
        regex: str,
        required: bool = False,
        search_from: Dict[str, Any] | None = None,
    ) -> Path:
        key = key.strip()
        if not key:
            raise RuleSuiteError("field key required")
        data = self.load_draft(draft_path)
        fields = _ensure_fields(data)
        if any(str(f.get("key", "")).strip() == key for f in fields):
            raise RuleSuiteError(f"field_exists: {key}")

        row: Dict[str, Any] = {"key": key, "regex": regex, "required": bool(required)}
        if search_from is not None:
            row["search_from"] = search_from
        fields.append(row)
        return self.save_draft(draft_path, data)

    def remove_field(self, draft_path: str, field_key: str) -> Path:
        data = self.load_draft(draft_path)
        fields = _ensure_fields(data)
        out = [f for f in fields if str(f.get("key", "")).strip() != field_key]
        if len(out) == len(fields):
            raise RuleSuiteError(f"field_not_found: {field_key}")
        data.setdefault("extract_rules", {})["fields"] = out

        col_map = data.setdefault("excel_rules", {}).setdefault("column_mapping", {})
        if isinstance(col_map, dict):
            col_map.pop(field_key, None)

        dedupe = data.setdefault("extract_rules", {}).get("dedupe_fields")
        if isinstance(dedupe, list):
            data["extract_rules"]["dedupe_fields"] = [str(k) for k in dedupe if str(k) != field_key]

        return self.save_draft(draft_path, data)

    def rename_field(self, draft_path: str, old_key: str, new_key: str) -> Path:
        new_key = new_key.strip()
        if not new_key:
            raise RuleSuiteError("new_key required")

        data = self.load_draft(draft_path)
        fields = _ensure_fields(data)

        if any(str(f.get("key", "")).strip() == new_key for f in fields):
            raise RuleSuiteError(f"field_exists: {new_key}")

        found = False
        for f in fields:
            if str(f.get("key", "")).strip() == old_key:
                f["key"] = new_key
                found = True
                break
        if not found:
            raise RuleSuiteError(f"field_not_found: {old_key}")

        col_map = data.setdefault("excel_rules", {}).setdefault("column_mapping", {})
        if isinstance(col_map, dict) and old_key in col_map:
            col_map[new_key] = col_map.pop(old_key)

        dedupe = data.setdefault("extract_rules", {}).get("dedupe_fields")
        if isinstance(dedupe, list):
            data["extract_rules"]["dedupe_fields"] = [new_key if str(k) == old_key else str(k) for k in dedupe]

        return self.save_draft(draft_path, data)

    def duplicate_field(self, draft_path: str, source_key: str, new_key: str) -> Path:
        new_key = new_key.strip()
        if not new_key:
            raise RuleSuiteError("new_key required")

        data = self.load_draft(draft_path)
        fields = _ensure_fields(data)
        if any(str(f.get("key", "")).strip() == new_key for f in fields):
            raise RuleSuiteError(f"field_exists: {new_key}")

        source = next((f for f in fields if str(f.get("key", "")).strip() == source_key), None)
        if not isinstance(source, dict):
            raise RuleSuiteError(f"field_not_found: {source_key}")

        cloned = deepcopy(source)
        cloned["key"] = new_key
        fields.append(cloned)
        return self.save_draft(draft_path, data)

    def move_field(self, draft_path: str, field_key: str, direction: str) -> Path:
        if direction not in {"up", "down"}:
            raise RuleSuiteError("direction must be 'up' or 'down'")

        data = self.load_draft(draft_path)
        fields = _ensure_fields(data)
        idx = next((i for i, f in enumerate(fields) if str(f.get("key", "")).strip() == field_key), -1)
        if idx < 0:
            raise RuleSuiteError(f"field_not_found: {field_key}")

        if direction == "up":
            if idx == 0:
                return self.save_draft(draft_path, data)
            fields[idx - 1], fields[idx] = fields[idx], fields[idx - 1]
        else:
            if idx >= len(fields) - 1:
                return self.save_draft(draft_path, data)
            fields[idx + 1], fields[idx] = fields[idx], fields[idx + 1]
        return self.save_draft(draft_path, data)

    def update_field(
        self,
        draft_path: str,
        field_key: str,
        regex: str | None = None,
        required: bool | None = None,
        search_from: Dict[str, Any] | None = None,
    ) -> Path:
        data = self.load_draft(draft_path)
        fields = _ensure_fields(data)

        for f in fields:
            if str(f.get("key", "")).strip() != field_key:
                continue
            if regex is not None:
                f["regex"] = regex
            if required is not None:
                f["required"] = bool(required)
            if search_from is not None:
                if search_from:
                    f["search_from"] = search_from
                else:
                    f.pop("search_from", None)
            return self.save_draft(draft_path, data)

        raise RuleSuiteError(f"field_not_found: {field_key}")

    def set_lot_rule(self, draft_path: str, regex: str) -> Path:
        data = self.load_draft(draft_path)
        lot_rule = data.setdefault("lot_rule", {})
        if not isinstance(lot_rule, dict):
            raise RuleSuiteError("lot_rule must be object")
        lot_rule["regex"] = regex
        return self.save_draft(draft_path, data)

    def set_dedupe_fields(self, draft_path: str, fields: List[str]) -> Path:
        data = self.load_draft(draft_path)
        clean: List[str] = []
        seen: set[str] = set()
        for f in fields:
            key = str(f).strip()
            if key and key not in seen:
                clean.append(key)
                seen.add(key)
        data.setdefault("extract_rules", {})["dedupe_fields"] = clean
        return self.save_draft(draft_path, data)

    def set_excel_rules(
        self,
        draft_path: str,
        filename_template: str,
        sheet_template: str,
        column_mapping: Dict[str, str],
    ) -> Path:
        data = self.load_draft(draft_path)
        excel_rules = data.setdefault("excel_rules", {})
        if not isinstance(excel_rules, dict):
            raise RuleSuiteError("excel_rules must be object")
        excel_rules["excel_filename_template"] = filename_template
        excel_rules["sheetname_template"] = sheet_template
        excel_rules["column_mapping"] = dict(column_mapping)
        return self.save_draft(draft_path, data)

    def test_regex(
        self,
        text: str,
        regex: str,
        group: int = 1,
        search_from: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        return regex_tools.test_regex(text, regex, group=group, search_from=search_from)

    def batch_check_fields(self, draft_path: str, assay_text: str, group: int = 1) -> Dict[str, Any]:
        fields = self._load_fields_list(draft_path)
        return regex_tools.batch_check_fields(fields, assay_text, group=group)

    def locate_fields(self, draft_path: str, assay_text: str, group: int = 1) -> Dict[str, Any]:
        fields = self._load_fields_list(draft_path)
        return regex_tools.locate_fields(fields, assay_text, group=group)

    def diff_draft_vs_active(self, project_root: str, assay_key: str, draft_path: str) -> Dict[str, Any]:
        draft_data = self.load_draft(draft_path)
        root = Path(project_root)
        active_data: Dict[str, Any] | None = None
        ruleset_file: str | None = None
        mode = "update"
        try:
            rs = resolve_ruleset(assay_key, str(root / "rules"), str(root / "rules" / "index.json"))
            active_data = rs.data
            ruleset_file = rs.ruleset_file
        except Exception:
            mode = "create"

        if active_data is None:
            return {
                "mode": mode,
                "assay_key": assay_key,
                "ruleset_file": ruleset_file,
                "changes": [{"path": "$", "active": None, "draft": draft_data}],
            }

        changes: List[Dict[str, Any]] = []
        collect_diffs("$", active_data, draft_data, changes)
        return {
            "mode": mode,
            "assay_key": assay_key,
            "ruleset_file": ruleset_file,
            "changes": changes,
        }

    def get_assay_text(
        self,
        project_root: str,
        pdf_path: str,
        assay_key: str,
        assay_name: str,
        draft_path: str | None = None,
    ) -> Dict[str, Any]:
        root = Path(project_root)
        doc = parse(pdf_path)
        raw_lines = [ln for p in doc.pages for ln in p.lines]
        norm_lines = normalize_lines(raw_lines)
        norm_text = "\n".join(norm_lines)

        index_path = root / "rules" / "index.json"
        detected = [m.assay_key for m in detect_assays(norm_text, str(index_path))]

        use_assay_name = assay_name.strip()
        if draft_path:
            draft_data = self.load_draft(draft_path)
            use_assay_name = str(draft_data.get("assay_name", use_assay_name)).strip()

        if not use_assay_name:
            raise RuleSuiteError("assay_name is required")

        blocks = split_by_assay_name_and_key(norm_text, [AssayDescriptor(assay_key=assay_key, assay_name=use_assay_name)])
        assay_block = blocks.get(assay_key, "")
        if not assay_block:
            raise RuleSuiteError(f"assay_block_empty: {assay_key}")

        return {
            "pdf_path": pdf_path,
            "assay_key": assay_key,
            "assay_name": use_assay_name,
            "detected_assays": detected,
            "normalized_text": norm_text,
            "assay_block": assay_block,
        }

    def validate_draft(self, draft_path: str) -> Dict[str, Any]:
        data = self.load_draft(draft_path)
        return _validate_draft_data(data)

    def preview_extract(
        self,
        project_root: str,
        pdf_path: str,
        assay_key: str,
        draft_path: str | None = None,
    ) -> Dict[str, Any]:
        root = Path(project_root)
        ruleset = self._load_ruleset_for_preview(root, assay_key, draft_path)
        assay_name = str(ruleset.data.get("assay_name", "")).strip()
        if not assay_name:
            raise RuleSuiteError("ruleset missing assay_name")

        text_result = self.get_assay_text(
            project_root=project_root,
            pdf_path=pdf_path,
            assay_key=assay_key,
            assay_name=assay_name,
            draft_path=draft_path,
        )
        record = extract_record(text_result["assay_block"], ruleset)
        return {
            "pdf_path": pdf_path,
            "assay_key": assay_key,
            "detected_assays": text_result["detected_assays"],
            "used_ruleset": draft_path or ruleset.ruleset_file,
            "lot_id": record.lot_id,
            "dedupe_key": record.dedupe_key,
            "data": record.data,
        }

    def activate_draft(self, project_root: str, assay_key: str, draft_path: str) -> Path:
        root = Path(project_root)
        rs = resolve_ruleset(assay_key, str(root / "rules"), str(root / "rules" / "index.json"))
        target = root / "rules" / rs.ruleset_file
        source_data = self.load_draft(draft_path)
        check = _validate_draft_data(source_data)
        if not check["ok"]:
            raise RuleSuiteError(f"draft_invalid: {check['errors']}")
        _write_json_atomic(target, source_data)
        return target

    def activate_new_draft(self, project_root: str, assay_key: str, assay_name: str, draft_path: str) -> Path:
        root = Path(project_root)
        rules_dir = root / "rules"
        index_path = rules_dir / "index.json"

        assay_key_clean = assay_key.strip()
        assay_name_clean = assay_name.strip()
        if not assay_key_clean or not assay_name_clean:
            raise RuleSuiteError("assay_key and assay_name are required")

        source_data = self.load_draft(draft_path)
        source_data["assay_key"] = assay_key_clean
        source_data["assay_name"] = assay_name_clean
        check = _validate_draft_data(source_data)
        if not check["ok"]:
            raise RuleSuiteError(f"draft_invalid: {check['errors']}")

        index = _read_json_object(index_path)
        assays = index.setdefault("assays", [])
        if not isinstance(assays, list):
            raise RuleSuiteError("index.assays must be list")

        if any(str(row.get("assay_key", "")).strip() == assay_key_clean for row in assays if isinstance(row, dict)):
            raise RuleSuiteError(f"assay_key_exists: {assay_key_clean}")

        safe_name = _safe_filename(assay_name_clean)
        if not safe_name:
            raise RuleSuiteError("invalid_assay_name_for_filename")
        if safe_name.lower() == "index":
            raise RuleSuiteError("invalid_assay_name_for_filename:index")

        ruleset_file = f"{safe_name}.json"
        lower_existing = {
            p.name.lower()
            for p in rules_dir.glob("*.json")
            if p.name.lower() != "index.json"
        }
        if ruleset_file.lower() in lower_existing:
            raise RuleSuiteError(f"ruleset_file_exists_case_insensitive: {ruleset_file}")
        target = rules_dir / ruleset_file
        if target.exists():
            raise RuleSuiteError(f"ruleset_file_exists: {ruleset_file}")

        _write_json_atomic(target, source_data)
        assays.append({"assay_key": assay_key_clean, "ruleset_file": ruleset_file})
        _write_json_atomic(index_path, index)
        return target

    def list_fields(self, project_root: str, assay_key: str) -> List[str]:
        root = Path(project_root)
        rs = resolve_ruleset(assay_key, str(root / "rules"), str(root / "rules" / "index.json"))
        fields = rs.data.get("extract_rules", {}).get("fields", [])
        return [str(f.get("key", "")).strip() for f in fields if str(f.get("key", "")).strip()]

    def _load_fields_list(self, draft_path: str) -> List[Any]:
        data = self.load_draft(draft_path)
        fields = data.get("extract_rules", {}).get("fields", [])
        if not isinstance(fields, list):
            raise RuleSuiteError("extract_rules.fields must be list")
        return fields

    def _load_ruleset_for_preview(self, root: Path, assay_key: str, draft_path: str | None) -> RuleSet:
        if draft_path:
            p = Path(draft_path)
            if not p.exists():
                raise RuleSuiteError(f"draft_not_found: {p}")
            data = json.loads(p.read_text(encoding="utf-8"))
            return RuleSet(assay_key=assay_key, ruleset_file=p.name, data=data)
        return resolve_ruleset(assay_key, str(root / "rules"), str(root / "rules" / "index.json"))


def _ensure_fields(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    extract_rules = data.setdefault("extract_rules", {})
    if not isinstance(extract_rules, dict):
        raise RuleSuiteError("extract_rules must be object")
    fields = extract_rules.setdefault("fields", [])
    if not isinstance(fields, list):
        raise RuleSuiteError("extract_rules.fields must be list")
    return fields
