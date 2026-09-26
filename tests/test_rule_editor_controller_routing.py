"""Phase 5 step 2A: Rule-Editor mixins route domain calls through one controller."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from rule_editor.clone_dialog import CloneRulesetDialog
from rule_editor.guide import GuideMixin
from rule_editor.history_actions import HistoryMixin
from rule_editor.manage_actions import ManageMixin, _inventory_row
from rule_editor.pdf_text_actions import PdfTextMixin
from rule_editor.regex_builder_popup import RegexBuilderPopup
from rule_editor.release_actions import ReleaseMixin
from rule_editor.wizard import NewRulesetWizard
from rule_editor_main import RuleEditorWindow

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STEP_FILES = (
    "rule_editor_main.py",
    "rule_editor/draft_actions.py",
    "rule_editor/pdf_text_actions.py",
    "rule_editor/field_actions.py",
    "rule_editor/regex_actions.py",
    "rule_editor/marking_actions.py",
    "rule_editor/meta_actions.py",
    "rule_editor/history_actions.py",
    "rule_editor/regex_builder_popup.py",
)
FORBIDDEN_IMPORT_PREFIXES = ("src.rulesuite", "src.parser", "src.normalizer")


class _Var:
    def __init__(self, value: str = "") -> None:
        self.value = value

    def get(self) -> str:
        return self.value

    def set(self, value: str) -> None:
        self.value = value


def _imports(rel_path: str) -> list[str]:
    tree = ast.parse((PROJECT_ROOT / rel_path).read_text(encoding="utf-8-sig"), filename=rel_path)
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.append(node.module)
    return found


def test_step2a_files_avoid_direct_rulesuite_parser_and_normalizer_imports() -> None:
    offenders: list[str] = []
    for rel_path in STEP_FILES:
        for module in _imports(rel_path):
            if module.startswith(FORBIDDEN_IMPORT_PREFIXES):
                offenders.append(f"{rel_path}: {module}")
    assert offenders == []


def test_rule_editor_package_has_no_src_imports() -> None:
    offenders: list[str] = []
    for path in (PROJECT_ROOT / "rule_editor").rglob("*.py"):
        rel_path = path.relative_to(PROJECT_ROOT).as_posix()
        for module in _imports(rel_path):
            if module == "src" or module.startswith("src."):
                offenders.append(f"{rel_path}: {module}")
    assert offenders == []


def test_mixins_and_popup_import_no_src_modules() -> None:
    offenders: list[str] = []
    for rel_path in STEP_FILES:
        if rel_path == "rule_editor_main.py":
            continue
        for module in _imports(rel_path):
            if module == "src" or module.startswith("src."):
                offenders.append(f"{rel_path}: {module}")
    assert offenders == []


def test_window_imports_rulesuite_controller_from_application_api() -> None:
    tree = ast.parse((PROJECT_ROOT / "rule_editor_main.py").read_text(encoding="utf-8-sig"))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "src.application.api":
            imported.extend(alias.name for alias in node.names)
    assert imported == ["RuleSuiteController"]


def test_var_root_rebinds_one_controller_and_ignores_empty_or_same_root(monkeypatch, tmp_path: Path) -> None:
    created: list[object] = []

    class _Controller:
        def __init__(self, root: str | Path) -> None:
            self.project_root = Path(root).resolve()
            created.append(self)

    monkeypatch.setattr("rule_editor_main.RuleSuiteController", _Controller)
    host = type("Host", (), {})()
    first_root = tmp_path / "a"
    host.var_root = _Var(str(first_root))
    host._rules = None
    host.project_root = first_root
    host._bind_rules_controller = RuleEditorWindow._bind_rules_controller.__get__(host, type(host))

    host._bind_rules_controller(first_root)
    first = host._rules
    RuleEditorWindow._on_var_root_written(host)
    assert host._rules is first

    host.var_root.set("   ")
    RuleEditorWindow._on_var_root_written(host)
    assert host._rules is first

    host.var_root.set(str(tmp_path / "b"))
    RuleEditorWindow._on_var_root_written(host)
    assert host._rules is not first
    assert host._rules.project_root == (tmp_path / "b").resolve()
    assert host.project_root == Path(str(tmp_path / "b"))
    assert created == [first, host._rules]


class _PdfHost(PdfTextMixin):
    def after(self, _delay: int, callback) -> None:
        callback()

    def _finish_text_load_success(self, block: str, detected: object) -> None:
        self.success = (block, detected)

    def _finish_text_load_error(self, msg: str, fallback_text: str = "") -> None:
        self.error = (msg, fallback_text)


def test_pdf_worker_uses_ui_thread_controller_and_fulltext_fallback() -> None:
    class _Rules:
        def __init__(self) -> None:
            self.calls: list[tuple[object, ...]] = []

        def get_assay_text(self, pdf: str, key: str, name: str, *, draft_path: str | None = None) -> dict[str, object]:
            self.calls.append(("assay", pdf, key, name, draft_path))
            return {"assay_block": "BLOCK", "detected_assays": ["(k)"]}

        def load_normalized_pdf_text(self, pdf: str) -> str:
            self.calls.append(("full", pdf))
            return "FULL"

    rules = _Rules()
    host = _PdfHost()
    host._load_text_thread(rules, "a.pdf", "(k)", "Name", "draft.json")
    assert rules.calls == [("assay", "a.pdf", "(k)", "Name", "draft.json")]
    assert host.success == ("BLOCK", ["(k)"])

    class _EmptyBlock(_Rules):
        def get_assay_text(self, pdf: str, key: str, name: str, *, draft_path: str | None = None) -> dict[str, object]:
            self.calls.append(("assay", pdf, key, name, draft_path))
            raise RuntimeError("assay_block_empty: (k)")

    empty = _EmptyBlock()
    failed = _PdfHost()
    failed._load_text_thread(empty, "b.pdf", "(k)", "Name", "draft.json")
    assert empty.calls == [("assay", "b.pdf", "(k)", "Name", "draft.json"), ("full", "b.pdf")]
    assert failed.error[0] == "assay_block_empty: (k)"
    assert failed.error[1] == "FULL"

    class _FallbackFails(_EmptyBlock):
        def load_normalized_pdf_text(self, pdf: str) -> str:
            self.calls.append(("full", pdf))
            raise RuntimeError("parse failed")

    broken = _FallbackFails()
    quiet = _PdfHost()
    quiet._load_text_thread(broken, "c.pdf", "(k)", "Name", None)
    assert quiet.error == ("assay_block_empty: (k)", "")


def test_regex_builder_uses_injected_controller() -> None:
    calls: dict[str, object] = {}

    class _Rules:
        def suggest_builder_spec_from_selection(
            self,
            line_text: str,
            selected_text: str,
            *,
            selection_start: int | None = None,
            selection_end: int | None = None,
            line_index: int | None = None,
        ) -> dict[str, object]:
            calls["suggest"] = (line_text, selected_text, selection_start, selection_end, line_index)
            return {"spec": {"value_type": "decimal", "line_index": "3"}}

        def build_regex_from_builder_spec(self, spec: dict[str, object]) -> dict[str, object]:
            calls["build"] = dict(spec)
            return {"regex": r"(V)", "proposed_search_from": {"line": 3}}

        def test_regex(
            self,
            text: str,
            regex: str,
            *,
            group: int = 1,
            search_from: dict[str, object] | None = None,
        ) -> dict[str, object]:
            calls["test"] = (text, regex, group, search_from)
            return {"matched": True, "value": "V"}

    popup = RegexBuilderPopup.__new__(RegexBuilderPopup)
    popup._rules = _Rules()
    spec = popup._initial_spec(
        {
            "line_text": "Line",
            "text": "V",
            "sel_start_in_line": 1,
            "sel_end_in_line": 2,
            "line_idx": 3,
        }
    )
    assert spec == {"value_type": "decimal", "line_index": "3"}
    assert calls["suggest"] == ("Line", "V", 1, 2, 3)

    popup._spec = lambda: {"value_type": "decimal"}
    popup._render_result = lambda result: calls.__setitem__("rendered", result)
    popup.var_use_search_from = _Var("1")
    popup.var_use_search_from.get = lambda: True
    popup._assay_text = "Line V"
    tested = popup._test_regex()
    assert tested is None
    assert calls["build"] == {"value_type": "decimal"}
    assert calls["test"] == ("Line V", r"(V)", 1, {"line": 3})
    rendered = calls["rendered"]
    assert rendered["test"]["value"] == "V"
    assert rendered["test_search_from"] == {"line": 3}


class _HistoryHost(HistoryMixin):
    def __init__(self, rules: object) -> None:
        self.current_draft_path = "draft.json"
        self._rules = rules
        self._suspend_dirty_tracking = False
        self._dirty = True
        self.applied: dict | None = None

    def _apply_data_to_widgets(self, snap: dict) -> None:
        self.applied = snap


def test_history_undo_restore_uses_controller_load_and_save() -> None:
    stored = {"assay_key": "(1)", "assay_name": "A"}
    saved: list[tuple[str, dict]] = []

    class _Rules:
        def load_draft(self, draft_path: str) -> dict:
            assert draft_path == "draft.json"
            return dict(stored)

        def restore_draft_snapshot(
            self,
            draft_path: str,
            data: dict,
            *,
            expected_revision: str | None = None,
            return_receipt: bool = False,
        ) -> str | dict:
            saved.append((draft_path, dict(data), expected_revision, return_receipt))
            if return_receipt:
                return {"before": dict(data), "after_revision": "ab" * 32}
            return draft_path

    host = _HistoryHost(_Rules())
    assert host._capture_draft_snapshot() == stored
    host._restore_snapshot({"assay_key": "(1)", "assay_name": "B"}, expected_revision="cd" * 32)
    assert saved == [("draft.json", {"assay_key": "(1)", "assay_name": "B"}, "cd" * 32, True)]
    assert host.applied == {"assay_key": "(1)", "assay_name": "B"}
    assert host._dirty is False
    with pytest.raises(RuntimeError, match="keine erwartete Revision"):
        host._restore_snapshot({"assay_key": "(1)", "assay_name": "B"})


def test_history_step_fail_closed_on_revision_conflict_and_redo_rebinds(monkeypatch) -> None:
    errors: list[str] = []
    monkeypatch.setattr(
        "tkinter.messagebox.showerror",
        lambda *_args, **_kwargs: errors.append(str(_args[-1])),
    )
    calls: list[tuple] = []

    class _Rules:
        def restore_draft_snapshot(self, draft_path: str, data: dict, **kwargs: object) -> dict:
            calls.append((draft_path, data, kwargs))
            if kwargs.get("expected_revision") == "aa" * 32:
                raise RuntimeError("draft_revision_conflict")
            return {
                "before": {"assay_key": "(after)"},
                "after_revision": "bb" * 32,
                "before_revision": kwargs.get("expected_revision"),
                "path": draft_path,
            }

    host = HistoryMixin()
    host.current_draft_path = "draft.json"
    host._rules = _Rules()
    host._field_mutation_guard = False
    host._dialog_guard = False
    host._field_form_dirty = False
    host._dirty = True
    host._suspend_dirty_tracking = False
    stale = {"snapshot": {"assay_key": "(stale)"}, "expected_revision": "aa" * 32}
    host._undo_stack = [dict(stale)]
    host._redo_stack = [{"snapshot": {"assay_key": "(redo)"}, "expected_revision": "cc" * 32}]
    host.applied = None
    host.hints = []
    host._set_hint = lambda text: host.hints.append(text)
    host._resolve_dirty_field_form = lambda: True
    host._apply_data_to_widgets = lambda snap: setattr(host, "applied", snap)

    host.on_undo()
    assert calls and calls[0][2]["expected_revision"] == "aa" * 32
    assert host._undo_stack == [stale]
    assert host._redo_stack == [{"snapshot": {"assay_key": "(redo)"}, "expected_revision": "cc" * 32}]
    assert any("draft_revision_conflict" in item for item in errors)
    assert host.applied is None

    host._undo_stack = [{"snapshot": {"assay_key": "(before)"}, "expected_revision": "dd" * 32}]
    host._redo_stack = []
    host.on_undo()
    assert host._undo_stack == []
    assert host._redo_stack == [{"snapshot": {"assay_key": "(after)"}, "expected_revision": "bb" * 32}]
    assert host.applied == {"assay_key": "(before)"}

    host.on_redo()
    assert host._redo_stack == []
    assert host._undo_stack == [{"snapshot": {"assay_key": "(after)"}, "expected_revision": "bb" * 32}]


def test_preview_worker_uses_ui_thread_controller_and_draft_path() -> None:
    calls: list[tuple[str, str, str | None]] = []
    scheduled: list[tuple[int, object]] = []

    class _Rules:
        def preview_extract(self, pdf: str, key: str, *, draft_path: str | None = None) -> dict[str, str]:
            calls.append((pdf, key, draft_path))
            return {"value": "ok"}

    host = ReleaseMixin.__new__(ReleaseMixin)
    host.after = lambda delay, callback: scheduled.append((delay, callback))
    host._preview_thread(_Rules(), "sample.pdf", "(6bd7)", "draft.json")

    assert calls == [("sample.pdf", "(6bd7)", "draft.json")]
    assert scheduled[0][0] == 0


def test_release_activation_readiness_is_fail_closed(monkeypatch) -> None:
    errors: list[str] = []

    class _Rules:
        def verify_authoring_proof(self, key: str, draft_path: str) -> dict:
            assert (key, draft_path) == ("(1111)", "draft.json")
            return {"ok": False, "errors": ["authoring_proof_draft_changed"]}

    host = ReleaseMixin.__new__(ReleaseMixin)
    host._rules = _Rules()
    host.current_draft_path = "draft.json"
    host.var_new_assay_key = _Var("(1111)")
    monkeypatch.setattr(
        "rule_editor.release_actions.messagebox.showerror",
        lambda _title, message: errors.append(str(message)),
    )

    assert host._check_authoring_readiness_for_activate() is False
    assert errors and "Regel aus PDF erstellen oder prüfen" in errors[0]


def test_activation_validation_does_not_rewrite_clean_proven_draft() -> None:
    calls: list[str] = []

    class _Rules:
        def validate_draft(self, draft_path: str) -> dict:
            calls.append(draft_path)
            return {"ok": True, "errors": []}

    host = ReleaseMixin.__new__(ReleaseMixin)
    host._rules = _Rules()
    host.current_draft_path = "draft.json"
    host._save_meta_to_draft = lambda **_kwargs: (_ for _ in ()).throw(
        AssertionError("clean activation must not rewrite the hash-bound draft")
    )
    host._render_validation_report = lambda _report: None

    assert host._quick_validate("Aktivierung", save=False) is True
    assert calls == ["draft.json"]


def test_wizard_text_worker_loads_only_normalized_pdf_text() -> None:
    calls: list[str] = []
    scheduled: list[int] = []

    class _Rules:
        def get_assay_text(self, *_args: object, **_kwargs: object) -> dict[str, str]:
            raise AssertionError("pdf load must not call get_assay_text")

        def load_normalized_pdf_text(self, pdf: str) -> str:
            calls.append(pdf)
            return "FULL TEXT"

    wizard = NewRulesetWizard.__new__(NewRulesetWizard)
    wizard._closed = False
    wizard.after = lambda delay, callback: scheduled.append(delay)
    wizard._load_text_thread(_Rules(), "sample.pdf", 1)

    assert calls == ["sample.pdf"]
    assert scheduled == [0]
    assert "assay_display_to_key" not in NewRulesetWizard.__init__.__code__.co_varnames


def test_step_by_step_toolbar_routes_to_real_wizard() -> None:
    calls: list[str] = []
    host = GuideMixin.__new__(GuideMixin)
    host.on_open_wizard = lambda *, intent="new": calls.append(intent)

    host.open_step_by_step()

    assert calls == ["neutral"]


def test_guided_starts_ignore_loaded_and_selected_assays(monkeypatch) -> None:
    wizard_calls: list[dict[str, object]] = []
    host = ManageMixin.__new__(ManageMixin)
    host.current_draft_path = r"I:\rules\drafts\loaded.draft.json"
    host._dirty = False
    host._rules = object()
    host.assay_display_to_key = {"Assay A (1111)": "(1111)"}
    host._selected_inventory_row = lambda: {"kind": "active", "assay_key": "(1111)", "path": "rules/A.json"}
    monkeypatch.setattr(
        "rule_editor.manage_actions.NewRulesetWizard",
        lambda _master, **kwargs: wizard_calls.append(kwargs),
    )

    host.on_open_wizard(intent="neutral")
    host.on_open_wizard()

    assert [call["start_intent"] for call in wizard_calls] == ["neutral", "new"]
    assert all("initial_draft_path" not in call for call in wizard_calls)
    assert all("assay_display_to_key" not in call for call in wizard_calls)


def test_dirty_editor_is_resolved_before_guided_start(monkeypatch) -> None:
    wizard_calls: list[str] = []
    saved: list[bool] = []
    reloaded: list[str] = []
    errors: list[str] = []
    prompts: list[str] = []

    host = ManageMixin.__new__(ManageMixin)
    host.current_draft_path = r"I:\rules\drafts\loaded.draft.json"
    host._dirty = True
    host._rules = object()
    host.assay_display_to_key = {}
    host._dialog_parent = lambda: None
    host._save_meta_to_draft = lambda push_undo=False: saved.append(push_undo)
    host.on_load_draft_into_editor = lambda path: reloaded.append(path) or True
    monkeypatch.setattr(
        "rule_editor.manage_actions.NewRulesetWizard",
        lambda _master, **kwargs: wizard_calls.append(str(kwargs["start_intent"])),
    )
    monkeypatch.setattr(
        "rule_editor.manage_actions.messagebox.showerror",
        lambda _title, message, **_kwargs: errors.append(str(message)),
    )

    monkeypatch.setattr(
        "rule_editor.manage_actions.messagebox.askyesnocancel",
        lambda *_args, **_kwargs: prompts.append("cancel") or None,
    )
    host.on_open_wizard(intent="neutral")
    assert wizard_calls == []
    assert reloaded == []
    assert saved == []

    monkeypatch.setattr(
        "rule_editor.manage_actions.messagebox.askyesnocancel",
        lambda *_args, **_kwargs: False,
    )
    host.on_open_wizard(intent="neutral")
    assert reloaded == [r"I:\rules\drafts\loaded.draft.json"]
    assert wizard_calls == ["neutral"]

    host.on_load_draft_into_editor = lambda path: False
    host.on_open_wizard(intent="neutral")
    assert wizard_calls == ["neutral"]

    host._save_meta_to_draft = lambda push_undo=False: (_ for _ in ()).throw(RuntimeError("save failed"))
    monkeypatch.setattr(
        "rule_editor.manage_actions.messagebox.askyesnocancel",
        lambda *_args, **_kwargs: True,
    )
    host.on_open_wizard(intent="neutral")
    assert errors == ["save failed"]
    assert wizard_calls == ["neutral"]

    host._save_meta_to_draft = lambda push_undo=False: saved.append(bool(push_undo))
    host.on_open_wizard(intent="new")
    assert saved == [True]
    assert wizard_calls == ["neutral", "new"]


def test_same_draft_wizard_close_reloads_editor_from_file() -> None:
    reloaded: list[str] = []
    host = ManageMixin.__new__(ManageMixin)
    host.current_draft_path = r"I:\rules\drafts\same.draft.json"
    host.on_load_draft_into_editor = lambda path: reloaded.append(path) or True

    host._sync_editor_after_wizard(r"I:\rules\drafts\same.draft.json")
    host._sync_editor_after_wizard(r"I:\rules\drafts\other.draft.json")

    assert reloaded == [r"I:\rules\drafts\same.draft.json"]


def test_clone_dialog_never_overwrites_existing_or_active_target(monkeypatch) -> None:
    calls: list[dict[str, object]] = []
    infos: list[str] = []

    class _Rules:
        def clone_ruleset_to_draft(self, *args: object, **kwargs: object) -> dict[str, str]:
            calls.append(dict(kwargs))
            return {"status": "exists", "draft_path": "draft.json"}

    dialog = CloneRulesetDialog.__new__(CloneRulesetDialog)
    dialog._rules = _Rules()
    dialog._active_rows = [
        {"assay_key": "(1111)", "assay_name": "Source"},
        {"assay_key": "(2222)", "assay_name": "Active"},
    ]
    dialog._selected_source_key = lambda: "(1111)"
    dialog.var_target_key = _Var("(2222)")
    dialog.var_target_name = _Var("Target")
    dialog._on_completed = lambda result: calls.append({"completed": result})
    dialog.destroy = lambda: calls.append({"destroyed": True})
    monkeypatch.setattr(
        "rule_editor.clone_dialog.messagebox.showinfo",
        lambda _title, message, **_kwargs: infos.append(str(message)),
    )
    monkeypatch.setattr("rule_editor.clone_dialog.messagebox.showerror", lambda *args, **kwargs: None)

    dialog._on_submit()
    assert calls == []
    assert any("(2222)" in message for message in infos)

    dialog.var_target_key = _Var("(abcd)")
    dialog._on_submit()
    assert calls == [{"overwrite": False, "include_fields": True}]
    assert any("nicht geändert" in message for message in infos)


def test_manage_edit_active_uses_open_active_as_draft_and_confirms_existing(monkeypatch) -> None:
    calls: list[str] = []
    prompts: list[bool] = []

    class _Rules:
        def open_active_as_draft(self, assay_key: str) -> dict[str, str]:
            calls.append(assay_key)
            return {"status": "exists", "draft_path": "draft.json"}

        def clone_ruleset_to_draft(self, *args: object, **kwargs: object) -> dict[str, str]:
            raise AssertionError(args)

    host = ManageMixin()
    host._rules = _Rules()
    host._selected_inventory_row = lambda: {
        "kind": "active",
        "assay_key": "(1111)",
        "assay_name": "Assay",
        "path": "rules/Assay.json",
    }
    host.var_draft_path = _Var("")
    loaded: list[str] = []
    host.on_load_draft_into_editor = lambda *args: loaded.append(str(args[0] if args else host.var_draft_path.get())) or True
    host._set_hint = lambda text: None
    host._refresh_ruleset_overview = lambda: None
    monkeypatch.setattr("rule_editor.manage_actions.messagebox.showerror", lambda *args, **kwargs: None)

    monkeypatch.setattr(
        "rule_editor.manage_actions.messagebox.askyesno",
        lambda *_args, **_kwargs: prompts.append(False) or False,
    )
    host.on_manage_edit_selected()
    host.on_inventory_primary_action()
    assert calls == ["(1111)", "(1111)"]
    assert loaded == []

    monkeypatch.setattr(
        "rule_editor.manage_actions.messagebox.askyesno",
        lambda *_args, **_kwargs: prompts.append(True) or True,
    )
    host.on_manage_edit_selected()
    assert loaded == ["draft.json"]


def test_inventory_row_is_display_only() -> None:
    class _Item:
        kind = "active"
        display_type = "Aktiv"
        assay_key = "(1111)"
        assay_name = "Name"
        path = "rules/AssayA.json"
        ruleset_file = "AssayA.json"
        field_count = 3
        valid = True
        error = None

    assert _inventory_row(_Item()) == {
        "kind": "active",
        "display_type": "Aktiv",
        "assay_key": "(1111)",
        "assay_name": "Name",
        "path": "rules/AssayA.json",
        "ruleset_file": "AssayA.json",
        "field_count": 3,
        "valid": True,
        "error": None,
        "modified_at": "",
        "sha256": "",
        "read_only": False,
    }


def test_manage_edit_history_routes_to_open_history_as_draft(monkeypatch) -> None:
    calls: list[str] = []

    class _Rules:
        def open_history_as_draft(self, path: str) -> dict[str, str]:
            calls.append(path)
            return {"status": "created", "draft_path": "draft.json"}

        def open_inactive_as_draft(self, path: str) -> dict[str, str]:
            raise AssertionError(path)

        def clone_ruleset_to_draft(self, *args: object, **kwargs: object) -> dict[str, str]:
            raise AssertionError(args)

    host = ManageMixin()
    host._rules = _Rules()
    host._selected_inventory_row = lambda: {
        "kind": "history",
        "path": "rules/history/AssayA-stamp.json",
        "assay_key": "(1111)",
    }
    host.var_draft_path = _Var("")
    loaded: list[str] = []
    host.on_load_draft_into_editor = lambda *args: loaded.append(str(args[0] if args else host.var_draft_path.get())) or True
    host._set_hint = lambda text: None
    host._log = lambda text: None
    host._refresh_ruleset_overview = lambda: None
    monkeypatch.setattr("rule_editor.manage_actions.messagebox.showerror", lambda *args, **kwargs: None)

    host.on_manage_edit_selected()

    assert calls == ["rules/history/AssayA-stamp.json"]
    assert loaded == ["draft.json"]


def test_manage_edit_and_delete_leave_trash_unchanged() -> None:
    class _Rules:
        def open_history_as_draft(self, path: str) -> dict[str, str]:
            raise AssertionError(path)

        def open_inactive_as_draft(self, path: str) -> dict[str, str]:
            raise AssertionError(path)

        def clone_ruleset_to_draft(self, *args: object, **kwargs: object) -> dict[str, str]:
            raise AssertionError(args)

        def delete_inventory_item(self, *args: object, **kwargs: object) -> dict[str, str]:
            raise AssertionError(args)

    hints: list[str] = []
    host = ManageMixin()
    host._rules = _Rules()
    host._selected_inventory_row = lambda: {"kind": "trash", "path": "rules/trash/old.json"}
    host._set_hint = hints.append

    host.on_manage_edit_selected()
    host.on_manage_delete_selected()

    assert hints
    assert all("nur lesbar" in hint.lower() or "nur fuer drafts" in hint.lower() for hint in hints)


def test_manage_edit_history_exists_no_does_not_load_or_overwrite(monkeypatch) -> None:
    class _Rules:
        def open_history_as_draft(self, path: str) -> dict[str, str]:
            return {"status": "exists", "draft_path": "draft.json"}

    host = ManageMixin()
    host._rules = _Rules()
    host._selected_inventory_row = lambda: {
        "kind": "history",
        "path": "rules/history/AssayA-stamp.json",
    }
    host.var_draft_path = _Var("")
    loaded: list[str] = []
    host.on_load_draft_into_editor = lambda *args: loaded.append(str(args[0] if args else host.var_draft_path.get())) or True
    host._set_hint = lambda text: None
    host._log = lambda text: None
    host._refresh_ruleset_overview = lambda: None
    monkeypatch.setattr("rule_editor.manage_actions.messagebox.askyesno", lambda *args, **kwargs: False)
    monkeypatch.setattr("rule_editor.manage_actions.messagebox.showerror", lambda *args, **kwargs: None)

    host.on_manage_edit_selected()

    assert loaded == []
    assert host.var_draft_path.get() == ""


def test_inventory_context_menu_history_and_trash_are_non_mutating(monkeypatch) -> None:
    from types import SimpleNamespace

    menus: list[object] = []

    class _Menu:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            self.entries: list[dict[str, object]] = []
            menus.append(self)

        def add_command(self, **kwargs: object) -> None:
            self.entries.append(dict(kwargs))

        def tk_popup(self, *_args: object, **_kwargs: object) -> None:
            return None

        def grab_release(self) -> None:
            return None

    class _Tree:
        def identify_row(self, _y: object) -> str:
            return "row"

        def selection_set(self, _row_id: object) -> None:
            return None

        def focus(self, _row_id: object) -> None:
            return None

    monkeypatch.setattr("rule_editor.manage_actions.tk.Menu", _Menu)
    host = ManageMixin()
    host.tree_rulesets = _Tree()

    rows = {
        "active": {"kind": "active", "assay_key": "(1111)", "path": "rules/A.json"},
        "draft": {"kind": "draft", "assay_key": "(d)", "path": "rules/drafts/d.draft.json"},
        "inactive": {"kind": "inactive", "assay_key": "(i)", "path": "rules/inactive/i.json"},
        "history": {"kind": "history", "path": "rules/history/a.json"},
        "trash": {"kind": "trash", "path": "rules/trash/old.json", "read_only": True},
    }
    expected = {
        "active": [
            ("Als Entwurf bearbeiten", host.on_manage_edit_selected),
            ("Regel deaktivieren …", host.on_manage_deactivate_selected),
            ("Als neue Regel duplizieren …", host.on_open_clone_ruleset_dialog),
            ("Details anzeigen", host.on_show_inventory_details),
        ],
        "draft": [
            ("Entwurf weiterbearbeiten", host.on_manage_edit_selected),
            ("Entwurf in Papierkorb verschieben …", host.on_manage_delete_selected),
            ("Endgültig löschen (nur nie aktiviert) …", host.on_delete_never_active_selected),
            ("Details anzeigen", host.on_show_inventory_details),
        ],
        "inactive": [
            ("Als Entwurf wiederherstellen …", host.on_manage_edit_selected),
            ("In Papierkorb verschieben …", host.on_manage_delete_selected),
            ("Details anzeigen", host.on_show_inventory_details),
        ],
        "history": [
            ("Als Entwurf wiederherstellen …", host.on_manage_edit_selected),
            ("Details anzeigen", host.on_show_inventory_details),
        ],
        "trash": [("Details anzeigen", host.on_show_inventory_details)],
    }
    for kind, row in rows.items():
        host._inventory_by_iid = {"row": row}
        host._show_inventory_context_menu(SimpleNamespace(y=1, x_root=0, y_root=0))
        menu_pairs = [(entry.get("label"), entry.get("command")) for entry in menus[-1].entries]
        assert menu_pairs == expected[kind]
        host._selected_inventory_row = lambda row=row: row
        more = tk_menu = menus
        host.on_inventory_more_actions()
        assert [(entry.get("label"), entry.get("command")) for entry in more[-1].entries] == expected[kind]
        assert host._inventory_context_actions(row)[0][1] == expected[kind][0][1]
    trash_menu = [entry for entry in menus if [item.get("label") for item in entry.entries] == ["Details anzeigen"]][-1]
    assert trash_menu.entries[0]["command"] == host.on_show_inventory_details
    assert "state" not in trash_menu.entries[0] or trash_menu.entries[0].get("state") != "disabled"


def test_delete_never_active_requires_draft_confirmation_and_clears_loaded_editor(monkeypatch) -> None:
    calls: list[str] = []
    dialogs: list[str] = []

    class _Rules:
        def delete_never_active_ruleset(self, path: str) -> dict[str, str]:
            calls.append(path)
            if path.endswith("blocked.draft.json"):
                raise RuntimeError("ruleset_activation_trace")
            return {"status": "deleted", "draft_path": path}

        def delete_inventory_item(self, *args: object, **kwargs: object) -> dict[str, str]:
            raise AssertionError(args)

    host = ManageMixin()
    host._rules = _Rules()
    host.current_draft_path = r"I:\rules\drafts\keep.draft.json"
    host.var_draft_path = _Var(host.current_draft_path)
    host._dirty = True
    host._suspend_dirty_tracking = False
    host._refresh_ruleset_overview = lambda: dialogs.append("refresh")
    hints: list[str] = []
    host._set_hint = hints.append
    answers = {"yes": True, "typed": "(keep)"}

    def askyesno(*_args: object, **_kwargs: object) -> bool:
        dialogs.append("yesno")
        return answers["yes"]

    def askstring(*_args: object, **_kwargs: object) -> str | None:
        dialogs.append("string")
        return answers["typed"]

    monkeypatch.setattr("rule_editor.manage_actions.messagebox.askyesno", askyesno)
    monkeypatch.setattr("rule_editor.manage_actions.simpledialog.askstring", askstring)
    monkeypatch.setattr("rule_editor.manage_actions.messagebox.showerror", lambda *_a, **_k: dialogs.append("error"))

    host._selected_inventory_row = lambda: {"kind": "active", "assay_key": "(keep)", "path": "rules/A.json"}
    host.on_delete_never_active_selected()
    assert calls == []
    assert "yesno" not in dialogs

    host._selected_inventory_row = lambda: {"kind": "draft", "assay_key": "(keep)", "path": "rules/drafts/keep.draft.json"}
    answers["yes"] = False
    host.on_delete_never_active_selected()
    assert calls == []
    assert dialogs.count("string") == 0

    answers["yes"] = True
    answers["typed"] = None
    host.on_delete_never_active_selected()
    assert calls == []

    answers["typed"] = "wrong"
    host.on_delete_never_active_selected()
    assert calls == []
    assert host.current_draft_path == r"I:\rules\drafts\keep.draft.json"
    assert host._dirty is True

    answers["typed"] = "(keep)"
    host._selected_inventory_row = lambda: {
        "kind": "draft",
        "assay_key": "(keep)",
        "path": "rules/drafts/blocked.draft.json",
    }
    host.on_delete_never_active_selected()
    assert calls == ["rules/drafts/blocked.draft.json"]
    assert "error" in dialogs
    assert host.current_draft_path == r"I:\rules\drafts\keep.draft.json"

    loaded = r"I:\rules\drafts\keep.draft.json"
    host.current_draft_path = loaded
    host.var_draft_path.set(loaded)
    host._dirty = True
    host._selected_inventory_row = lambda: {"kind": "draft", "assay_key": "(keep)", "path": loaded}
    host.on_delete_never_active_selected()
    assert calls[-1] == loaded
    assert host.current_draft_path is None
    assert host.var_draft_path.get() == ""
    assert host._dirty is False
    assert "refresh" in dialogs


def test_recoverable_draft_discard_stays_on_trash_move(monkeypatch) -> None:
    calls: list[tuple[object, ...]] = []

    class _Rules:
        def delete_inventory_item(self, kind: str, path: str) -> dict[str, str]:
            calls.append((kind, path))
            return {"trash_path": "rules/trash/moved.json"}

        def delete_never_active_ruleset(self, path: str) -> dict[str, str]:
            raise AssertionError(path)

    host = ManageMixin()
    host._rules = _Rules()
    host._selected_inventory_row = lambda: {"kind": "draft", "path": "rules/drafts/a.draft.json", "assay_key": "(a)"}
    host._set_hint = lambda _text: None
    host._log = lambda _text: None
    host._refresh_ruleset_overview = lambda: None
    monkeypatch.setattr("rule_editor.manage_actions.messagebox.askyesno", lambda *_a, **_k: True)
    host.on_manage_delete_selected()
    assert calls == [("draft", "rules/drafts/a.draft.json")]


def test_inventory_details_are_read_only(monkeypatch) -> None:
    shown: list[str] = []

    class _Rules:
        def delete_never_active_ruleset(self, path: str) -> dict[str, str]:
            raise AssertionError(path)

        def delete_inventory_item(self, *args: object) -> dict[str, str]:
            raise AssertionError(args)

        def open_active_as_draft(self, key: str) -> dict[str, str]:
            raise AssertionError(key)

    host = ManageMixin()
    host._rules = _Rules()
    host._selected_inventory_row = lambda: {
        "kind": "trash",
        "display_type": "Papierkorb",
        "assay_key": "(old)",
        "assay_name": "Alt",
        "path": "rules/trash/old.json",
        "ruleset_file": "old.json",
        "sha256": "abc123",
        "field_count": 2,
        "modified_at": "2026-01-01",
        "valid": False,
        "read_only": True,
        "error": "broken",
    }
    monkeypatch.setattr(
        "rule_editor.manage_actions.messagebox.showinfo",
        lambda _title, message, **_kwargs: shown.append(str(message)),
    )
    host.on_show_inventory_details()
    text = shown[0]
    assert "rules/trash/old.json" in text
    assert "abc123" in text
    assert "broken" in text
    assert "Nur lesen: True" in text


class _SwitchRules:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def draft_path_for_assay(self, assay_key: str) -> str:
        return f"rules/drafts/{assay_key}.draft.json"

    def open_active_as_draft(self, assay_key: str) -> dict[str, str]:
        self.calls.append(("active", assay_key))
        return {"status": "created", "draft_path": self.draft_path_for_assay(assay_key)}

    def open_history_as_draft(self, path: str) -> dict[str, str]:
        self.calls.append(("history", path))
        return {"status": "created", "draft_path": "rules/drafts/(h).draft.json"}

    def open_inactive_as_draft(self, path: str) -> dict[str, str]:
        self.calls.append(("inactive", path))
        return {"status": "created", "draft_path": "rules/drafts/(i).draft.json"}


def _switch_host(rules: _SwitchRules) -> ManageMixin:
    host = ManageMixin()
    host._rules = rules
    host.current_draft_path = r"I:\rules\drafts\keep.draft.json"
    host.var_draft_path = _Var(host.current_draft_path)
    host.var_new_assay_key = _Var("(keep)")
    host.var_new_assay_name = _Var("Keep")
    host._dirty = True
    host._undo_stack = [{"assay_key": "(keep)"}]
    host._redo_stack = [{"assay_key": "redo"}]
    host.pages: list[str] = []
    host.loaded: list[str] = []
    host.saved: list[bool] = []
    host._show_page = lambda page: host.pages.append(page)
    host._set_hint = lambda _text: None
    host._log = lambda _text: None
    host._refresh_ruleset_overview = lambda: None
    host._reload_assays = lambda: None
    def _load(*args: object) -> bool:
        path = str(args[0]) if args else host.var_draft_path.get()
        host.var_draft_path.set(path)
        host.loaded.append(path)
        host._dirty = False
        return True

    host.on_load_draft_into_editor = _load

    def save(*, push_undo: bool = False) -> dict[str, str]:
        host.saved.append(push_undo)
        host._dirty = False
        return {"assay_key": "(keep)"}

    host._save_meta_to_draft = save
    return host


def test_dirty_switch_uses_one_guard_before_backend(monkeypatch) -> None:
    rules = _SwitchRules()
    host = _switch_host(rules)
    prompts: list[str] = []

    def ask(*_args: object, **_kwargs: object):
        prompts.append("ask")
        return None

    monkeypatch.setattr("rule_editor.manage_actions.messagebox.askyesnocancel", ask)
    monkeypatch.setattr("rule_editor.manage_actions.messagebox.askyesno", lambda *_a, **_k: True)
    monkeypatch.setattr("rule_editor.manage_actions.messagebox.showerror", lambda *_a, **_k: None)

    host._selected_inventory_row = lambda: {"kind": "active", "assay_key": "(other)", "path": "rules/A.json"}
    host.on_manage_edit_selected()
    host._selected_inventory_row = lambda: {"kind": "history", "assay_key": "(h)", "path": "rules/history/h.json"}
    host.on_manage_edit_selected()
    host._selected_inventory_row = lambda: {"kind": "inactive", "assay_key": "(i)", "path": "rules/inactive/i.json"}
    host.on_manage_edit_selected()
    host._selected_inventory_row = lambda: {"kind": "draft", "assay_key": "(d)", "path": "rules/drafts/other.draft.json"}
    host.on_manage_edit_selected()
    assert prompts == ["ask", "ask", "ask", "ask"]
    assert rules.calls == []
    assert host.loaded == []
    assert host.current_draft_path == r"I:\rules\drafts\keep.draft.json"
    assert host._dirty is True

    host._selected_inventory_row = lambda: {
        "kind": "draft",
        "assay_key": "(keep)",
        "path": host.current_draft_path,
    }
    host.on_manage_edit_selected()
    assert prompts == ["ask", "ask", "ask", "ask"]
    assert host.loaded == []
    assert host.pages == ["workspace"]

    monkeypatch.setattr("rule_editor.manage_actions.messagebox.askyesnocancel", lambda *_a, **_k: False)
    host._selected_inventory_row = lambda: {"kind": "draft", "path": "rules/drafts/other.draft.json"}
    host.on_manage_edit_selected()
    assert host.saved == []
    assert host._dirty is False
    assert host.loaded == ["rules/drafts/other.draft.json"]

    host._dirty = True
    host.current_draft_path = r"I:\rules\drafts\keep.draft.json"
    monkeypatch.setattr("rule_editor.manage_actions.messagebox.askyesnocancel", lambda *_a, **_k: True)
    host._selected_inventory_row = lambda: {"kind": "active", "assay_key": "(other)", "path": "rules/A.json"}
    host.on_manage_edit_selected()
    assert host.saved == [True]
    assert rules.calls == [("active", "(other)")]
    assert host.loaded[-1] == "rules/drafts/(other).draft.json"

    def fail_save(*, push_undo: bool = False) -> dict[str, str]:
        host.saved.append(push_undo)
        raise RuntimeError("save failed")

    host._save_meta_to_draft = fail_save
    host._dirty = True
    host.current_draft_path = r"I:\rules\drafts\keep.draft.json"
    before = list(host.loaded)
    host._selected_inventory_row = lambda: {"kind": "draft", "path": "rules/drafts/blocked.draft.json"}
    host.on_manage_edit_selected()
    assert host.loaded == before
    assert host.current_draft_path == r"I:\rules\drafts\keep.draft.json"
    assert host._dirty is True


def test_clone_and_wizard_callbacks_use_the_same_switch_guard(monkeypatch) -> None:
    rules = _SwitchRules()
    host = _switch_host(rules)
    monkeypatch.setattr("rule_editor.manage_actions.messagebox.askyesnocancel", lambda *_a, **_k: None)
    monkeypatch.setattr("rule_editor.manage_actions.messagebox.showerror", lambda *_a, **_k: None)
    host._on_clone_completed({"status": "created", "draft_path": "rules/drafts/clone.draft.json"})
    host._wizard_open_draft("rules/drafts/wizard.draft.json")
    host.on_activate = lambda: host.loaded.append("activate")
    host._wizard_activate_draft("rules/drafts/wizard-activate.draft.json")
    assert host.loaded == []
    assert host.current_draft_path == r"I:\rules\drafts\keep.draft.json"
    assert host._dirty is True


def test_recoverable_discard_clears_loaded_draft_and_keeps_state_on_error(monkeypatch) -> None:
    class _Rules:
        def delete_inventory_item(self, kind: str, path: str) -> dict[str, str]:
            if path.endswith("broken.draft.json"):
                raise RuntimeError("move failed")
            return {"trash_path": "rules/trash/moved.json"}

        def delete_never_active_ruleset(self, path: str) -> dict[str, str]:
            raise AssertionError(path)

    host = ManageMixin()
    host._rules = _Rules()
    loaded = r"I:\rules\drafts\keep.draft.json"
    host.current_draft_path = loaded
    host.var_draft_path = _Var(loaded)
    host.var_new_assay_key = _Var("(keep)")
    host.var_new_assay_name = _Var("Keep")
    host.fields_data = [{"key": "A"}]
    host._dirty = True
    host._undo_stack = [{"k": 1}]
    host._redo_stack = [{"k": 2}]
    host.pages: list[str] = []
    host.hints: list[str] = []
    host._show_page = lambda page: host.pages.append(page)
    host._set_hint = host.hints.append
    host._log = lambda _text: None
    host.tree_regex_results = object()
    host._regex_result_data = {"regex_1": {"status": "HIT"}}
    host._regex_result_counter = 4
    host._field_marking_data = {"A": {"value": "alt"}}
    host._field_marking_tags = {"field::A"}
    host._visible_marking_keys = {"A"}
    host._active_marking_key = "A"

    def _clear_regex() -> None:
        host._regex_result_data.clear()
        host._set_hint("Regex-Ergebnisliste geleert.")

    host._clear_regex_results = _clear_regex
    host._refresh_ruleset_overview = lambda: None
    monkeypatch.setattr("rule_editor.manage_actions.messagebox.askyesno", lambda *_a, **_k: True)
    monkeypatch.setattr("rule_editor.manage_actions.messagebox.showerror", lambda *_a, **_k: None)

    host._selected_inventory_row = lambda: {"kind": "draft", "path": loaded, "assay_key": "(keep)"}
    host.on_manage_delete_selected()
    assert host.current_draft_path is None
    assert host.var_draft_path.get() == ""
    assert host.var_new_assay_key.get() == ""
    assert host.fields_data == []
    assert host._dirty is False
    assert host._undo_stack == []
    assert host._redo_stack == []
    assert host.pages == ["inventory"]
    assert host._regex_result_data == {}
    assert host._regex_result_counter == 0
    assert host._field_marking_data == {}
    assert host._field_marking_tags == set()
    assert host._visible_marking_keys == set()
    assert host._active_marking_key is None
    assert host.hints[-1].startswith("Eintrag nach rules/trash/")
    assert "Regex-Ergebnisliste geleert." in host.hints

    host.current_draft_path = loaded
    host.var_draft_path.set(loaded)
    host.var_new_assay_key.set("(keep)")
    host.fields_data = [{"key": "A"}]
    host._dirty = True
    host._undo_stack = [{"k": 1}]
    host.pages.clear()
    host._selected_inventory_row = lambda: {"kind": "draft", "path": "rules/drafts/broken.draft.json"}
    host.on_manage_delete_selected()
    assert host.current_draft_path == loaded
    assert host.var_new_assay_key.get() == "(keep)"
    assert host.fields_data == [{"key": "A"}]
    assert host._dirty is True
    assert host._undo_stack == [{"k": 1}]
    assert host.pages == []


def test_discard_keeps_editor_when_target_load_fails(monkeypatch) -> None:
    rules = _SwitchRules()
    host = _switch_host(rules)
    host.var_new_assay_key.set("(keep)")
    notes: list[str] = []
    host._set_hint = notes.append
    host._log = lambda text: notes.append(f"log:{text}")

    def fail_load(*_args: object) -> bool:
        host.var_draft_path.set("rules/drafts/broken.draft.json")
        host.current_draft_path = "rules/drafts/broken.draft.json"
        return False

    host.on_load_draft_into_editor = fail_load
    monkeypatch.setattr("rule_editor.manage_actions.messagebox.askyesnocancel", lambda *_a, **_k: False)
    monkeypatch.setattr("rule_editor.manage_actions.messagebox.showerror", lambda *_a, **_k: None)
    host._selected_inventory_row = lambda: {"kind": "draft", "path": "rules/drafts/broken.draft.json"}
    host.on_manage_edit_selected()
    assert host.current_draft_path == r"I:\rules\drafts\keep.draft.json"
    assert host.var_draft_path.get() == r"I:\rules\drafts\keep.draft.json"
    assert host._dirty is True
    assert host.var_new_assay_key.get() == "(keep)"
    assert notes == []


def test_discard_keeps_editor_when_restore_backend_fails(monkeypatch) -> None:
    class _Rules(_SwitchRules):
        def open_active_as_draft(self, assay_key: str) -> dict[str, str]:
            raise RuntimeError("restore failed")

    host = _switch_host(_Rules())
    host.var_new_assay_key.set("(keep)")
    monkeypatch.setattr("rule_editor.manage_actions.messagebox.askyesnocancel", lambda *_a, **_k: False)
    monkeypatch.setattr("rule_editor.manage_actions.messagebox.showerror", lambda *_a, **_k: None)
    host._selected_inventory_row = lambda: {"kind": "active", "assay_key": "(other)", "path": "rules/A.json"}
    host.on_manage_edit_selected()
    assert host.loaded == []
    assert host.current_draft_path == r"I:\rules\drafts\keep.draft.json"
    assert host.var_draft_path.get() == r"I:\rules\drafts\keep.draft.json"
    assert host._dirty is True
    assert host.var_new_assay_key.get() == "(keep)"


def test_discard_then_declined_existing_draft_stays_dirty(monkeypatch) -> None:
    class _Rules(_SwitchRules):
        def open_history_as_draft(self, path: str) -> dict[str, str]:
            return {"status": "exists", "draft_path": "rules/drafts/existing.draft.json"}

    host = _switch_host(_Rules())
    monkeypatch.setattr("rule_editor.manage_actions.messagebox.askyesnocancel", lambda *_a, **_k: False)
    monkeypatch.setattr("rule_editor.manage_actions.messagebox.askyesno", lambda *_a, **_k: False)
    monkeypatch.setattr("rule_editor.manage_actions.messagebox.showerror", lambda *_a, **_k: None)
    host._selected_inventory_row = lambda: {
        "kind": "history",
        "assay_key": "(h)",
        "path": "rules/history/h.json",
    }
    host.on_manage_edit_selected()
    assert host.loaded == []
    assert host.current_draft_path == r"I:\rules\drafts\keep.draft.json"
    assert host.var_draft_path.get() == r"I:\rules\drafts\keep.draft.json"
    assert host._dirty is True


def test_failed_callback_load_skips_success_and_activate(monkeypatch) -> None:
    host = _switch_host(_SwitchRules())
    notes: list[str] = []
    host._set_hint = notes.append
    host._log = notes.append
    host.on_load_draft_into_editor = lambda *_args: False
    activated: list[str] = []
    host.on_activate = lambda: activated.append("activate")
    monkeypatch.setattr("rule_editor.manage_actions.messagebox.askyesnocancel", lambda *_a, **_k: False)
    monkeypatch.setattr("rule_editor.manage_actions.messagebox.showerror", lambda *_a, **_k: None)
    host._wizard_activate_draft("rules/drafts/missing.draft.json")
    host._wizard_open_draft("rules/drafts/missing.draft.json")
    host._on_clone_completed({"status": "created", "draft_path": "rules/drafts/missing.draft.json"})
    assert activated == []
    assert notes == []
    assert host._dirty is True
    assert host.current_draft_path == r"I:\rules\drafts\keep.draft.json"
    assert host.var_draft_path.get() == r"I:\rules\drafts\keep.draft.json"
