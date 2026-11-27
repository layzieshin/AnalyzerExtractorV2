"""Phase 6: Inventar/Arbeitsbereich-Shell und dreispaltiges Layout."""
from __future__ import annotations

import ast
import sys
import tkinter as tk
from tkinter import ttk
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
VIEW_MODULES = (
    "rule_editor/ui_builder.py",
    "rule_editor/toolbar.py",
    "rule_editor/inventory_view.py",
    "rule_editor/workspace.py",
    "rule_editor/field_list_panel.py",
    "rule_editor/report_panel.py",
    "rule_editor/field_settings_panel.py",
    "rule_editor/advanced_view.py",
)
PRIMARY_LABELS = (
    "Neue Regel aus PDF",
    "Regel auswählen",
    "Weitere Aktionen",
    "Aktualisieren",
    "Speichern",
    "Regel testen",
    "Geprüfte Regel aktivieren",
    "Abschluss prüfen",
    "Später weiterbearbeiten",
    "Muster aus Markierung",
    "Regex testen",
    "Regeldetails",
)
CONTRACT_ATTRS = (
    "tree_rulesets",
    "tree_fields",
    "txt_block",
    "txt_log",
    "txt_field_preview",
    "list_validation",
    "tree_cols",
    "tree_regex_results",
    "lbl_loaded_assay_key",
    "lbl_loaded_assay_name",
    "frame_marking_panel",
    "ent_field_regex",
    "ent_marking_regex",
    "workspace_panes",
)


@pytest.mark.parametrize("width,height,scale", [(1380, 760, 1.0), (960, 620, 1.25)])
def test_direct_workplace_single_grid_and_builder_all_controls_native(tmp_path, width, height, scale):
    from src.application.api import RuleSuiteController
    from interfaces.tk.desktop_theme import configure_desktop_theme
    from rule_editor.editor_workspace import RuleEditorWorkspace
    root = tk.Tk()
    previous_scaling = root.tk.call("tk", "scaling")
    workspace = None
    try:
        root.tk.call("tk", "scaling", 96 / 72 * scale)
        configure_desktop_theme(root)
        root.geometry(f"{width}x{height}+20+20")
        project = _isolated_root(tmp_path)
        rules = RuleSuiteController(project)
        draft = rules.create_blank_draft("(42d4)", "Anti-Centromeres IgG")
        rules.add_field(draft, "PC_IST", r"PC IST:\s*([\d,]+)")
        workspace = RuleEditorWorkspace(root, project, rules=rules, initial_inventory=(), embedded=True)
        workspace.pack(fill="both", expand=True)
        assert workspace.on_load_draft_into_editor(draft)
        root.update()
        assert workspace._select_field("PC_IST")
        workspace.var_field_regex.set("LOCAL UNSAVED")
        workspace.assay_block_text = "PC IST: 104,2"
        assert workspace.tree_marking_legend is None
        assert workspace.tree_fields.item(workspace.tree_fields.get_children()[0], "values")[0] == "PC_IST"
        assert not isinstance(workspace.report_notebook, ttk.Notebook)
        y = workspace.btn_regex_builder.winfo_rooty()
        scroll = workspace.field_settings_scrollable._canvas.yview()
        button = workspace.btn_regex_builder
        button.event_generate("<ButtonPress-1>", x=button.winfo_width() // 2, y=button.winfo_height() // 2)
        root.update()
        button.event_generate("<ButtonRelease-1>", x=button.winfo_width() // 2, y=button.winfo_height() // 2)
        root.update()
        popup = workspace._regex_builder_popup
        assert y == button.winfo_rooty() and scroll == workspace.field_settings_scrollable._canvas.yview()
        assert len(popup._builder_inputs) == 20
        for widget in (list(popup._builder_inputs.values()) + [popup.btn_build, popup.btn_test, popup.btn_accept]):
            assert widget.winfo_viewable()
        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)
        for widget in descendants(popup):
            if widget.winfo_class() not in {"TEntry", "TCombobox", "TCheckbutton", "TButton", "TLabel", "Text"}:
                continue
            assert widget.winfo_viewable(), (widget, widget.winfo_class())
            x1, y1 = widget.winfo_rootx(), widget.winfo_rooty()
            x2, y2 = x1 + widget.winfo_width(), y1 + widget.winfo_height()
            parent = widget.master
            while parent is not None:
                assert x1 >= parent.winfo_rootx() - 1 and y1 >= parent.winfo_rooty() - 1, (widget, parent)
                assert x2 <= parent.winfo_rootx() + parent.winfo_width() + 1 and y2 <= parent.winfo_rooty() + parent.winfo_height() + 1, (widget, parent, (x1, y1, x2, y2))
                if parent is popup:
                    break
                parent = parent.master
        before = Path(draft).read_bytes()
        popup.var_left_marker.set("PC IST:")
        popup.var_value_type.set("decimal")
        popup.var_expected.set("104,2")
        popup._test_regex()
        assert popup._last_result["test"]["value"] == "104,2"
        popup._accept()
        assert workspace.var_field_regex.get() != "LOCAL UNSAVED"
        assert Path(draft).read_bytes() == before
    finally:
        root.tk.call("tk", "scaling", previous_scaling)
        if workspace is not None:
            workspace.destroy()
        root.destroy()


def _imports(rel_path: str) -> list[str]:
    tree = ast.parse((PROJECT_ROOT / rel_path).read_text(encoding="utf-8-sig"), filename=rel_path)
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.append(node.module)
    return found


def _isolated_root(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    rules = root / "rules"
    rules.mkdir(parents=True)
    (rules / "drafts").mkdir()
    (rules / "inactive").mkdir()
    (rules / "index.json").write_text('{"assays": []}', encoding="utf-8")
    return root


def _walk_entries(widget: tk.Misc) -> list[tk.Entry]:
    found: list[tk.Entry] = []
    for child in widget.winfo_children():
        if isinstance(child, tk.Entry):
            found.append(child)
        found.extend(_walk_entries(child))
    return found


def _button_texts(widget: tk.Misc) -> list[str]:
    texts: list[str] = []
    for child in widget.winfo_children():
        if isinstance(child, (tk.Button, ttk.Button)):
            texts.append(str(child.cget("text")))
        texts.extend(_button_texts(child))
    return texts


def _buttons(widget: tk.Misc) -> list[tk.Button]:
    found: list[tk.Button] = []
    for child in widget.winfo_children():
        if isinstance(child, tk.Button):
            found.append(child)
        found.extend(_buttons(child))
    return found


def _pane_of(widget: tk.Misc, pane_names: set[str]) -> str | None:
    current: tk.Misc | None = widget
    while current is not None:
        if str(current) in pane_names:
            return str(current)
        current = getattr(current, "master", None)
    return None


def _open_editor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from rule_editor_main import RuleEditorWindow

    root = _isolated_root(tmp_path)
    monkeypatch.setenv("ARE_HOME", str(root))
    try:
        editor = RuleEditorWindow(project_root=root)
    except tk.TclError as exc:
        pytest.skip(f"Tk not available: {exc}")
    return editor


def test_shared_workspace_embeds_once_without_root_calls_or_duplicate_inventory_reads(tmp_path):
    from types import SimpleNamespace
    from interfaces.tk.desktop_theme import configure_desktop_theme
    from interfaces.tk.views.rules_view import RulesView
    from rule_editor.editor_workspace import RuleEditorWorkspace

    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk not available: {exc}")
    root.withdraw()
    configure_desktop_theme(root)
    rules = SimpleNamespace(list_inventory=lambda **_k: pytest.fail("loaded inventory must be reused"))
    view = RulesView(root, on_open_rule_editor=lambda: None, on_refresh=lambda: None, on_validate=lambda: None)
    item = SimpleNamespace(kind="active", assay_key="(1111)", assay_name="Actual configured full assay name",
        path=str(tmp_path / "rules" / "A.json"), ruleset_file="A.json", valid=True, field_count=2)
    try:
        view.render_inventory((item,))
        view.bind_editor(rules, tmp_path)
        editor = view._editor
        view.bind_editor(rules, tmp_path)
        assert view._editor is editor and isinstance(editor, RuleEditorWorkspace) and isinstance(editor, ttk.Frame)
        assert editor.winfo_toplevel() is root and editor._rules is rules
        assert view._tree is editor.tree_rulesets and len(editor.tree_rulesets.get_children()) == 1
        assert editor.tree_rulesets.set(editor.tree_rulesets.get_children()[0], "name") == item.assay_name
        assert editor._task_runner.active_keys() == frozenset()
        editor.inventory_filter_vars["active"].set(False)
        editor._on_inventory_filter_changed()
        assert editor.tree_rulesets.get_children() == ()
        editor._select_all_inventory_filters()
        assert len(editor.tree_rulesets.get_children()) == 1
        assert view.prepare_leave()
    finally:
        root.destroy()


def test_shared_workspace_shortcuts_and_close_are_local_and_release_owned_callbacks(tmp_path):
    from types import SimpleNamespace
    from interfaces.tk.desktop_theme import configure_desktop_theme
    from rule_editor.editor_workspace import RuleEditorWorkspace

    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk not available: {exc}")
    root.withdraw()
    configure_desktop_theme(root)
    outside = tk.Entry(root)
    editor = RuleEditorWorkspace(root, tmp_path, rules=SimpleNamespace(), initial_inventory=())
    try:
        tag, timer, runner = editor._shortcut_tag, editor._autosave_after_id, editor._task_runner
        assert tag in editor.ent_field_regex.bindtags() and tag not in outside.bindtags()
        assert root.bind("<Control-z>") == "" and editor._dialog_parent() is root
        editor.destroy()
        editor.destroy()
        assert root.winfo_exists() and outside.winfo_exists() and runner.shutdown
        assert root.bind_class(tag, "<Control-z>") == ""
        with pytest.raises(tk.TclError):
            root.tk.call("after", "info", timer)
    finally:
        root.destroy()


def _proof_editor(tmp_path, *, embedded=False):
    from interfaces.tk.desktop_theme import configure_desktop_theme
    from rule_editor.editor_workspace import RuleEditorWorkspace
    from src.application.api import DesktopSettings, RuleSuiteController
    from test_rulesuite import _setup_project, _v2_draft, _v2_pdf

    project = _setup_project(tmp_path)
    draft = _v2_draft(project)
    pdf = _v2_pdf(project / "chosen.pdf")
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk not available: {exc}")
    root.withdraw()
    configure_desktop_theme(root)
    rules = RuleSuiteController(project, settings_provider=lambda: DesktopSettings("sqlite", str(project / "missing.sqlite3")))
    editor = RuleEditorWorkspace(root, project, rules=rules, initial_inventory=(), embedded=embedded)
    editor.on_load_draft_into_editor(draft)
    editor.var_pdf.set(str(pdf))
    return root, editor, rules, Path(draft), pdf


def _finish_editor_tasks(root, editor):
    import time

    deadline = time.monotonic() + 10
    while editor._task_runner.active_keys() and time.monotonic() < deadline:
        root.update()
        time.sleep(0.01)
    root.update()
    assert not editor._task_runner.active_keys() and not editor._busy


def test_shared_workspace_rule_test_uses_one_pdf_off_ui_and_transient_real_values(tmp_path):
    import threading

    root, editor, rules, draft, pdf = _proof_editor(tmp_path)
    main_thread, calls = threading.get_ident(), []
    original = rules.create_authoring_proof

    def proof(*args, **kwargs):
        assert threading.get_ident() != main_thread
        calls.append((args, kwargs))
        return original(*args, **kwargs)

    rules.create_authoring_proof = proof
    try:
        editor.on_preview()
        assert str(editor.btn_activate.cget("state")) == "disabled"
        _finish_editor_tasks(root, editor)
        assert calls == [((("(1111)", str(draft), str(pdf))), {})]
        assert editor._proof_result["status"] == "ready"
        assert editor.lbl_primary_result.cget("text") == "Bestanden"
        assert editor.lbl_secondary_result.cget("text") == "Offen"
        assert editor.var_proof_detail.get() == "Einmal geprüft – Zweitprüfung noch offen"
        values = [editor.tree_authoring_values.item(key, "values") for key in editor.tree_authoring_values.get_children()]
        assert ("test", "RAW_ONLY_932742", "Nicht geprüft") in values
        assert str(editor.btn_activate.cget("state")) == "normal"
        editor.var_pdf.set(str(pdf.with_name("other.pdf")))
        assert editor._proof_result is None and editor.tree_authoring_values.get_children() == ()
        assert str(editor.btn_activate.cget("state")) == "disabled" and len(calls) == 1
        assert not (draft.parents[2] / "missing.sqlite3").exists()
    finally:
        root.destroy()


@pytest.mark.parametrize("change", ["pdf_aba", "draft", "scope"])
def test_shared_workspace_pending_rule_test_never_displays_old_choice_or_reenables_activation(tmp_path, change):
    import threading

    root, editor, rules, draft, pdf = _proof_editor(tmp_path)
    done, release, calls = threading.Event(), threading.Event(), []
    original = rules.create_authoring_proof

    def proof(*args):
        result = original(*args)
        calls.append(args)
        done.set()
        assert release.wait(5)
        return result

    rules.create_authoring_proof = proof
    try:
        editor.on_preview()
        assert done.wait(3)
        if change == "pdf_aba":
            editor.var_pdf.set(str(pdf.with_name("other.pdf")))
            editor.var_pdf.set(str(pdf))
        elif change == "draft":
            other = draft.with_name("other.draft.json")
            other.write_bytes(draft.read_bytes())
            editor.on_load_draft_into_editor(str(other))
        else:
            editor.invalidate_context()
        release.set()
        _finish_editor_tasks(root, editor)
        assert editor._proof_result is None and editor.tree_authoring_values.get_children() == ()
        assert str(editor.btn_activate.cget("state")) == "disabled" and len(calls) == 1
        editor.on_preview()
        _finish_editor_tasks(root, editor)
        assert len(calls) == 2 and editor._proof_result["status"] == "ready"
        assert str(editor.btn_activate.cget("state")) == "normal"
    finally:
        release.set()
        root.destroy()


def test_shared_authoring_controls_render_without_controller_reads(tmp_path):
    root, editor, rules, _draft, _pdf = _proof_editor(tmp_path)
    try:
        editor.on_preview()
        _finish_editor_tasks(root, editor)
        for name in ("draft_content_revision", "load_draft", "verify_authoring_proof", "diff_draft_vs_active"):
            setattr(rules, name, lambda *_a, **_k: pytest.fail("rendering must not read files"))
        for _ in range(3):
            editor._sync_authoring_controls()
            assert editor.authoring_target_ready(editor._authoring_target(), origin=editor)
        assert str(editor.btn_activate.cget("state")) == "normal"
    finally:
        root.destroy()


def test_shared_inventory_integrity_action_uses_same_controller_off_tk(tmp_path):
    import threading

    root, editor, rules, draft, _pdf = _proof_editor(tmp_path)
    calls, main_thread = [], threading.get_ident()
    original = rules.validate_rules_integrity
    before = draft.read_bytes()

    def validate():
        assert threading.get_ident() != main_thread
        calls.append("integrity")
        return original()

    rules.validate_rules_integrity = validate
    try:
        editor._request_inventory_integrity()
        _finish_editor_tasks(root, editor)
        assert calls == ["integrity"] and editor.var_hint.get().startswith("Integrität:")
        assert draft.read_bytes() == before
    finally:
        root.destroy()


def test_shared_authoring_activation_is_explicit_once_and_off_tk(tmp_path, monkeypatch):
    import threading

    root, editor, rules, draft, _pdf = _proof_editor(tmp_path)
    main_thread, calls, confirmations = threading.get_ident(), [], []
    try:
        editor.on_preview()
        _finish_editor_tasks(root, editor)
        for name in ("verify_authoring_proof", "diff_draft_vs_active", "activate_draft"):
            original = getattr(rules, name)

            def call(*args, _name=name, _original=original, **kwargs):
                assert threading.get_ident() != main_thread
                calls.append((_name, args, kwargs))
                return _original(*args, **kwargs)

            setattr(rules, name, call)
        monkeypatch.setattr("rule_editor.release_actions.messagebox.askyesno", lambda *a, **k: confirmations.append(a) or True)
        # A stale GUI inventory cannot decide creation/update.
        editor.known_assay_keys.clear()
        editor.on_activate()
        editor.on_activate()
        _finish_editor_tasks(root, editor)
        assert len(confirmations) == 1
        commits = [call for call in calls if call[0] == "activate_draft"]
        assert len(commits) == 1 and commits[0][1] == ("(1111)", str(draft))
        assert commits[0][2]["assay_name"] == "Assay A" and commits[0][2]["expected_mode"] == "update"
        assert commits[0][2]["authoring_proof"]["attempt_id"]
        assert editor._proof_result is None
    finally:
        root.destroy()


def test_shared_authoring_confirm_cannot_commit_a_replaced_proof(tmp_path, monkeypatch):
    import threading

    root, editor, rules, draft, pdf = _proof_editor(tmp_path)
    errors, confirmations = [], []
    try:
        editor.on_preview()
        _finish_editor_tasks(root, editor)
        active = rules.project_root / "rules" / "AssayA.json"
        before = active.read_bytes()

        def confirm(*args, **kwargs):
            confirmations.append(args)
            # Simulate a second editor completing a new valid attempt while
            # the first editor's native confirmation is open.
            worker = threading.Thread(target=lambda: rules.create_authoring_proof("(1111)", str(draft), str(pdf)))
            worker.start()
            worker.join(5)
            assert not worker.is_alive()
            return True

        monkeypatch.setattr("rule_editor.release_actions.messagebox.askyesno", confirm)
        monkeypatch.setattr("rule_editor.release_actions.messagebox.showerror", lambda *a, **k: errors.append(a))
        editor.on_activate()
        _finish_editor_tasks(root, editor)
        assert len(confirmations) == 1 and errors and "attempt_changed" in str(errors)
        assert active.read_bytes() == before and not (rules.project_root / "rules" / "history").exists()
    finally:
        root.destroy()


def test_wizard_uses_shared_one_pdf_test_then_same_explicit_activation(tmp_path, monkeypatch):
    from rule_editor.wizard import NewRulesetWizard
    import threading

    root, editor, rules, draft, pdf = _proof_editor(tmp_path)
    wizard, calls, activations = None, [], []
    original = rules.create_authoring_proof
    main_thread = threading.get_ident()

    def proof(*args, **kwargs):
        assert threading.get_ident() != main_thread
        calls.append((args, kwargs))
        return original(*args, **kwargs)

    rules.create_authoring_proof = proof
    monkeypatch.setattr("rule_editor.release_actions.messagebox.askyesno", lambda *a, **k: True)
    original_activate = rules.activate_draft
    rules.activate_draft = lambda *a, **k: activations.append((a, k)) or original_activate(*a, **k)
    try:
        root.deiconify()
        wizard = NewRulesetWizard(editor, rules, initial_draft_path=str(draft), proof_owner=editor,
            on_session_closed=editor._sync_editor_after_wizard, on_activate_requested=editor._wizard_activate_draft)
        assert str(wizard.transient()) == str(root)
        assert not hasattr(wizard, "var_reference_pdf")
        wizard.var_pdf.set(str(pdf))
        wizard._show_step(3)
        wizard._on_rule_test()
        _finish_editor_tasks(root, editor)
        assert len(calls) == 1 and calls[0][1] == {} and calls[0][0] == ("(1111)", str(draft), str(pdf))
        assert wizard.lbl_primary_result.cget("text") == "Bestanden"
        assert activations == []
        wizard.var_finish_action.set("activate")
        wizard._finish()
        _finish_editor_tasks(root, editor)
        assert wizard._closed and len(calls) == 1 and len(activations) == 1
    finally:
        if wizard is not None and not wizard._closed:
            wizard._shutdown(None)
        root.destroy()


@pytest.mark.parametrize("change", ["pdf", "field", "leave", "close"])
def test_wizard_shared_pending_test_cannot_publish_old_target(tmp_path, change):
    from rule_editor.wizard import NewRulesetWizard
    import threading

    root, editor, rules, draft, pdf = _proof_editor(tmp_path)
    wizard = None
    held, release = threading.Event(), threading.Event()
    original = rules.create_authoring_proof

    def proof(*args):
        result = original(*args)
        held.set()
        assert release.wait(5)
        return result

    rules.create_authoring_proof = proof
    try:
        root.deiconify()
        wizard = NewRulesetWizard(editor, rules, initial_draft_path=str(draft), proof_owner=editor)
        wizard.var_pdf.set(str(pdf))
        wizard._show_step(3)
        wizard._on_rule_test()
        assert held.wait(3)
        if change == "pdf":
            wizard.var_pdf.set(str(pdf.with_name("different.pdf")))
            wizard.var_pdf.set(str(pdf))
        elif change == "field":
            wizard.var_f_regex.set("changed")
        elif change == "leave":
            editor.invalidate_context()
        else:
            wizard._shutdown(None)
        release.set()
        _finish_editor_tasks(root, editor)
        assert editor._proof_result is None
        assert str(editor.btn_activate.cget("state")) == "disabled"
        if not wizard._closed:
            assert wizard.tree_authoring_values.get_children() == ()
    finally:
        release.set()
        if wizard is not None and not wizard._closed:
            wizard._shutdown(None)
        root.destroy()


@pytest.mark.parametrize("mutation", ["save", "add"])
def test_wizard_successful_mutation_always_revokes_ready_proof(tmp_path, mutation):
    from rule_editor.wizard import NewRulesetWizard

    root, editor, rules, draft, pdf = _proof_editor(tmp_path)
    wizard = None
    try:
        root.deiconify()
        wizard = NewRulesetWizard(editor, rules, initial_draft_path=str(draft), proof_owner=editor)
        wizard.var_pdf.set(str(pdf))
        wizard.assay_text = "VALUE X"
        key = wizard._fields[0]["key"] if mutation == "save" else "extra"
        wizard.var_f_key.set(key)
        wizard.var_f_regex.set("VALUE (X)")
        wizard._show_step(3)
        wizard._on_rule_test()
        _finish_editor_tasks(root, editor)
        assert editor.authoring_target_ready(wizard._rule_test_target(), origin=wizard)
        # No StringVar write between proof and successful mutator.
        if mutation == "save":
            assert wizard._save_current_field(require_match=False)
        else:
            wizard._on_add_custom()
        assert editor._proof_result is None and wizard._field_report is None
        assert wizard.tree_authoring_values.get_children() == ()
        assert not editor.authoring_target_ready(wizard._rule_test_target(), origin=wizard)
    finally:
        if wizard is not None and not wizard._closed:
            wizard._shutdown(None)
        root.destroy()


def test_direct_search_mode_change_revokes_proof_without_activation_form_save(tmp_path):
    root, editor, _rules, _draft, _pdf = _proof_editor(tmp_path)
    try:
        editor._select_field(editor.fields_data[0]["key"])
        editor.on_preview()
        _finish_editor_tasks(root, editor)
        assert editor._proof_result["status"] == "ready"
        editor._set_search_mode("line", line="1")
        assert editor._proof_result is None and editor._field_form_dirty
        editor._guard_field_form = lambda: pytest.fail("activation must never save the field form")
        editor.on_activate()
        assert str(editor.btn_activate.cget("state")) == "disabled"
    finally:
        root.destroy()


@pytest.mark.parametrize("change", ["pdf", "scope"])
def test_shared_pdf_text_discards_late_previous_descriptor(tmp_path, change):
    import threading

    root, editor, rules, _draft, pdf = _proof_editor(tmp_path)
    held, release = threading.Event(), threading.Event()
    main_thread = threading.get_ident()

    def text(*_args, **_kwargs):
        assert threading.get_ident() != main_thread
        held.set()
        assert release.wait(5)
        return {"assay_block": "STALE TEXT", "detected_assays": []}

    rules.get_assay_text = text
    try:
        editor.on_load_text()
        assert held.wait(3)
        if change == "pdf":
            editor.var_pdf.set(str(pdf.with_name("other.pdf")))
        else:
            editor.invalidate_context()
        release.set()
        _finish_editor_tasks(root, editor)
        assert "STALE TEXT" not in editor.txt_block.get("1.0", "end") and editor.assay_block_text == ""
    finally:
        release.set()
        root.destroy()


@pytest.mark.parametrize("width,height,scale", [(1420, 930, 1.0), (960, 620, 1.25)])
def test_mockup_workspace_native_cards_reflow_without_clipped_controls(tmp_path, width, height, scale):
    root, editor, _rules, _draft, _pdf = _proof_editor(tmp_path, embedded=True)
    original_scaling = root.tk.call("tk", "scaling")
    try:
        root.tk.call("tk", "scaling", (4 / 3) * scale)
        root.geometry(f"{width}x{height}")
        # The direct workplace uses the approved context-only focus area, not
        # artificial permanent navigation/header gutters.
        editor.pack(fill="both", expand=True)
        editor._show_page("workspace")
        root.deiconify()
        for _ in range(4):
            root.update()
        editor._layout_editor_workspace()
        root.update()
        left, document, right = editor._workspace_cards
        assert left._rounded and document._rounded
        right_cards = [child for child in right.winfo_children() if getattr(child, "_rounded", False)]
        assert len(right_cards) == 2
        assert editor._workspace_compact is (width == 960)
        assert len(editor.workspace_panes.panes()) == 3
        assert left.winfo_rootx() < editor.txt_block.winfo_rootx() < editor.ent_field_regex.winfo_rootx()
        assert editor.txt_block.winfo_rooty() < root.winfo_rooty() + 200
        assert editor.txt_block.winfo_height() > height * .55
        assert editor.ent_field_regex.winfo_rooty() + editor.ent_field_regex.winfo_height() <= root.winfo_rooty() + height
        assert editor.ent_field_regex.winfo_width() >= 200
        assert editor.ent_field_regex.winfo_rootx() + editor.ent_field_regex.winfo_width() <= right.winfo_rootx() + right.winfo_width()
        assert editor.tree_marking_legend is None
        assert editor.frame_marking_panel.winfo_manager() == "grid"
        assert tuple(editor.tree_fields.cget("displaycolumns")) == ("status",)
        for button in editor.field_list_actions._controls:
            assert button.winfo_rooty() + button.winfo_height() <= root.winfo_rooty() + height
        for button in editor.editor_navigation._controls:
            flow = editor.editor_navigation
            assert 0 <= button.winfo_x() < flow.winfo_width()
            assert button.winfo_x() + button.winfo_width() <= flow.winfo_width()
        # All document controls have one baseline; there is no second native tab bar.
        text_button, pdf_button = editor.btn_document_text, editor.btn_document_pdf
        assert abs(text_button.winfo_rooty() - pdf_button.winfo_rooty()) <= 1
        assert abs(text_button.winfo_rooty() - editor.ent_test_pdf.winfo_rooty()) <= 8
        assert not isinstance(editor.report_notebook, ttk.Notebook)
        compact = editor._workspace_compact
        editor._toggle_advanced()
        assert editor.workspace_scrollable.winfo_manager() == ""
        editor._hide_advanced()
        root.update()
        assert editor._workspace_compact is compact and editor.workspace_panes.winfo_manager() == "grid"
    finally:
        root.tk.call("tk", "scaling", original_scaling)
        root.destroy()


def test_compact_inventory_keeps_at_least_three_full_rows_visible(tmp_path):
    from src.application.api import RulesetInventoryItem
    root, editor, _rules, _draft, _pdf = _proof_editor(tmp_path, embedded=True)
    try:
        root.tk.call("tk", "scaling", 5 / 3)
        root.geometry("960x620")
        ttk.Frame(root, height=60, style="Header.TFrame").pack(side="top", fill="x")
        ttk.Frame(root, width=222, style="Nav.TFrame").pack(side="left", fill="y")
        editor.pack(side="right", fill="both", expand=True)
        editor._show_page("inventory")
        editor.render_inventory(tuple(RulesetInventoryItem("draft", "Entwurf", f"({i})", f"Assay {i}", f"rule{i}.json", f"rule{i}.json", 13, True, None) for i in range(5)))
        root.deiconify()
        for _ in range(4):
            root.update()
        third = editor.tree_rulesets.get_children()[2]
        bounds = editor.tree_rulesets.bbox(third)
        assert bounds and bounds[1] + bounds[3] <= editor.tree_rulesets.winfo_height()
        assert editor._embedded and not _walk_entries(editor.editor_navigation)
    finally:
        root.destroy()


def test_html_buttons_keep_single_proof_owner_and_reveal_activation_only_in_completion(tmp_path):
    root, editor, _rules, _draft, pdf = _proof_editor(tmp_path, embedded=True)
    try:
        assert [button.cget("text") for button in editor.editor_action_flow._controls] == [
            "Speichern", "Rückgängig", "Wiederholen", "Struktur prüfen", "Änderungen vergleichen", "Regeldetails"]
        assert editor.btn_rule_test.cget("text") == "Regel testen"
        assert not editor.btn_activate.winfo_manager()
        assert editor.btn_field_commit.cget("style") == "RuleSuite.Primary.TButton"
        assert editor.btn_field_replace.cget("style") == "RuleSuite.Secondary.TButton"
        editor.on_preview()
        _finish_editor_tasks(root, editor)
        assert editor._proof_result["status"] == "ready" and not editor.btn_activate.winfo_manager()
        editor.btn_completion.invoke()
        assert editor._completion_visible and editor.authoring_values_frame.winfo_manager() == "pack"
        assert editor.editor_functions.winfo_manager() == "grid"
        assert str(editor.btn_activate.cget("state")) == "normal"
        assert editor.btn_activate.cget("text") == "Geprüfte Regel aktivieren"
        editor.var_pdf.set(str(pdf.with_name("different.pdf")))
        assert editor._proof_result is None and not editor._completion_visible and not editor.btn_activate.winfo_manager()
    finally:
        root.destroy()


def test_html_field_apply_and_explicit_replace_use_same_existing_commit(tmp_path):
    root, editor, rules, _draft, _pdf = _proof_editor(tmp_path, embedded=True)
    calls = []
    original = rules.replace_field
    rules.replace_field = lambda *a, **k: calls.append((a, k)) or original(*a, **k)
    try:
        key = editor.fields_data[0]["key"]
        assert editor._select_field(key)
        editor.var_field_regex.set(r"Test:\s*(\w+)")
        editor.btn_field_commit.invoke()
        assert len(calls) == 1 and calls[0][0][1] == key and calls[0][1]["key"] == key
        renamed = key + "_renamed"
        editor.var_field_key.set(renamed)
        assert str(editor.btn_field_commit.cget("state")) == "disabled"
        editor.on_apply_field()
        assert len(calls) == 1
        editor.btn_field_replace.invoke()
        assert len(calls) == 2 and calls[1][0][1] == key and calls[1][1]["key"] == renamed
        editor.on_begin_new_field()
        assert editor.btn_field_commit.cget("text") == "Feld anlegen"
        assert str(editor.btn_field_replace.cget("state")) == "disabled"
    finally:
        root.destroy()


def test_html_inventory_disclosure_filters_locally_and_keeps_global_theme(tmp_path):
    root, editor, rules, _draft, _pdf = _proof_editor(tmp_path, embedded=True)
    try:
        style = ttk.Style(root)
        assert style.lookup("RuleSuite.Primary.TButton", "background") == "#175ba4"
        assert style.lookup("RuleSuite.Secondary.TButton", "bordercolor") == "#c5d7eb"
        assert style.lookup("RuleSuite.Danger.TButton", "foreground") == "#a93c42"
        assert style.lookup("Primary.TButton", "background") == "#175ba4"
        editor._show_page("inventory")
        assert editor.btn_inventory_new.cget("text") == "Neue Regel aus PDF"
        assert not editor.inventory_state_options.winfo_manager()
        rules.list_inventory = lambda **_k: pytest.fail("local filters must not reread inventory")
        editor.btn_inventory_states.invoke()
        assert editor.inventory_state_options.winfo_manager() == "pack"
        editor.inventory_filter_vars["draft"].set(False)
        editor._on_inventory_filter_changed()
        assert editor.btn_inventory_states.cget("text") == "Zustände · 4"
        editor.var_inventory_search.set("Anti-MPO")
        editor._clear_inventory_filters()
        assert editor.var_inventory_search.get() == "" and all(v.get() for v in editor.inventory_filter_vars.values())
        assert editor.btn_inventory_states.cget("text") == "Zustände · 5"
    finally:
        root.destroy()


def test_field_buttons_fit_mockup_row_without_native_minimum_width(tmp_path):
    root, editor, _rules, _draft, _pdf = _proof_editor(tmp_path, embedded=True)
    try:
        root.tk.call("tk", "scaling", 4 / 3)
        root.update_idletasks()
        buttons = editor.field_list_actions._controls[:4]
        assert sum(button.winfo_reqwidth() for button in buttons) + 18 <= 215
        assert buttons[2].winfo_reqwidth() < 45 and buttons[3].winfo_reqwidth() < 45
        assert ttk.Style(root).lookup("RuleSuite.Primary.TButton", "focuscolor") == "#ffffff"
    finally:
        root.destroy()


@pytest.mark.parametrize("width,height,scale", [(1420, 930, 1.0), (960, 620, 1.25)])
def test_inventory_filterbar_has_flexible_search_aligned_controls_and_visible_disclosure(tmp_path, width, height, scale):
    root, editor, _rules, _draft, _pdf = _proof_editor(tmp_path, embedded=True)
    try:
        root.tk.call("tk", "scaling", (4 / 3) * scale)
        root.geometry(f"{width}x{height}")
        ttk.Frame(root, height=60, style="Header.TFrame").pack(side="top", fill="x")
        ttk.Frame(root, width=222, style="Nav.TFrame").pack(side="left", fill="y")
        editor.pack(side="right", fill="both", expand=True)
        editor._show_page("inventory")
        root.deiconify()
        for _ in range(4):
            root.update()
        entry, button = editor._inventory_search_entry, editor._inventory_search_button
        assert entry.winfo_rooty() == button.winfo_rooty()
        assert entry.winfo_height() == button.winfo_height()
        assert entry.winfo_width() >= (280 if width == 1420 else 350)
        assert editor.btn_inventory_states.cget("image")
        groups = (editor._inventory_filter_group, editor._inventory_stock_group, editor._inventory_search_group)
        if width == 1420:
            assert len({group.winfo_rooty() for group in groups}) == 1
        else:
            assert groups[2].winfo_rooty() > groups[0].winfo_rooty()
            assert groups[2].winfo_width() == editor._inventory_filterbar.winfo_width()
            import tkinter.font as tkfont
            heading_font = tkfont.Font(root, font=ttk.Style(root).lookup("Treeview.Heading", "font"))
            assert editor.tree_rulesets.column("fields", "width") >= heading_font.measure("Feldzahl") + 24
            assert editor.tree_rulesets.xview() == (0.0, 1.0)
        right = editor._inventory_filterbar.winfo_rootx() + editor._inventory_filterbar.winfo_width()
        for group in groups:
            assert group.winfo_rootx() + group.winfo_width() <= right
        editor.inventory_filter_vars["draft"].set(False)
        editor._on_inventory_filter_changed()
        assert editor.btn_inventory_states.cget("text") == "Zustände · 4" and editor.btn_inventory_states.cget("image")
    finally:
        root.destroy()


def test_native_paned_cards_can_reflow_to_same_parent_grid():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk not available: {exc}")
    root.withdraw()
    try:
        body = ttk.Frame(root)
        panes = ttk.Panedwindow(body, orient="horizontal")
        card = ttk.Frame(body)
        panes.add(card)
        assert str(card) in panes.panes()
        panes.forget(card)
        card.grid(row=0, column=0)
        assert card.winfo_manager() == "grid"
    finally:
        root.destroy()


def test_project_root_entry_is_readonly() -> None:
    from rule_editor.toolbar import build_toolbar

    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk not available: {exc}")
    root.withdraw()
    try:
        host = tk.Frame(root)
        host.var_root = tk.StringVar(value="I:/proj")
        host.var_hint = tk.StringVar(value="")
        host.on_pick_root = lambda: None
        host.on_open_wizard = lambda: None
        host.open_step_by_step = lambda: None
        build_toolbar(host)
        entries = [child for child in host.winfo_children() if isinstance(child, tk.Entry)]
        if not entries:
            entries = [
                child
                for frame in host.winfo_children()
                for child in _walk_entries(frame)
            ]
        assert len(entries) == 1
        assert str(entries[0].cget("state")) == "readonly"
        buttons = _button_texts(host)
        assert buttons.count("Wählen …") == 1
        assert "Geführter Modus" in buttons
    finally:
        root.destroy()


def test_phase6_view_modules_import_no_src() -> None:
    offenders: list[str] = []
    for rel_path in VIEW_MODULES:
        for module in _imports(rel_path):
            if module == "src" or module.startswith("src."):
                offenders.append(f"{rel_path}: {module}")
    assert offenders == []
    line_count = len((PROJECT_ROOT / "rule_editor/ui_builder.py").read_text(encoding="utf-8").splitlines())
    assert line_count < 220


def test_phase6_static_navigation_and_ttk_pane_contract() -> None:
    main_source = (PROJECT_ROOT / "rule_editor_main.py").read_text(encoding="utf-8")
    workspace_source = (PROJECT_ROOT / "rule_editor/workspace.py").read_text(encoding="utf-8")
    assert "self.minsize(1024, 768)" in main_source
    assert 'self.geometry("1440x900")' in main_source
    assert 'self.state("zoomed")' in main_source
    assert "except tk.TclError:" in main_source
    assert "self.notebook" not in main_source
    assert "ttk.Panedwindow" in workspace_source
    assert ".pane(" not in workspace_source
    # minsize belongs to the responsive grid, never unsupported ttk panes.
    assert "panes.pane(" not in workspace_source


def test_phase6_select_tab_routes_without_notebook() -> None:
    from rule_editor_main import RuleEditorWorkspace

    calls: list[tuple[str, str | None]] = []
    host = type("Host", (), {})()
    host._show_page = lambda page: calls.append(("page", page))
    host._show_advanced = lambda section=None: calls.append(("advanced", section))
    host._hide_advanced = lambda: calls.append(("hide", None))
    host._set_active_step_button = lambda key: calls.append(("active", key))

    RuleEditorWorkspace._select_tab(host, "draft")
    RuleEditorWorkspace._select_tab(host, "pdf")
    RuleEditorWorkspace._select_tab(host, "meta")

    assert calls == [
        ("page", "inventory"),
        ("active", "draft"),
        ("page", "workspace"),
        ("hide", None),
        ("active", "pdf"),
        ("advanced", "meta"),
        ("active", "meta"),
    ]


class _Var:
    def __init__(self, value: str = "") -> None:
        self.value = value

    def get(self) -> str:
        return self.value

    def set(self, value: str) -> None:
        self.value = value


def test_phase6_successful_draft_load_opens_workspace_and_failure_does_not(monkeypatch: pytest.MonkeyPatch) -> None:
    from rule_editor.draft_actions import DraftMixin

    class Host(DraftMixin):
        def __init__(self, rules: object) -> None:
            self._rules = rules
            self.var_draft_path = _Var("draft.json")
            self.current_draft_path = None
            self.pages: list[str] = []
            self.applied: list[dict] = []

        def _apply_data_to_widgets(self, data: dict) -> None:
            self.applied.append(data)

        def _set_hint(self, _text: str) -> None:
            return None

        def _log(self, _text: str) -> None:
            return None

        def _show_page(self, page: str) -> None:
            self.pages.append(page)

    class GoodRules:
        def load_draft(self, path: str) -> dict:
            assert path == "draft.json"
            return {"assay_key": "(p6)"}

    good = Host(GoodRules())
    good.on_load_draft_into_editor()
    assert good.current_draft_path == "draft.json"
    assert good.applied == [{"assay_key": "(p6)"}]
    assert good.pages == ["workspace"]

    errors: list[str] = []

    class BadRules:
        def load_draft(self, _path: str) -> dict:
            raise RuntimeError("broken draft")

    monkeypatch.setattr(
        "rule_editor.draft_actions.messagebox.showerror",
        lambda _title, message: errors.append(str(message)),
    )
    bad = Host(BadRules())
    bad.on_load_draft_into_editor()
    assert bad.current_draft_path is None
    assert bad.pages == []
    assert errors == ["broken draft"]


def test_phase6_context_help_contract() -> None:
    from rule_editor.constants import HELP_TEXTS

    assert "Berichttexts" in HELP_TEXTS["search_pattern"]
    assert "fehlerhaft" in HELP_TEXTS["required_field"]
    assert "späteren Bereich" in HELP_TEXTS["search_from"]
    assert "Regex testen" in HELP_TEXTS["pattern_from_selection"]


def test_phase6_visible_guidance_uses_workspace_terms() -> None:
    sources = "\n".join(
        (PROJECT_ROOT / rel_path).read_text(encoding="utf-8-sig")
        for rel_path in (
            "rule_editor/constants.py",
            "rule_editor/field_actions.py",
            "rule_editor/pdf_text_actions.py",
            "rule_editor/regex_actions.py",
            "rule_editor/guide.py",
        )
    )
    for obsolete in ("PDF-Tab", "Felder-Tab", "Zum passenden Tab"):
        assert obsolete not in sources
    assert "Zum passenden Bereich" not in sources
    assert 'self.on_open_wizard(intent="neutral")' in sources


def test_phase6_shell_is_inventory_and_three_column_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    editor = _open_editor(tmp_path, monkeypatch)
    try:
        editor.update_idletasks()
        assert editor.minsize() == (1024, 768)
        width_s, rest = editor.geometry().split("x", 1)
        height_s = rest.split("+", 1)[0]
        assert int(width_s) >= 1024
        assert int(height_s) >= 768
        assert not hasattr(editor, "notebook")
        assert editor._active_page == "inventory"
        assert editor.page_inventory.winfo_manager() == "grid"
        assert editor.page_workspace.winfo_manager() == ""
        assert not hasattr(editor, "cmb_inventory_filter")
        assert not hasattr(editor, "var_inventory_filter")
        assert {kind: editor.inventory_filter_vars[kind].get() for kind in ("active", "draft", "inactive", "history", "trash")} == {
            "active": True,
            "draft": True,
            "inactive": True,
            "history": True,
            "trash": True,
        }

        for name in CONTRACT_ATTRS:
            assert getattr(editor, name) is not None, name
        assert editor.tree_marking_legend is None and editor._unified_field_grid
        assert editor.tree_rulesets.cget("yscrollcommand")
        assert editor.ent_field_regex is editor.ent_marking_regex
        assert editor.txt_marking_regex_preview is None

        panes = editor.workspace_panes
        children = list(panes.panes())
        assert len(children) == 3
        assert str(panes.cget("orient")) == "horizontal"
        assert [int(panes.pane(child, "weight")) for child in children] == [20, 52, 28]
        assert editor.frame_advanced.winfo_manager() == ""
        assert panes.winfo_manager() == "grid"

        pane_names = set(children)
        left = _pane_of(editor.tree_fields, pane_names)
        middle = _pane_of(editor.txt_block, pane_names)
        right = _pane_of(editor.ent_field_regex, pane_names)
        assert left is not None and middle is not None and right is not None
        assert len({left, middle, right}) == 3
        assert children == [left, middle, right]

        texts = _button_texts(editor)
        for label in PRIMARY_LABELS:
            assert label in texts
        hidden = " ".join(texts).lower()
        for blocked in ("trash", "history", "wiederherstellen", "papierkorb"):
            assert blocked not in hidden

        editor._show_page("workspace")
        try:
            editor.state("normal")
        except tk.TclError:
            pass
        editor.geometry("1024x768")
        editor.update_idletasks()
        assert editor._active_page == "workspace"
        assert editor.page_workspace.winfo_manager() == "grid"
        for button in _buttons(editor.page_workspace):
            if button.winfo_manager() != "grid" or button.master.winfo_width() <= 1:
                continue
            assert button.winfo_x() >= 0, str(button.cget("text"))
            assert button.winfo_x() + button.winfo_width() <= button.master.winfo_width() + 1, str(
                button.cget("text")
            )
        editor._toggle_marking_panel()
        assert editor.frame_marking_panel.winfo_manager() == "grid"
        editor._toggle_marking_panel()
        assert editor.frame_marking_panel.winfo_manager() == "grid"
        assert tuple(editor.cmb_marking_mode.cget("values")) == ("Alle markieren", "Alle ausblenden", "Nur Treffer", "Nur aktives Feld")
        assert str(editor.btn_toggle_markings.cget("text")) == "↻"

        editor._toggle_advanced()
        assert editor._advanced_visible is True
        assert editor.frame_advanced.winfo_manager() == "grid"
        assert editor.workspace_scrollable.winfo_manager() == ""
        editor._show_page("inventory")
        assert editor._active_page == "inventory"
        assert editor._advanced_visible is False
    finally:
        editor.destroy()


def _requested_size(widget: tk.Misc) -> tuple[int, int]:
    size = widget.geometry().split("+", 1)[0].split("-", 1)[0]
    width_s, height_s = size.split("x", 1)
    return int(width_s), int(height_s)


def test_rule_editor_keeps_default_size_when_maximize_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    zoom_attempts: list[str] = []

    def state(self, newstate=None):
        if newstate == "zoomed":
            zoom_attempts.append(str(newstate))
            raise tk.TclError("zoom unsupported")
        if newstate is None:
            return "normal"
        return None

    monkeypatch.setattr(tk.Tk, "state", state)
    editor = _open_editor(tmp_path, monkeypatch)
    try:
        editor.update_idletasks()
        assert editor.minsize() == (1024, 768)
        width, height = _requested_size(editor)
        assert abs(width - 1440) <= 40
        assert abs(height - 900) <= 40
        if sys.platform == "win32":
            assert zoom_attempts == ["zoomed"]
        else:
            assert zoom_attempts == []
    finally:
        editor.destroy()


def test_rule_editor_does_not_maximize_off_windows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    zoom_attempts: list[str] = []
    original_state = tk.Tk.state

    def state(self, newstate=None):
        if newstate == "zoomed":
            zoom_attempts.append(str(newstate))
        return original_state(self, newstate)

    monkeypatch.setattr(tk.Tk, "state", state)
    editor = _open_editor(tmp_path, monkeypatch)
    try:
        editor.update_idletasks()
        assert zoom_attempts == []
        assert editor.minsize() == (1024, 768)
        width, height = _requested_size(editor)
        assert abs(width - 1440) <= 40
        assert abs(height - 900) <= 40
    finally:
        editor.destroy()


def test_presentation_contract_is_static() -> None:
    main_source = (PROJECT_ROOT / "rule_editor_main.py").read_text(encoding="utf-8")
    workspace = (PROJECT_ROOT / "rule_editor/workspace.py").read_text(encoding="utf-8")
    inventory = (PROJECT_ROOT / "rule_editor/inventory_view.py").read_text(encoding="utf-8")
    fields = (PROJECT_ROOT / "rule_editor/field_list_panel.py").read_text(encoding="utf-8")
    settings = (PROJECT_ROOT / "rule_editor/field_settings_panel.py").read_text(encoding="utf-8")
    wizard_ui = (PROJECT_ROOT / "rule_editor/wizard_ui.py").read_text(encoding="utf-8")
    manage = (PROJECT_ROOT / "rule_editor/manage_actions.py").read_text(encoding="utf-8")
    toolbar = (PROJECT_ROOT / "rule_editor/toolbar.py").read_text(encoding="utf-8")
    presentation_files = (
        "rule_editor/toolbar.py",
        "rule_editor/inventory_view.py",
        "rule_editor/workspace.py",
        "rule_editor/field_list_panel.py",
        "rule_editor/field_settings_panel.py",
        "rule_editor/report_panel.py",
        "rule_editor/advanced_view.py",
        "rule_editor/wizard.py",
        "rule_editor/wizard_ui.py",
    )

    assert "configure_desktop_theme(self)" in main_source
    assert 'self.title("Analyzer Result Extractor – Regelverwaltung")' in main_source
    assert "configure_desktop_theme(self)" in wizard_ui
    for callback in (
        "host.on_undo",
        "host.on_redo",
        "host.on_save_all",
        "host.on_validate",
        "host.on_preview",
        "host.on_show_diff",
        "host.on_activate",
        "host._toggle_advanced",
    ):
        assert callback in workspace
    assert "zip(host._workspace_cards, (20, 52, 28))" in workspace
    assert 'state="readonly"' in toolbar
    assert 'command=""' in fields
    assert "host.on_open_regex_library" in settings and '"Bibliothek"' in settings
    assert "width=4" not in settings
    assert "width=5" not in settings
    assert 'text="Bib..."' not in wizard_ui
    assert "width=4," not in wizard_ui
    assert "Regex-Bibliothek …" in wizard_ui
    for kind in ("active", "draft", "inactive", "history", "trash"):
        assert f'"{kind}"' in inventory
    for label in (
        "Als Entwurf bearbeiten",
        "Regel deaktivieren …",
        "Als neue Regel duplizieren …",
        "Entwurf weiterbearbeiten",
        "Entwurf in Papierkorb verschieben …",
        "Endgültig löschen (nur nie aktiviert) …",
        "Als Entwurf wiederherstellen …",
        "In Papierkorb verschieben …",
        "Details anzeigen",
    ):
        assert label in manage
    combined = "\n".join((PROJECT_ROOT / path).read_text(encoding="utf-8") for path in presentation_files)
    for obsolete in ("Gesamtpreview", "Draft validieren", "Erweiterte Optionen", "Bib..."):
        assert obsolete not in combined
