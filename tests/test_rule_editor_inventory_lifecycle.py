import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace

import pytest

import rule_editor.manage_actions as manage_actions
import rule_editor_main

_REMOVED_LABELS = (
    "Draft aus aktivem Assay",
    "Felder aus Regelwerk uebernehmen",
    "Felder aus Regelwerk übernehmen",
    "Neuer Assay-Key",
    "Neuer Assay-Name",
    "Neues Draft mit Headern",
    "Von Grund auf neu...",
    "Draft-Datei",
    "Draft laden...",
    "Draft laden in Editor",
    "Von bestehender Rule ableiten...",
    "Assays neu laden",
    "Als Entwurf bearbeiten",
)
_MAIN_ACTIONS = (
    "Neue Regel aus PDF …",
    "Aktion für Auswahl",
    "Weitere Aktionen …",
    "Aktualisieren",
    "Alle Zustände anzeigen",
)
_FILTER_LABELS = ("Aktiv", "Entwürfe", "Inaktiv", "Historie", "Papierkorb")


def _walk(widget: tk.Misc):
    yield widget
    for child in widget.winfo_children():
        yield from _walk(child)


def _is_under(widget: tk.Misc, ancestor: tk.Misc) -> bool:
    current: tk.Misc | None = widget
    while current is not None:
        if current == ancestor:
            return True
        current = getattr(current, "master", None)
    return False


def _bound_entries(widget: tk.Misc, variable: tk.Variable) -> list[tk.Entry]:
    target = str(variable)
    return [
        child
        for child in _walk(widget)
        if isinstance(child, tk.Entry) and str(child.cget("textvariable")) == target
    ]


def _widget_texts(widget: tk.Misc) -> list[str]:
    texts: list[str] = []
    for child in widget.winfo_children():
        if isinstance(child, (tk.Button, ttk.Button, tk.Checkbutton, tk.Label)):
            texts.append(str(child.cget("text")))
        texts.extend(_widget_texts(child))
    return texts


class _Item:
    def __init__(self, kind: str, key: str) -> None:
        self.kind = kind
        self.display_type = kind
        self.assay_key = key
        self.assay_name = key
        self.path = f"{kind}/{key}.json"
        self.ruleset_file = f"{key}.json"
        self.field_count = 2
        self.valid = True
        self.error = None
        self.modified_at = "2026-09-25"
        self.sha256 = "deadbeef"
        self.read_only = kind in {"history", "trash"}


def test_rule_editor_window_exposes_multiselect_inventory_filters() -> None:
    try:
        app = rule_editor_main.RuleEditorWindow()
    except tk.TclError as exc:
        pytest.skip(f"Tk not available: {exc}")
    try:
        assert hasattr(app, "on_manage_deactivate_selected")
        assert hasattr(app, "on_delete_never_active_selected")
        assert hasattr(app, "on_inventory_primary_action")
        assert not hasattr(app, "var_inventory_filter")
        assert not hasattr(app, "cmb_inventory_filter")
        assert set(app.inventory_filter_vars) == {"active", "draft", "inactive", "history", "trash"}
        assert all(variable.get() for variable in app.inventory_filter_vars.values())
        columns = tuple(app.tree_rulesets["columns"])
        assert columns == ("type", "key", "name", "fields", "modified", "status")
        texts = _widget_texts(app.page_inventory)
        for label in _MAIN_ACTIONS:
            assert label in texts
        for label in _FILTER_LABELS:
            assert label in texts
        for label in _REMOVED_LABELS:
            assert label not in texts
        assert "..." not in texts
        assert "Assays neu laden" not in _widget_texts(app)
        assert manage_actions._INVENTORY_KINDS == ("active", "draft", "inactive", "history", "trash")
        visible = _widget_texts(app)
        assert "Draft-Datei" not in visible
        assert "Entwurf" not in visible
        assert "Laden" not in visible
        assert not hasattr(app, "cmb_assay")
        assert app.lbl_loaded_assay_key.cget("textvariable")
        assert app.lbl_loaded_assay_name.cget("textvariable")
        assert _bound_entries(app, app.var_draft_path) == []
        name_entries = _bound_entries(app, app.var_new_assay_name)
        assert name_entries
        assert all(_is_under(entry, app.frame_advanced) for entry in name_entries)
    finally:
        app.destroy()


def test_inventory_filters_apply_locally_after_one_all_read() -> None:
    try:
        app = rule_editor_main.RuleEditorWindow()
    except tk.TclError as exc:
        pytest.skip(f"Tk not available: {exc}")
    items = [
        _Item("active", "(a)"),
        _Item("draft", "(d)"),
        _Item("inactive", "(i)"),
        _Item("history", "(h)"),
        _Item("trash", "(t)"),
    ]
    calls: list[str] = []

    def list_inventory(kind: str = "all") -> list[_Item]:
        calls.append(kind)
        return list(items)

    try:
        app._rules.list_inventory = list_inventory  # type: ignore[method-assign]
        app._refresh_ruleset_overview()
        assert calls == ["all"]
        assert len(app.tree_rulesets.get_children()) == 5

        app.inventory_filter_vars["draft"].set(False)
        app.inventory_filter_vars["trash"].set(False)
        app._on_inventory_filter_changed()
        assert calls == ["all", "all"]
        shown = {app.tree_rulesets.set(row_id, "key") for row_id in app.tree_rulesets.get_children()}
        assert shown == {"(a)", "(i)", "(h)"}

        for variable in app.inventory_filter_vars.values():
            variable.set(False)
        app._refresh_ruleset_overview()
        assert calls == ["all", "all", "all"]
        assert app.tree_rulesets.get_children() == ()

        app._select_all_inventory_filters()
        assert calls == ["all", "all", "all", "all"]
        assert all(variable.get() for variable in app.inventory_filter_vars.values())
        assert len(app.tree_rulesets.get_children()) == 5
        assert "file" not in app.tree_rulesets["columns"]
        assert "sha" not in app.tree_rulesets["columns"]
    finally:
        app.destroy()


def test_inventory_primary_action_matches_context_command() -> None:
    host = manage_actions.ManageMixin()
    row = {"kind": "active", "assay_key": "(1111)"}
    actions = host._inventory_context_actions(row)
    host._selected_inventory_row = lambda: row
    called: list[str] = []
    host.on_manage_edit_selected = lambda: called.append("edit")
    actions = host._inventory_context_actions(row)
    assert actions[0] == ("Als Entwurf bearbeiten", host.on_manage_edit_selected)
    host.on_inventory_primary_action()
    assert called == ["edit"]
    assert isinstance(SimpleNamespace(kind="active"), SimpleNamespace)


def test_inventory_primary_button_uses_context_action_label() -> None:
    try:
        app = rule_editor_main.RuleEditorWindow()
    except tk.TclError as exc:
        pytest.skip(f"Tk not available: {exc}")
    items = [
        _Item("active", "(a)"),
        _Item("draft", "(d)"),
        _Item("inactive", "(i)"),
        _Item("history", "(h)"),
        _Item("trash", "(t)"),
    ]
    try:
        app._rules.list_inventory = lambda kind="all": list(items)  # type: ignore[method-assign]
        app._refresh_ruleset_overview()
        expected = {
            "(a)": "Als Entwurf bearbeiten",
            "(d)": "Entwurf weiterbearbeiten",
            "(i)": "Als Entwurf wiederherstellen …",
            "(h)": "Als Entwurf wiederherstellen …",
            "(t)": "Details anzeigen",
        }
        for row_id in app.tree_rulesets.get_children():
            app.tree_rulesets.selection_set(row_id)
            app._sync_inventory_primary_button()
            key = app.tree_rulesets.set(row_id, "key")
            assert str(app.btn_inventory_primary.cget("text")) == expected[key]
            actions = app._inventory_context_actions(app._inventory_by_iid[row_id])
            assert actions[0][0] == expected[key]
    finally:
        app.destroy()


def test_clear_loaded_draft_empties_disabled_preview_and_residues() -> None:
    try:
        app = rule_editor_main.RuleEditorWindow()
    except tk.TclError as exc:
        pytest.skip(f"Tk not available: {exc}")
    try:
        app.txt_field_preview.configure(state="normal")
        app.txt_field_preview.insert("1.0", "preview-residue")
        app.txt_field_preview.configure(state="disabled")
        app.txt_block.insert("1.0", "block-residue")
        app.current_draft_path = r"I:\rules\drafts\gone.draft.json"
        app.var_draft_path.set(app.current_draft_path)
        app._dirty = True
        app.var_new_assay_key.set("(gone)")
        app.var_new_assay_name.set("Gone")
        app.fields_data = [{"key": "A", "regex": "a", "required": False}]
        app.column_mapping_data = {"A": "A"}
        app.assay_block_text = "block-residue"
        app._undo_stack = [{"k": 1}]
        app._redo_stack = [{"k": 2}]
        app._regex_result_counter = 3
        app._regex_result_data = {"regex_1": {"status": "HIT"}}
        app.tree_regex_results.insert("", "end", iid="regex_1", values=("A", "HIT", ".*", "v", "ctx"))
        app._field_marking_data = {"A": {"value": "alt"}}
        app._field_marking_tags = {"field::A"}
        app._visible_marking_keys = {"A"}
        app._active_marking_key = "A"
        app.txt_block.tag_add("field::A", "1.0", "1.1")
        app.tree_marking_legend.insert("", "end", text="A", values=("HIT", "ja", "alt"))
        app.tree_fields.insert("", "end", values=("A", "a", "Gesamter Assay-Text"))
        app.tree_cols.insert("", "end", values=("A", "A"))
        app.list_validation.insert("end", "alt")
        app._show_page("workspace")
        app._clear_loaded_draft()
        assert app.txt_field_preview.get("1.0", "end-1c") == ""
        assert str(app.txt_field_preview.cget("state")) == "disabled"
        assert app.txt_block.get("1.0", "end-1c") == ""
        assert app.tree_regex_results.get_children() == ()
        assert app._regex_result_data == {}
        assert app._regex_result_counter == 0
        assert app._field_marking_data == {}
        assert app._field_marking_tags == set()
        assert app._visible_marking_keys == set()
        assert app._active_marking_key is None
        assert app.tree_marking_legend.get_children() == ()
        assert app.tree_fields.get_children() == ()
        assert app.tree_cols.get_children() == ()
        assert app.list_validation.size() == 0
        assert app.fields_data == []
        assert app.column_mapping_data == {}
        assert app.assay_block_text == ""
        assert app.var_new_assay_key.get() == ""
        assert app._undo_stack == []
        assert app._redo_stack == []
        assert app.current_draft_path is None
        assert app.var_draft_path.get() == ""
        assert app._dirty is False
        assert app._active_page == "inventory"
    finally:
        app.destroy()
