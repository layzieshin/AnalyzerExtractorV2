"""RuleSuite-Fassade: Draft-Lifecycle, Feld-/Meta-Mutationen, Preview und Aktivierung.

Die Fachlogik ist nach Verantwortlichkeit in Submodule aufgeteilt:
- json_io: atomares JSON-Schreiben, sichere Datei-/Key-Namen
- validation: Draft-Validierung (bewusst ohne ruleresolver-Import)
- regex_tools: Regex-Test, Batch-Check, Feld-Lokalisierung
- diffing: rekursiver Struktur-Diff
"""
from __future__ import annotations

import hashlib
import json
import re
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
from .history import snapshot_existing_active_ruleset
from .json_io import _read_json_object, _safe_filename, _safe_key, _write_json_atomic
from .lifecycle import rulesuite_draft_lock, rulesuite_lifecycle_lock
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
        *,
        excel_column: str | None = None,
        dedupe_member: bool | None = None,
        return_receipt: bool = False,
    ) -> Path | Dict[str, Any]:
        path = Path(draft_path)

        def _mutate(data: Dict[str, Any]) -> None:
            _apply_field_addition(
                data,
                key=key,
                regex=regex,
                required=required,
                search_from=search_from,
                excel_column=excel_column,
                dedupe_member=dedupe_member,
            )

        receipt = _locked_draft_mutation(
            path,
            _mutate,
            failure_code="draft_add_failed",
            conflict_code="draft_changed_during_add",
        )
        return _publish_mutation(path, receipt, return_receipt=return_receipt)

    def remove_field(self, draft_path: str, field_key: str, *, return_receipt: bool = False) -> Path | Dict[str, Any]:
        path = Path(draft_path)

        def _mutate(data: Dict[str, Any]) -> None:
            fields = _ensure_fields(data)
            out = [f for f in fields if str(f.get("key", "")).strip() != field_key]
            if len(out) == len(fields):
                raise RuleSuiteError(f"field_not_found: {field_key}")
            data.setdefault("extract_rules", {})["fields"] = out
            col_map = _column_mapping_dict(data)
            col_map.pop(field_key, None)
            dedupe = data.setdefault("extract_rules", {}).get("dedupe_fields")
            if isinstance(dedupe, list):
                data["extract_rules"]["dedupe_fields"] = [str(k) for k in dedupe if str(k) != field_key]

        receipt = _locked_draft_mutation(
            path,
            _mutate,
            failure_code="draft_remove_failed",
            conflict_code="draft_changed_during_remove",
        )
        return _publish_mutation(path, receipt, return_receipt=return_receipt)

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

        col_map = _column_mapping_dict(data)
        if old_key in col_map:
            col_map[new_key] = col_map.pop(old_key)
        _ensure_column_mapping_entry(data, new_key)

        dedupe = data.setdefault("extract_rules", {}).get("dedupe_fields")
        if isinstance(dedupe, list):
            data["extract_rules"]["dedupe_fields"] = [new_key if str(k) == old_key else str(k) for k in dedupe]

        return self.save_draft(draft_path, data)

    def duplicate_field(
        self,
        draft_path: str,
        source_key: str,
        new_key: str,
        *,
        return_receipt: bool = False,
    ) -> Path | Dict[str, Any]:
        new_key = new_key.strip()
        if not new_key:
            raise RuleSuiteError("new_key required")
        path = Path(draft_path)

        def _mutate(data: Dict[str, Any]) -> None:
            fields = _ensure_fields(data)
            if any(str(f.get("key", "")).strip() == new_key for f in fields):
                raise RuleSuiteError(f"field_exists: {new_key}")
            source = next((f for f in fields if str(f.get("key", "")).strip() == source_key), None)
            if not isinstance(source, dict):
                raise RuleSuiteError(f"field_not_found: {source_key}")
            cloned = deepcopy(source)
            cloned["key"] = new_key
            fields.append(cloned)
            _ensure_column_mapping_entry(data, new_key)

        receipt = _locked_draft_mutation(
            path,
            _mutate,
            failure_code="draft_duplicate_failed",
            conflict_code="draft_changed_during_duplicate",
        )
        return _publish_mutation(path, receipt, return_receipt=return_receipt)

    def move_field(
        self,
        draft_path: str,
        field_key: str,
        direction: str,
        *,
        return_receipt: bool = False,
    ) -> Path | Dict[str, Any]:
        if direction not in {"up", "down"}:
            raise RuleSuiteError("direction must be 'up' or 'down'")
        path = Path(draft_path)

        def _mutate(data: Dict[str, Any]) -> None:
            fields = _ensure_fields(data)
            idx = next((i for i, f in enumerate(fields) if str(f.get("key", "")).strip() == field_key), -1)
            if idx < 0:
                raise RuleSuiteError(f"field_not_found: {field_key}")
            if direction == "up":
                if idx == 0:
                    return
                fields[idx - 1], fields[idx] = fields[idx], fields[idx - 1]
            elif idx < len(fields) - 1:
                fields[idx + 1], fields[idx] = fields[idx], fields[idx + 1]

        receipt = _locked_draft_mutation(
            path,
            _mutate,
            failure_code="draft_move_failed",
            conflict_code="draft_changed_during_move",
        )
        return _publish_mutation(path, receipt, return_receipt=return_receipt)

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
            _ensure_column_mapping_entry(data, field_key)
            return self.save_draft(draft_path, data)

        raise RuleSuiteError(f"field_not_found: {field_key}")

    def replace_field(
        self,
        draft_path: str,
        selected_key: str,
        *,
        key: str,
        regex: str,
        required: bool,
        search_from: Dict[str, Any] | None,
        excel_column: str | None = None,
        dedupe_member: bool | None = None,
        return_receipt: bool = False,
    ) -> Path | Dict[str, Any]:
        path = Path(draft_path)

        def _mutate(data: Dict[str, Any]) -> None:
            _apply_field_replacement(
                data,
                selected_key,
                key=key,
                regex=regex,
                required=required,
                search_from=search_from,
                excel_column=excel_column,
                dedupe_member=dedupe_member,
            )

        receipt = _locked_draft_mutation(
            path,
            _mutate,
            failure_code="draft_replace_failed",
            conflict_code="draft_changed_during_replace",
        )
        return _publish_mutation(path, receipt, return_receipt=return_receipt)

    def update_draft_meta(
        self,
        draft_path: str,
        *,
        assay_key: str,
        assay_name: str,
        lot_regex: str,
        excel_filename_template: str,
        sheetname_template: str,
        return_receipt: bool = False,
    ) -> Path | Dict[str, Any]:
        path = Path(draft_path)
        assay_key_clean = assay_key.strip() if isinstance(assay_key, str) else ""
        assay_name_clean = assay_name.strip() if isinstance(assay_name, str) else ""
        lot_clean = lot_regex.strip() if isinstance(lot_regex, str) else ""
        filename_clean = excel_filename_template.strip() if isinstance(excel_filename_template, str) else ""
        sheet_clean = sheetname_template.strip() if isinstance(sheetname_template, str) else ""
        if not assay_key_clean or not assay_name_clean:
            raise RuleSuiteError("assay_key and assay_name are required")
        if not lot_clean:
            raise RuleSuiteError("lot_rule.regex required")
        if not filename_clean or not sheet_clean:
            raise RuleSuiteError("excel filename and sheetname are required")

        def _mutate(data: Dict[str, Any]) -> None:
            data["assay_key"] = assay_key_clean
            data["assay_name"] = assay_name_clean
            lot_rule = data.get("lot_rule")
            if lot_rule is None:
                lot_rule = {}
            if not isinstance(lot_rule, dict):
                raise RuleSuiteError("lot_rule must be object")
            lot_rule["regex"] = lot_clean
            data["lot_rule"] = lot_rule
            excel_rules = data.get("excel_rules")
            if excel_rules is None:
                excel_rules = {}
            if not isinstance(excel_rules, dict):
                raise RuleSuiteError("excel_rules must be object")
            excel_rules["excel_filename_template"] = filename_clean
            excel_rules["sheetname_template"] = sheet_clean
            data["excel_rules"] = excel_rules

        receipt = _locked_draft_mutation(
            path,
            _mutate,
            failure_code="draft_meta_failed",
            conflict_code="draft_changed_during_meta",
        )
        return _publish_mutation(path, receipt, return_receipt=return_receipt)

    def draft_content_revision(self, draft_path: str) -> str:
        path = Path(draft_path)
        with rulesuite_draft_lock(path):
            original, _loaded = _read_draft_bytes(path)
            return _content_revision(original)

    def restore_draft_snapshot(
        self,
        draft_path: str,
        data: Dict[str, Any],
        *,
        expected_revision: str | None = None,
        return_receipt: bool = False,
    ) -> Path | Dict[str, Any]:
        path = Path(draft_path)
        if not isinstance(data, dict):
            raise RuleSuiteError("draft_data_must_be_object")
        if not _is_content_revision(expected_revision):
            raise RuleSuiteError("draft_restore_revision_required")
        snapshot = deepcopy(data)

        def _mutate(current: Dict[str, Any]) -> None:
            current.clear()
            current.update(snapshot)

        receipt = _locked_draft_mutation(
            path,
            _mutate,
            failure_code="draft_restore_failed",
            conflict_code="draft_changed_during_restore",
            expected_revision=expected_revision,
            revision_conflict_code="draft_revision_conflict",
        )
        return _publish_mutation(path, receipt, return_receipt=return_receipt)

    def sync_column_mapping_from_fields(self, draft_path: str) -> Path:
        data = self.load_draft(draft_path)
        fields = _ensure_fields(data)
        for field in fields:
            key = str(field.get("key", "")).strip()
            if key:
                _ensure_column_mapping_entry(data, key)
        return self.save_draft(draft_path, data)

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
        detected: list[str] = []
        try:
            detected = [m.assay_key for m in detect_assays(norm_text, str(index_path))]
        except Exception:
            detected = []

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
            "device_id": getattr(record, "device_id", "DEFAULT_DEVICE"),
            "dedupe_version": getattr(record, "dedupe_version", ""),
            "dedupe_basis": getattr(record, "dedupe_basis", {}),
            "data": record.data,
        }

    def activate_draft(self, project_root: str, assay_key: str, draft_path: str) -> Path:
        with rulesuite_lifecycle_lock(project_root):
            root = Path(project_root)
            rs = resolve_ruleset(assay_key, str(root / "rules"), str(root / "rules" / "index.json"))
            target = root / "rules" / rs.ruleset_file
            source_data = self.load_draft(draft_path)
            check = _validate_draft_data(source_data)
            if not check["ok"]:
                raise RuleSuiteError(f"draft_invalid: {check['errors']}")
            snapshot_existing_active_ruleset(target)
            _write_json_atomic(target, source_data)
            return target

    def activate_new_draft(self, project_root: str, assay_key: str, assay_name: str, draft_path: str) -> Path:
        with rulesuite_lifecycle_lock(project_root):
            return self._activate_new_draft_unlocked(project_root, assay_key, assay_name, draft_path)

    def _activate_new_draft_unlocked(self, project_root: str, assay_key: str, assay_name: str, draft_path: str) -> Path:
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


def _read_draft_bytes(path: Path) -> tuple[bytes, Dict[str, Any]]:
    if not path.is_file():
        raise RuleSuiteError(f"draft_not_found: {path}")
    original = path.read_bytes()
    try:
        loaded = json.loads(original.decode("utf-8"))
    except Exception as exc:
        raise RuleSuiteError(f"draft_parse_failed: {exc}") from exc
    if not isinstance(loaded, dict):
        raise RuleSuiteError("draft_root_not_object")
    return original, loaded


def _content_revision(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _is_content_revision(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _publish_mutation(path: Path, receipt: Dict[str, Any], *, return_receipt: bool) -> Path | Dict[str, Any]:
    if return_receipt:
        return receipt
    return path


def _locked_draft_mutation(
    path: Path,
    mutate,
    *,
    failure_code: str,
    conflict_code: str,
    expected_revision: str | None = None,
    revision_conflict_code: str = "draft_revision_conflict",
) -> Dict[str, Any]:
    with rulesuite_draft_lock(path):
        original, loaded = _read_draft_bytes(path)
        before_revision = _content_revision(original)
        if expected_revision is not None and before_revision != expected_revision:
            raise RuleSuiteError(revision_conflict_code)
        before = deepcopy(loaded)
        data = deepcopy(loaded)
        mutate(data)
        written = _commit_draft_mutation(
            path,
            original,
            data,
            failure_code=failure_code,
            conflict_code=conflict_code,
        )
        return {
            "before": before,
            "before_revision": before_revision,
            "after_revision": _content_revision(written),
            "path": str(path),
        }


def _commit_draft_mutation(
    path: Path,
    original: bytes,
    data: Dict[str, Any],
    *,
    failure_code: str,
    conflict_code: str,
) -> bytes:
    if path.read_bytes() != original:
        raise RuleSuiteError(conflict_code)
    try:
        _write_json_atomic(path, data)
    except Exception as exc:
        raise RuleSuiteError(failure_code) from exc
    return path.read_bytes()


def _validated_search_from(search_from: Dict[str, Any] | None) -> Dict[str, Any] | None:
    if search_from is None:
        return None
    if not isinstance(search_from, dict):
        raise RuleSuiteError("invalid_search_from")
    has_after = "after" in search_from
    has_line = "line" in search_from
    if has_after == has_line or set(search_from) - {"after", "line"}:
        raise RuleSuiteError("invalid_search_from")
    if has_after:
        marker = search_from.get("after")
        if not isinstance(marker, str) or not marker.strip():
            raise RuleSuiteError("invalid_search_from")
        try:
            re.compile(marker)
        except re.error as exc:
            raise RuleSuiteError("invalid_search_from") from exc
        return {"after": marker}
    line = search_from.get("line")
    if isinstance(line, bool) or not isinstance(line, int) or line < 0:
        raise RuleSuiteError("invalid_search_from")
    return {"line": line}


def _apply_field_addition(
    data: Dict[str, Any],
    *,
    key: str,
    regex: str,
    required: bool,
    search_from: Dict[str, Any] | None,
    excel_column: str | None,
    dedupe_member: bool | None,
) -> None:
    new_key = str(key).strip() if isinstance(key, str) else ""
    if not new_key:
        raise RuleSuiteError("field key required")
    if not isinstance(required, bool):
        raise RuleSuiteError("invalid_required")
    if not isinstance(regex, str) or not regex.strip():
        raise RuleSuiteError("invalid_regex")
    try:
        re.compile(regex)
    except re.error as exc:
        raise RuleSuiteError("invalid_regex") from exc
    if dedupe_member is not None and not isinstance(dedupe_member, bool):
        raise RuleSuiteError("invalid_dedupe_member")
    if excel_column is not None and (not isinstance(excel_column, str) or not excel_column.strip()):
        raise RuleSuiteError("invalid_excel_column")
    checked_search = _validated_search_from(search_from)

    extract_rules = data.get("extract_rules")
    if extract_rules is None:
        extract_rules = {}
        data["extract_rules"] = extract_rules
    if not isinstance(extract_rules, dict):
        raise RuleSuiteError("extract_rules must be object")
    fields = extract_rules.get("fields")
    if fields is None:
        fields = []
        extract_rules["fields"] = fields
    if not isinstance(fields, list):
        raise RuleSuiteError("extract_rules.fields must be list")
    if any(not isinstance(field, dict) for field in fields):
        raise RuleSuiteError("malformed_fields")
    if any(str(field.get("key", "")).strip() == new_key for field in fields):
        raise RuleSuiteError(f"field_exists: {new_key}")

    excel_rules = data.get("excel_rules", {})
    if excel_rules is None:
        excel_rules = {}
    if not isinstance(excel_rules, dict):
        raise RuleSuiteError("excel_rules must be object")
    if "column_mapping" not in excel_rules or excel_rules.get("column_mapping") is None:
        column_mapping: Dict[str, Any] = {}
    elif not isinstance(excel_rules.get("column_mapping"), dict):
        raise RuleSuiteError("excel_rules.column_mapping must be object")
    else:
        column_mapping = dict(excel_rules["column_mapping"])
    if excel_column is None:
        if new_key not in column_mapping:
            column_mapping[new_key] = new_key
    else:
        column_mapping[new_key] = excel_column.strip()
    data["excel_rules"] = excel_rules
    excel_rules["column_mapping"] = column_mapping

    raw_dedupe = extract_rules.get("dedupe_fields", None) if "dedupe_fields" in extract_rules else None
    if "dedupe_fields" in extract_rules and extract_rules.get("dedupe_fields") is None:
        raw_dedupe = None
    if raw_dedupe is not None and not isinstance(raw_dedupe, list):
        raise RuleSuiteError("extract_rules.dedupe_fields must be list")
    if isinstance(raw_dedupe, list) and any(not isinstance(item, str) for item in raw_dedupe):
        raise RuleSuiteError("malformed_dedupe_fields")
    if dedupe_member is True:
        migrated = [str(item) for item in (raw_dedupe or [])]
        if new_key not in migrated:
            migrated.append(new_key)
        extract_rules["dedupe_fields"] = migrated
    elif dedupe_member is False and isinstance(raw_dedupe, list):
        extract_rules["dedupe_fields"] = [str(item) for item in raw_dedupe if str(item) != new_key]

    row: Dict[str, Any] = {"key": new_key, "regex": regex, "required": required}
    if checked_search is not None:
        row["search_from"] = checked_search
    fields.append(row)


def _apply_field_replacement(
    data: Dict[str, Any],
    selected_key: str,
    *,
    key: str,
    regex: str,
    required: bool,
    search_from: Dict[str, Any] | None,
    excel_column: str | None,
    dedupe_member: bool | None,
) -> None:
    identity = str(selected_key).strip()
    new_key = str(key).strip() if isinstance(key, str) else ""
    if not identity or not new_key:
        raise RuleSuiteError("field key required")
    if not isinstance(regex, str) or not regex.strip():
        raise RuleSuiteError("invalid_regex")
    try:
        re.compile(regex)
    except re.error as exc:
        raise RuleSuiteError("invalid_regex") from exc
    if not isinstance(required, bool):
        raise RuleSuiteError("invalid_required")
    if dedupe_member is not None and not isinstance(dedupe_member, bool):
        raise RuleSuiteError("invalid_dedupe_member")
    if excel_column is not None and (not isinstance(excel_column, str) or not excel_column.strip()):
        raise RuleSuiteError("invalid_excel_column")
    checked_search = _validated_search_from(search_from)

    extract_rules = data.get("extract_rules")
    if not isinstance(extract_rules, dict):
        raise RuleSuiteError("extract_rules must be object")
    fields = extract_rules.get("fields")
    if not isinstance(fields, list):
        raise RuleSuiteError("extract_rules.fields must be list")
    matches = [idx for idx, field in enumerate(fields) if isinstance(field, dict) and str(field.get("key", "")).strip() == identity]
    if len(matches) != 1:
        if not matches:
            raise RuleSuiteError(f"field_not_found: {identity}")
        raise RuleSuiteError("field_identity_ambiguous")
    index = matches[0]
    for idx, field in enumerate(fields):
        if idx == index or not isinstance(field, dict):
            continue
        if str(field.get("key", "")).strip() == new_key:
            raise RuleSuiteError(f"field_exists: {new_key}")

    excel_rules = data.get("excel_rules", {})
    if excel_rules is None:
        excel_rules = {}
    if not isinstance(excel_rules, dict):
        raise RuleSuiteError("excel_rules must be object")
    column_mapping = excel_rules.get("column_mapping", {})
    if column_mapping is None:
        column_mapping = {}
    if not isinstance(column_mapping, dict):
        raise RuleSuiteError("excel_rules.column_mapping must be object")
    column_mapping = dict(column_mapping)
    if new_key != identity and new_key in column_mapping:
        raise RuleSuiteError("column_mapping_conflict")
    mapping_changes = excel_column is not None or new_key != identity
    if mapping_changes:
        if excel_column is None:
            if identity in column_mapping:
                column_mapping[new_key] = column_mapping.pop(identity)
            else:
                column_mapping[new_key] = new_key
        else:
            if new_key != identity:
                column_mapping.pop(identity, None)
            column_mapping[new_key] = excel_column.strip()
        data["excel_rules"] = excel_rules
        excel_rules["column_mapping"] = column_mapping

    if "dedupe_fields" not in extract_rules or extract_rules.get("dedupe_fields") is None:
        dedupe = []
        dedupe_present = False
    else:
        dedupe = extract_rules.get("dedupe_fields")
        dedupe_present = True
    if not isinstance(dedupe, list):
        raise RuleSuiteError("extract_rules.dedupe_fields must be list")
    was_member = any(str(item) == identity for item in dedupe)
    target_member = was_member if dedupe_member is None else dedupe_member
    migrated: List[str] = []
    seen: set[str] = set()
    placed = False
    for item in dedupe:
        item_key = str(item)
        if item_key == identity or item_key == new_key:
            if target_member and not placed:
                migrated.append(new_key)
                seen.add(new_key)
                placed = True
            continue
        if item_key in seen:
            continue
        migrated.append(item_key)
        seen.add(item_key)
    if target_member and new_key not in seen:
        migrated.append(new_key)
    if dedupe_present or target_member:
        extract_rules["dedupe_fields"] = migrated

    updated = deepcopy(fields[index])
    updated["key"] = new_key
    updated["regex"] = regex
    updated["required"] = required
    if checked_search is None:
        updated.pop("search_from", None)
    else:
        updated["search_from"] = checked_search
    fields[index] = updated


def _ensure_fields(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    extract_rules = data.setdefault("extract_rules", {})
    if not isinstance(extract_rules, dict):
        raise RuleSuiteError("extract_rules must be object")
    fields = extract_rules.setdefault("fields", [])
    if not isinstance(fields, list):
        raise RuleSuiteError("extract_rules.fields must be list")
    return fields


def _column_mapping_dict(data: Dict[str, Any]) -> Dict[str, str]:
    excel_rules = data.setdefault("excel_rules", {})
    if not isinstance(excel_rules, dict):
        excel_rules = {}
        data["excel_rules"] = excel_rules
    col_map = excel_rules.get("column_mapping")
    if not isinstance(col_map, dict):
        col_map = {}
        excel_rules["column_mapping"] = col_map
    return col_map


def _ensure_column_mapping_entry(data: Dict[str, Any], field_key: str) -> None:
    key = field_key.strip()
    if not key:
        return
    col_map = _column_mapping_dict(data)
    if key not in col_map:
        col_map[key] = key
