from __future__ import annotations

from typing import Any, Dict, List

from .rulesuite import RuleSuite
from .templates import HEADER_FIELD_KEYS, REQUIRED_HEADER_FIELD_KEYS
from .required_fields import check_required_fields as _check_required_fields
from .authoring_readiness import check_authoring_readiness as _check_authoring_readiness
from .header_aliases import LEGACY_HEADER_ALIASES, LEGACY_HEADER_ALIAS_KEYS
from .regex_builder import build_regex_from_builder_spec as _build_regex_from_builder_spec
from .regex_builder import suggest_builder_spec_from_selection as _suggest_builder_spec_from_selection
from .regex_suggest import suggest_regex_from_selection as _suggest_regex_from_selection

__all__ = [
    "HEADER_FIELD_KEYS",
    "LEGACY_HEADER_ALIASES",
    "LEGACY_HEADER_ALIAS_KEYS",
    "REQUIRED_HEADER_FIELD_KEYS",
    "activate_draft",
    "activate_new_draft",
    "add_field",
    "adopt_candidate_field",
    "batch_check_fields",
    "build_regex_from_builder_spec",
    "check_authoring_readiness",
    "check_candidates",
    "check_required_fields",
    "create_blank_draft",
    "create_draft",
    "create_draft_from_ruleset",
    "create_draft_from_template",
    "delete_ruleset",
    "derive_draft",
    "diff_draft_vs_active",
    "get_assay_text",
    "list_fields",
    "list_rulesets",
    "load_draft",
    "locate_fields",
    "read_candidate_fields",
    "move_field",
    "preview_extract",
    "remove_field",
    "rename_field",
    "save_draft",
    "set_dedupe_fields",
    "set_excel_rules",
    "set_field_regex",
    "set_lot_rule",
    "suggest_builder_spec_from_selection",
    "suggest_regex_from_selection",
    "test_regex",
    "update_field",
    "validate_draft",
]


def create_draft(project_root: str, assay_key: str) -> str:
    return str(RuleSuite().create_draft(project_root, assay_key))


def create_blank_draft(project_root: str, assay_key: str, assay_name: str) -> str:
    return str(RuleSuite().create_blank_draft(project_root, assay_key, assay_name))


def derive_draft(project_root: str, source_assay_key: str, new_assay_key: str, new_assay_name: str) -> str:
    return str(RuleSuite().derive_draft(project_root, source_assay_key, new_assay_key, new_assay_name))


def load_draft(draft_path: str) -> Dict[str, Any]:
    return RuleSuite().load_draft(draft_path)


def save_draft(draft_path: str, data: Dict[str, Any]) -> str:
    return str(RuleSuite().save_draft(draft_path, data))


def set_field_regex(draft_path: str, field_key: str, regex: str) -> str:
    return str(RuleSuite().set_field_regex(draft_path, field_key, regex))


def add_field(
    draft_path: str,
    key: str,
    regex: str,
    required: bool = False,
    search_from: Dict[str, Any] | None = None,
) -> str:
    return str(RuleSuite().add_field(draft_path, key, regex, required=required, search_from=search_from))


def remove_field(draft_path: str, field_key: str) -> str:
    return str(RuleSuite().remove_field(draft_path, field_key))


def rename_field(draft_path: str, old_key: str, new_key: str) -> str:
    return str(RuleSuite().rename_field(draft_path, old_key, new_key))


def duplicate_field(draft_path: str, source_key: str, new_key: str) -> str:
    return str(RuleSuite().duplicate_field(draft_path, source_key, new_key))


def move_field(draft_path: str, field_key: str, direction: str) -> str:
    return str(RuleSuite().move_field(draft_path, field_key, direction))


def update_field(
    draft_path: str,
    field_key: str,
    regex: str | None = None,
    required: bool | None = None,
    search_from: Dict[str, Any] | None = None,
) -> str:
    return str(
        RuleSuite().update_field(
            draft_path,
            field_key,
            regex=regex,
            required=required,
            search_from=search_from,
        )
    )


def set_lot_rule(draft_path: str, regex: str) -> str:
    return str(RuleSuite().set_lot_rule(draft_path, regex))


def set_dedupe_fields(draft_path: str, fields: List[str]) -> str:
    return str(RuleSuite().set_dedupe_fields(draft_path, fields))


def set_excel_rules(
    draft_path: str,
    filename_template: str,
    sheet_template: str,
    column_mapping: Dict[str, str],
) -> str:
    return str(RuleSuite().set_excel_rules(draft_path, filename_template, sheet_template, column_mapping))


def test_regex(text: str, regex: str, group: int = 1) -> Dict[str, Any]:
    return RuleSuite().test_regex(text, regex, group=group)


test_regex.__test__ = False


def suggest_regex_from_selection(
    line_text: str,
    selected_text: str,
    selection_start: int | None = None,
    selection_end: int | None = None,
) -> Dict[str, Any]:
    return _suggest_regex_from_selection(
        line_text,
        selected_text,
        selection_start=selection_start,
        selection_end=selection_end,
    )


def build_regex_from_builder_spec(spec: Dict[str, Any]) -> Dict[str, Any]:
    return _build_regex_from_builder_spec(spec)


def suggest_builder_spec_from_selection(
    line_text: str,
    selected_text: str,
    selection_start: int | None = None,
    selection_end: int | None = None,
    *,
    line_index: int | None = None,
) -> Dict[str, Any]:
    return _suggest_builder_spec_from_selection(
        line_text,
        selected_text,
        selection_start=selection_start,
        selection_end=selection_end,
        line_index=line_index,
    )


def get_assay_text(
    project_root: str,
    pdf_path: str,
    assay_key: str,
    assay_name: str,
    draft_path: str | None = None,
) -> Dict[str, Any]:
    return RuleSuite().get_assay_text(project_root, pdf_path, assay_key, assay_name, draft_path=draft_path)


def validate_draft(draft_path: str) -> Dict[str, Any]:
    return RuleSuite().validate_draft(draft_path)


def batch_check_fields(draft_path: str, assay_text: str, group: int = 1) -> Dict[str, Any]:
    return RuleSuite().batch_check_fields(draft_path, assay_text, group=group)


def check_required_fields(draft_path: str, assay_text: str, group: int = 1) -> Dict[str, Any]:
    return _check_required_fields(draft_path, assay_text, group=group)


def check_authoring_readiness(
    draft_path: str,
    assay_text: str | None = None,
    *,
    group: int = 1,
) -> Dict[str, Any]:
    """Authoring-Readiness: Struktur optional + Pflichtfelder gegen Beispieltext.

    Siehe ``authoring_readiness.check_authoring_readiness`` für Semantik (``no_assay_text`` vs. fachliche Freigabe).
    """
    return _check_authoring_readiness(draft_path, assay_text, group=group)


def locate_fields(draft_path: str, assay_text: str, group: int = 1) -> Dict[str, Any]:
    return RuleSuite().locate_fields(draft_path, assay_text, group=group)


locate_fields.__test__ = False


def diff_draft_vs_active(project_root: str, assay_key: str, draft_path: str) -> Dict[str, Any]:
    return RuleSuite().diff_draft_vs_active(project_root, assay_key, draft_path)


def preview_extract(project_root: str, pdf_path: str, assay_key: str, draft_path: str | None = None) -> Dict[str, Any]:
    return RuleSuite().preview_extract(project_root, pdf_path, assay_key, draft_path=draft_path)


def activate_draft(project_root: str, assay_key: str, draft_path: str) -> str:
    return str(RuleSuite().activate_draft(project_root, assay_key, draft_path))


def activate_new_draft(project_root: str, assay_key: str, assay_name: str, draft_path: str) -> str:
    return str(RuleSuite().activate_new_draft(project_root, assay_key, assay_name, draft_path))


def list_fields(project_root: str, assay_key: str) -> List[str]:
    return RuleSuite().list_fields(project_root, assay_key)


def create_draft_from_template(project_root: str, assay_key: str, assay_name: str) -> str:
    from .templates import create_draft_from_template as _impl

    return str(_impl(project_root, assay_key, assay_name))


def create_draft_from_ruleset(
    project_root: str,
    source_assay_key: str,
    new_assay_key: str,
    new_assay_name: str,
) -> str:
    from .candidates import create_draft_from_ruleset as _impl

    return str(_impl(project_root, source_assay_key, new_assay_key, new_assay_name))


def read_candidate_fields(
    project_root: str,
    *,
    source: str | None = None,
    source_assay_key: str | None = None,
) -> Dict[str, Any]:
    from .candidates import read_candidate_fields as _impl

    return _impl(project_root, source=source, source_assay_key=source_assay_key)


def check_candidates(
    project_root: str,
    assay_text: str,
    draft_path: str,
    candidate_source: Dict[str, Any],
    *,
    dismissed_keys: tuple[str, ...] | list[str] = (),
    group: int = 1,
) -> Dict[str, Any]:
    from .candidates import check_candidates as _impl

    return _impl(
        project_root,
        assay_text,
        draft_path,
        candidate_source,
        dismissed_keys=dismissed_keys,
        group=group,
    )


def adopt_candidate_field(
    project_root: str,
    draft_path: str,
    field_key: str,
    candidate_source: Dict[str, Any],
    *,
    regex: str | None = None,
    required: bool | None = None,
    search_from: Dict[str, Any] | None = None,
    search_from_set: bool = False,
) -> str:
    from .candidates import _SEARCH_FROM_UNSET
    from .candidates import adopt_candidate_field as _impl

    sf = search_from if search_from_set else _SEARCH_FROM_UNSET
    return str(
        _impl(
            project_root,
            draft_path,
            field_key,
            candidate_source,
            regex=regex,
            required=required,
            search_from=sf,  # type: ignore[arg-type]
        )
    )


def list_rulesets(project_root: str) -> List[Dict[str, Any]]:
    from .manage import list_rulesets as _impl

    return _impl(project_root)


def delete_ruleset(project_root: str, assay_key: str) -> Dict[str, Any]:
    from .manage import delete_ruleset as _impl

    return _impl(project_root, assay_key)
