from __future__ import annotations

from pathlib import Path
from typing import Any

from src.assaycandidate.api import annotate_assay_candidates, find_assay_candidates, load_known_assay_keys
from src.contentsplitter.api import AssayDescriptor, split_by_assay_name_and_key
from src.jobcontroller.api import get_job_diagnostic_sources
from src.normalizer.api import normalize_lines
from src.parser.api import parse
from src.ruleresolver.api import validate_rules_integrity as ruleresolver_validate_rules_integrity
from src.rulesuite.api import (
    AuthoringReadinessError,
    REQUIRED_HEADER_FIELD_KEYS,
    activate_draft,
    activate_new_draft,
    add_field,
    adopt_candidate_field,
    adopt_candidate_fields,
    batch_check_fields,
    build_regex_from_builder_spec,
    check_authoring_readiness,
    check_candidates,
    check_required_fields,
    clone_ruleset_to_draft,
    create_blank_draft,
    create_authoring_proof,
    create_draft,
    create_draft_from_ruleset,
    create_draft_from_template,
    create_draft_from_template_if_missing,
    deactivate_ruleset,
    delete_inventory_item,
    delete_never_active_ruleset,
    delete_ruleset,
    diff_draft_vs_active,
    draft_path_for_assay,
    duplicate_field,
    derive_draft,
    get_assay_text,
    list_fields,
    list_rulesuite_inventory,
    load_draft,
    locate_fields,
    move_field,
    open_active_as_draft,
    open_history_as_draft,
    open_inactive_as_draft,
    preview_extract,
    read_candidate_fields,
    remove_field,
    rename_field,
    replace_field,
    draft_content_revision,
    restore_draft_snapshot,
    save_draft,
    set_dedupe_fields,
    set_excel_rules,
    set_field_regex,
    set_lot_rule,
    suggest_builder_spec_from_selection,
    suggest_regex_from_selection,
    sync_column_mapping_from_fields,
    test_regex,
    update_draft_meta,
    update_field,
    validate_draft,
    verify_authoring_proof,
)

from .models import AssayCandidateItem, RulesetInventoryItem


class RuleSuiteController:
    def __init__(self, project_root: str | Path) -> None:
        self._project_root = Path(project_root).resolve()

    @property
    def project_root(self) -> Path:
        return self._project_root

    @property
    def required_header_field_keys(self) -> tuple[str, ...]:
        return tuple(REQUIRED_HEADER_FIELD_KEYS)

    def load_normalized_pdf_text(self, pdf_path: str) -> str:
        document = parse(pdf_path)
        lines = [line for page in document.pages for line in page.lines]
        return "\n".join(normalize_lines(lines))

    def derive_assay_block(self, normalized_text: str, assay_key: str, assay_name: str) -> str:
        """Leitet einen Assay-Block nur aus bereits normalisiertem Text und Ziel-Key/-Name ab."""
        key = str(assay_key or "").strip()
        name = str(assay_name or "").strip()
        if not key or not name:
            raise ValueError("assay_key and assay_name are required")
        try:
            blocks = split_by_assay_name_and_key(
                str(normalized_text or ""),
                [AssayDescriptor(assay_key=key, assay_name=name)],
            )
        except RuntimeError as exc:
            if str(exc).startswith("content_split_failed:"):
                return ""
            raise
        return str(blocks.get(key, "") or "").strip()

    def list_inventory(self, kind: str = "all") -> list[RulesetInventoryItem]:
        rows = list_rulesuite_inventory(str(self._project_root), kind=kind)
        return [_to_inventory_item(row) for row in rows]

    def discover_assay_candidates(self, normalized_text: str) -> tuple[AssayCandidateItem, ...]:
        candidates = find_assay_candidates(str(normalized_text or ""))
        known_keys = load_known_assay_keys(str(self._project_root / "rules" / "index.json"))
        annotated = annotate_assay_candidates(candidates, known_keys)
        return tuple(_to_assay_candidate_item(row) for row in annotated)

    def discover_assay_candidates_for_job(self, job_id: str) -> tuple[AssayCandidateItem, ...]:
        sources = get_job_diagnostic_sources(self._project_root, job_id)
        if sources is None:
            return ()
        known_keys = load_known_assay_keys(str(self._project_root / "rules" / "index.json"))
        discovered: list[dict[str, Any]] = []
        seen: set[str] = set()
        for text in [sources.normalized_text, *(text for _, text in sources.block_texts)]:
            if not str(text or "").strip():
                continue
            for candidate in find_assay_candidates(str(text)):
                candidate_id = str(candidate.get("candidate_id") or "")
                if candidate_id and candidate_id in seen:
                    continue
                if candidate_id:
                    seen.add(candidate_id)
                discovered.append(candidate)
        annotated = annotate_assay_candidates(discovered, known_keys)
        return tuple(_to_assay_candidate_item(row) for row in annotated)

    def validate_rules_integrity(self) -> dict[str, Any]:
        rules_dir = self._project_root / "rules"
        index_path = rules_dir / "index.json"
        return ruleresolver_validate_rules_integrity(str(rules_dir), str(index_path))

    def load_draft(self, draft_path: str) -> dict[str, Any]:
        return load_draft(draft_path)

    def save_draft(self, draft_path: str, data: dict[str, Any]) -> str:
        return save_draft(draft_path, data)

    def create_draft(self, assay_key: str) -> str:
        return create_draft(str(self._project_root), assay_key)

    def create_blank_draft(self, assay_key: str, assay_name: str) -> str:
        return create_blank_draft(str(self._project_root), assay_key, assay_name)

    def derive_draft(self, source_assay_key: str, new_assay_key: str, new_assay_name: str) -> str:
        return derive_draft(str(self._project_root), source_assay_key, new_assay_key, new_assay_name)

    def clone_ruleset_to_draft(
        self,
        source_assay_key: str,
        target_assay_key: str,
        target_assay_name: str,
        *,
        overwrite: bool = False,
        include_fields: bool = True,
    ) -> dict[str, Any]:
        return clone_ruleset_to_draft(
            str(self._project_root),
            source_assay_key,
            target_assay_key,
            target_assay_name,
            overwrite=overwrite,
            include_fields=include_fields,
        )

    def create_draft_from_template(self, assay_key: str, assay_name: str) -> str:
        return create_draft_from_template(str(self._project_root), assay_key, assay_name)

    def create_draft_from_template_if_missing(self, assay_key: str, assay_name: str) -> dict[str, Any]:
        return create_draft_from_template_if_missing(str(self._project_root), assay_key, assay_name)

    def create_draft_from_ruleset(
        self,
        source_assay_key: str,
        new_assay_key: str,
        new_assay_name: str,
    ) -> str:
        return create_draft_from_ruleset(str(self._project_root), source_assay_key, new_assay_key, new_assay_name)

    def draft_path_for_assay(self, assay_key: str) -> str:
        return draft_path_for_assay(str(self._project_root), assay_key)

    def deactivate_ruleset(self, assay_key: str) -> dict[str, Any]:
        return deactivate_ruleset(str(self._project_root), assay_key)

    def delete_ruleset(self, assay_key: str) -> dict[str, Any]:
        return delete_ruleset(str(self._project_root), assay_key)

    def delete_never_active_ruleset(self, draft_path: str) -> dict[str, Any]:
        return delete_never_active_ruleset(str(self._project_root), draft_path)

    def open_active_as_draft(self, assay_key: str) -> dict[str, Any]:
        return open_active_as_draft(str(self._project_root), assay_key)

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
    ) -> str | dict[str, Any]:
        return update_draft_meta(
            draft_path,
            assay_key=assay_key,
            assay_name=assay_name,
            lot_regex=lot_regex,
            excel_filename_template=excel_filename_template,
            sheetname_template=sheetname_template,
            return_receipt=return_receipt,
        )

    def draft_content_revision(self, draft_path: str) -> str:
        return draft_content_revision(draft_path)

    def restore_draft_snapshot(
        self,
        draft_path: str,
        data: dict[str, Any],
        *,
        expected_revision: str | None = None,
        return_receipt: bool = False,
    ) -> str | dict[str, Any]:
        return restore_draft_snapshot(
            draft_path,
            data,
            expected_revision=expected_revision,
            return_receipt=return_receipt,
        )

    def replace_field(
        self,
        draft_path: str,
        selected_key: str,
        *,
        key: str,
        regex: str,
        required: bool,
        search_from: dict[str, Any] | None,
        excel_column: str | None = None,
        dedupe_member: bool | None = None,
        return_receipt: bool = False,
    ) -> str | dict[str, Any]:
        return replace_field(
            draft_path,
            selected_key,
            key=key,
            regex=regex,
            required=required,
            search_from=search_from,
            excel_column=excel_column,
            dedupe_member=dedupe_member,
            return_receipt=return_receipt,
        )

    def delete_inventory_item(self, kind: str, path_or_key: str) -> dict[str, Any]:
        return delete_inventory_item(str(self._project_root), kind, path_or_key)

    def open_history_as_draft(self, history_path: str) -> dict[str, Any]:
        return open_history_as_draft(str(self._project_root), history_path)

    def open_inactive_as_draft(self, inactive_path: str) -> dict[str, Any]:
        return open_inactive_as_draft(str(self._project_root), inactive_path)

    def activate_draft(self, assay_key: str, draft_path: str) -> str:
        self._require_authoring_proof(assay_key, draft_path)
        return activate_draft(str(self._project_root), assay_key, draft_path)

    def activate_new_draft(self, assay_key: str, assay_name: str, draft_path: str) -> str:
        self._require_authoring_proof(assay_key, draft_path)
        return activate_new_draft(str(self._project_root), assay_key, assay_name, draft_path)

    def create_authoring_proof(
        self,
        assay_key: str,
        draft_path: str,
        failing_pdf_path: str,
        reference_pdf_path: str | None = None,
    ) -> dict[str, Any]:
        return create_authoring_proof(
            str(self._project_root),
            assay_key,
            draft_path,
            failing_pdf_path,
            reference_pdf_path,
        )

    def verify_authoring_proof(self, assay_key: str, draft_path: str) -> dict[str, Any]:
        return verify_authoring_proof(str(self._project_root), assay_key, draft_path)

    def _require_authoring_proof(self, assay_key: str, draft_path: str) -> None:
        report = self.verify_authoring_proof(assay_key, draft_path)
        if report.get("ok"):
            return
        errors = ",".join(str(item) for item in report.get("errors", [])) or "authoring_proof_invalid"
        raise AuthoringReadinessError(errors)

    def list_fields(self, assay_key: str) -> list[str]:
        return list_fields(str(self._project_root), assay_key)

    def add_field(
        self,
        draft_path: str,
        key: str,
        regex: str,
        *,
        required: bool = False,
        search_from: dict[str, Any] | None = None,
        excel_column: str | None = None,
        dedupe_member: bool | None = None,
        return_receipt: bool = False,
    ) -> str | dict[str, Any]:
        return add_field(
            draft_path,
            key,
            regex,
            required=required,
            search_from=search_from,
            excel_column=excel_column,
            dedupe_member=dedupe_member,
            return_receipt=return_receipt,
        )

    def remove_field(self, draft_path: str, field_key: str, *, return_receipt: bool = False) -> str | dict[str, Any]:
        return remove_field(draft_path, field_key, return_receipt=return_receipt)

    def rename_field(self, draft_path: str, old_key: str, new_key: str) -> str:
        return rename_field(draft_path, old_key, new_key)

    def duplicate_field(
        self, draft_path: str, source_key: str, new_key: str, *, return_receipt: bool = False
    ) -> str | dict[str, Any]:
        return duplicate_field(draft_path, source_key, new_key, return_receipt=return_receipt)

    def move_field(
        self, draft_path: str, field_key: str, direction: str, *, return_receipt: bool = False
    ) -> str | dict[str, Any]:
        return move_field(draft_path, field_key, direction, return_receipt=return_receipt)

    def update_field(
        self,
        draft_path: str,
        field_key: str,
        *,
        regex: str | None = None,
        required: bool | None = None,
        search_from: dict[str, Any] | None = None,
    ) -> str:
        return update_field(
            draft_path,
            field_key,
            regex=regex,
            required=required,
            search_from=search_from,
        )

    def set_field_regex(self, draft_path: str, field_key: str, regex: str) -> str:
        return set_field_regex(draft_path, field_key, regex)

    def set_lot_rule(self, draft_path: str, regex: str) -> str:
        return set_lot_rule(draft_path, regex)

    def set_dedupe_fields(self, draft_path: str, fields: list[str]) -> str:
        return set_dedupe_fields(draft_path, fields)

    def set_excel_rules(
        self,
        draft_path: str,
        filename_template: str,
        sheet_template: str,
        column_mapping: dict[str, str],
    ) -> str:
        return set_excel_rules(draft_path, filename_template, sheet_template, column_mapping)

    def sync_column_mapping_from_fields(self, draft_path: str) -> str:
        return sync_column_mapping_from_fields(draft_path)

    def get_assay_text(
        self,
        pdf_path: str,
        assay_key: str,
        assay_name: str,
        *,
        draft_path: str | None = None,
    ) -> dict[str, Any]:
        return get_assay_text(
            str(self._project_root),
            pdf_path,
            assay_key,
            assay_name,
            draft_path=draft_path,
        )

    def test_regex(
        self,
        text: str,
        regex: str,
        *,
        group: int = 1,
        search_from: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return test_regex(text, regex, group=group, search_from=search_from)

    def suggest_regex_from_selection(
        self,
        line_text: str,
        selected_text: str,
        *,
        selection_start: int | None = None,
        selection_end: int | None = None,
    ) -> dict[str, Any]:
        return suggest_regex_from_selection(
            line_text,
            selected_text,
            selection_start=selection_start,
            selection_end=selection_end,
        )

    def suggest_builder_spec_from_selection(
        self,
        line_text: str,
        selected_text: str,
        *,
        selection_start: int | None = None,
        selection_end: int | None = None,
        line_index: int | None = None,
    ) -> dict[str, Any]:
        return suggest_builder_spec_from_selection(
            line_text,
            selected_text,
            selection_start=selection_start,
            selection_end=selection_end,
            line_index=line_index,
        )

    def build_regex_from_builder_spec(self, spec: dict[str, Any]) -> dict[str, Any]:
        return build_regex_from_builder_spec(spec)

    def batch_check_fields(self, draft_path: str, assay_text: str, *, group: int = 1) -> dict[str, Any]:
        return batch_check_fields(draft_path, assay_text, group=group)

    def check_required_fields(self, draft_path: str, assay_text: str, *, group: int = 1) -> dict[str, Any]:
        return check_required_fields(draft_path, assay_text, group=group)

    def check_authoring_readiness(
        self,
        draft_path: str,
        assay_text: str | None = None,
        *,
        group: int = 1,
    ) -> dict[str, Any]:
        return check_authoring_readiness(draft_path, assay_text, group=group)

    def locate_fields(self, draft_path: str, assay_text: str, *, group: int = 1) -> dict[str, Any]:
        return locate_fields(draft_path, assay_text, group=group)

    def validate_draft(self, draft_path: str) -> dict[str, Any]:
        return validate_draft(draft_path)

    def diff_draft_vs_active(self, assay_key: str, draft_path: str) -> dict[str, Any]:
        return diff_draft_vs_active(str(self._project_root), assay_key, draft_path)

    def preview_extract(
        self,
        pdf_path: str,
        assay_key: str,
        *,
        draft_path: str | None = None,
    ) -> dict[str, Any]:
        return preview_extract(str(self._project_root), pdf_path, assay_key, draft_path=draft_path)

    def read_candidate_fields(
        self,
        *,
        source: str | None = None,
        source_assay_key: str | None = None,
    ) -> dict[str, Any]:
        return read_candidate_fields(
            str(self._project_root),
            source=source,
            source_assay_key=source_assay_key,
        )

    def check_candidates(
        self,
        assay_text: str,
        draft_path: str,
        candidate_source: dict[str, Any],
        *,
        dismissed_keys: tuple[str, ...] | list[str] = (),
        group: int = 1,
    ) -> dict[str, Any]:
        return check_candidates(
            str(self._project_root),
            assay_text,
            draft_path,
            candidate_source,
            dismissed_keys=dismissed_keys,
            group=group,
        )

    def adopt_candidate_field(
        self,
        draft_path: str,
        field_key: str,
        candidate_source: dict[str, Any],
        *,
        regex: str | None = None,
        required: bool | None = None,
        search_from: dict[str, Any] | None = None,
        search_from_set: bool = False,
    ) -> str:
        return adopt_candidate_field(
            str(self._project_root),
            draft_path,
            field_key,
            candidate_source,
            regex=regex,
            required=required,
            search_from=search_from,
            search_from_set=search_from_set,
        )

    def adopt_candidate_fields(
        self,
        draft_path: str,
        candidate_source: dict[str, Any],
        field_keys: list[str] | None = None,
        overwrite: bool = False,
    ) -> dict[str, Any]:
        return adopt_candidate_fields(
            str(self._project_root),
            draft_path,
            candidate_source,
            field_keys=field_keys,
            overwrite=overwrite,
        )


def _to_assay_candidate_item(row: dict[str, Any]) -> AssayCandidateItem:
    return AssayCandidateItem(
        candidate_id=str(row.get("candidate_id") or ""),
        assay_key=str(row.get("assay_key") or ""),
        assay_name_hint=str(row.get("assay_name_hint") or ""),
        test_file=str(row.get("test_file") or ""),
        line_no=str(row.get("line_no") or ""),
        line_text=str(row.get("line_text") or ""),
        reason=str(row.get("reason") or ""),
        confidence=str(row.get("confidence") or ""),
        known_status=str(row.get("known_status") or ""),
    )


def _to_inventory_item(row: dict[str, Any]) -> RulesetInventoryItem:
    return RulesetInventoryItem(
        kind=str(row.get("kind") or ""),
        display_type=str(row.get("display_type") or ""),
        assay_key=str(row.get("assay_key") or ""),
        assay_name=str(row.get("assay_name") or ""),
        path=str(row.get("path") or ""),
        ruleset_file=str(row.get("ruleset_file") or ""),
        field_count=int(row.get("field_count") or 0),
        valid=bool(row.get("valid")),
        error=row.get("error"),
        modified_at=str(row.get("modified_at") or ""),
        sha256=str(row.get("sha256") or ""),
        read_only=bool(row.get("read_only")),
    )
