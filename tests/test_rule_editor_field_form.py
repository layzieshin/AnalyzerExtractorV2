"""Stabiler Feldeditor: Auswahl, atomare Formularaktion, Dirty-Guard."""
from __future__ import annotations

import tkinter as tk
from pathlib import Path

import pytest

from rule_editor.field_actions import FieldsMixin
from rule_editor.history_actions import HistoryMixin
from rule_editor.meta_actions import MetaMixin
from rule_editor.release_actions import ReleaseMixin


class _Var:
    def __init__(self, value: object = "") -> None:
        self.value = value

    def get(self) -> object:
        return self.value

    def set(self, value: object) -> None:
        self.value = value


class _Tree:
    def __init__(self, rows: list[tuple[str, tuple[str, ...]]]) -> None:
        self.rows = rows
        self.selected: tuple[str, ...] = ()
        self.selection_set_calls = 0
        self.selection_remove_calls = 0

    def selection(self) -> tuple[str, ...]:
        return self.selected

    def item(self, iid: str, option: str) -> tuple[str, ...]:
        assert option == "values"
        for row_id, values in self.rows:
            if row_id == iid:
                return values
        raise KeyError(iid)

    def get_children(self) -> list[str]:
        return [row_id for row_id, _values in self.rows]

    def selection_set(self, iid: str) -> None:
        self.selection_set_calls += 1
        self.selected = (iid,)

    def selection_remove(self, _ids: object) -> None:
        self.selection_remove_calls += 1
        self.selected = ()

    def focus(self, _iid: str) -> None:
        return None

    def see(self, _iid: str) -> None:
        return None


class _FieldHost(FieldsMixin):
    def __init__(self) -> None:
        self.current_draft_path = "draft.json"
        self.fields_data = [
            {"key": "alpha", "regex": r"A:\s*(\w+)", "required": True, "search_from": {"line": 2}},
        ]
        self.column_mapping_data = {"alpha": "ALPHA"}
        self.var_field_key = _Var("alpha")
        self.var_field_regex = _Var(r"A:\s*(\w+)")
        self.var_field_required = _Var(True)
        self.var_field_excel_column = _Var("ALPHA")
        self.var_field_dedupe = _Var(True)
        self.var_search_mode = _Var("line")
        self.var_search_mode_label = _Var("Ab Zeile")
        self.var_search_after = _Var("")
        self.var_search_line = _Var("2")
        self.var_regex_group = _Var("1")
        self.var_dedupe_fields = _Var("alpha")
        self.var_field_guidance = _Var("")
        self._selected_field_key: str | None = "alpha"
        self._field_form_dirty = False
        self._field_form_loading = False
        self._field_form_is_new = False
        self._field_form_return_key = None
        self._suppress_field_select = False
        self._suspend_dirty_tracking = False
        self._dirty = True
        self._undo_stack: list[dict] = [{"prior": True}]
        self._redo_stack: list[dict] = [{"redo": True}]
        self._marking_sync_guard = True
        self.assay_block_text = ""
        self._field_marking_data: dict = {}
        self.tree_fields = _Tree([("row-alpha", ("alpha", r"A:\s*(\w+)", "Ab Zeile"))])
        self.tree_fields.selected = ("row-alpha",)
        self.restored: str | None = "unset"
        self.hints: list[str] = []
        self.logs: list[str] = []
        self.refreshed: str | None = None
        self.btn_field_commit = None
        self._rules = _Rules()

    def _set_hint(self, text: str) -> None:
        self.hints.append(text)

    def _log(self, text: str) -> None:
        self.logs.append(text)

    def _capture_draft_snapshot(self) -> dict:
        return {"snapshot": "before"}

    def _refresh_fields_tree(self, selected_key: str | None = None) -> None:
        self.refreshed = selected_key

    def _refresh_cols_tree(self) -> None:
        return None

    def _maybe_refresh_field_markings(self) -> None:
        return None

    def _restore_tree_selection(self, key: str | None) -> None:
        self.restored = key


class _Rules:
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.payload = {
            "assay_key": "(1)",
            "assay_name": "Alt",
            "vendor_extension": {"keep": True},
            "lot_rule": {"regex": "LOT", "extra": 1},
            "extract_rules": {
                "fields": [{"key": "alpha", "regex": r"A:\s*(\w+)", "required": True}],
                "dedupe_fields": ["alpha"],
                "custom_rule": {"mode": "strict"},
            },
            "excel_rules": {
                "excel_filename_template": "a.xlsx",
                "sheetname_template": "s",
                "column_mapping": {"alpha": "ALPHA"},
                "extra_excel": "keep",
            },
        }

    def load_draft(self, _path: str) -> dict:
        return self.payload

    def save_draft(self, _path: str, data: dict) -> str:
        self.payload = data
        self.calls.append(("save", data))
        return _path

    def replace_field(self, path: str, selected_key: str, **kwargs: object) -> str:
        self.calls.append(("replace", selected_key, kwargs))
        field = self.payload["extract_rules"]["fields"][0]
        field["key"] = kwargs["key"]
        field["regex"] = kwargs["regex"]
        field["required"] = kwargs["required"]
        self.payload["excel_rules"]["column_mapping"] = {str(kwargs["key"]): kwargs["excel_column"]}
        if kwargs["dedupe_member"]:
            self.payload["extract_rules"]["dedupe_fields"] = [str(kwargs["key"])]
        else:
            self.payload["extract_rules"]["dedupe_fields"] = []
        return self._receipt() if kwargs.get("return_receipt") else path

    def add_field(self, path: str, key: str, regex: str, **kwargs: object) -> str | dict:
        self.calls.append(("add", key, regex, kwargs))
        self.payload["extract_rules"]["fields"].append({"key": key, "regex": regex, "required": False})
        self.payload["excel_rules"]["column_mapping"][key] = kwargs["excel_column"]
        if kwargs["dedupe_member"]:
            self.payload["extract_rules"]["dedupe_fields"].append(key)
        return self._receipt() if kwargs.get("return_receipt") else path

    def remove_field(self, path: str, field_key: str, **kwargs: object) -> str | dict:
        self.calls.append(("remove", field_key))
        return self._receipt() if kwargs.get("return_receipt") else path

    def _receipt(self) -> dict:
        return {
            "before": {"locked_before": True},
            "after_revision": "ab" * 32,
            "before_revision": "cd" * 32,
            "path": "draft.json",
        }

    def update_draft_meta(self, path: str, **kwargs: object) -> str | dict:
        self.calls.append(("meta", kwargs))
        self.payload["assay_key"] = kwargs["assay_key"]
        self.payload["assay_name"] = kwargs["assay_name"]
        self.payload["lot_rule"]["regex"] = kwargs["lot_regex"]
        self.payload["excel_rules"]["excel_filename_template"] = kwargs["excel_filename_template"]
        self.payload["excel_rules"]["sheetname_template"] = kwargs["sheetname_template"]
        if kwargs.get("return_receipt"):
            return {
                "before": {"snap": True},
                "after_revision": "ab" * 32,
                "before_revision": "cd" * 32,
                "path": path,
            }
        return path


def test_restore_tree_selection_does_not_reemit_for_active_field() -> None:
    host = FieldsMixin.__new__(FieldsMixin)
    host._suppress_field_select = False
    host.tree_fields = _Tree([("row-alpha", ("alpha", r"A:\s*(\w+)", "Ab Zeile"))])
    host.tree_fields.selected = ("row-alpha",)

    host._restore_tree_selection("alpha")

    assert host.tree_fields.selected == ("row-alpha",)
    assert host.tree_fields.selection_remove_calls == 0
    assert host.tree_fields.selection_set_calls == 0


def test_replace_keeps_stable_identity_required_and_one_undo() -> None:
    host = _FieldHost()
    host.var_field_key.set("beta")
    host.var_field_regex.set(r"B:\s*(\w+)")
    host.var_field_excel_column.set("BETA")
    host.var_field_dedupe.set(False)
    host._field_form_dirty = True

    assert host._commit_replace_field() is True

    kind, selected, kwargs = host._rules.calls[0]
    assert kind == "replace"
    assert selected == "alpha"
    assert kwargs["key"] == "beta"
    assert kwargs["required"] is True
    assert kwargs["excel_column"] == "BETA"
    assert kwargs["dedupe_member"] is False
    assert host._selected_field_key == "beta"
    assert host.var_field_key.get() == "beta"
    assert host.column_mapping_data == {"beta": "BETA"}
    assert host.var_dedupe_fields.get() == ""
    assert host._undo_stack == [
        {"prior": True},
        {"snapshot": {"locked_before": True}, "expected_revision": "ab" * 32},
    ]
    assert host._redo_stack == []
    assert host._dirty is True
    assert host._field_form_dirty is False


def test_failed_replace_does_not_touch_undo_or_dirty_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("rule_editor.field_actions.messagebox.showerror", lambda *_a, **_k: None)
    host = _FieldHost()

    def _boom(*_args: object, **_kwargs: object) -> str:
        raise RuntimeError("validation")

    host._rules.replace_field = _boom  # type: ignore[method-assign]
    host._field_form_dirty = True
    undo = list(host._undo_stack)
    redo = list(host._redo_stack)

    assert host._commit_replace_field() is False
    assert host._undo_stack == undo
    assert host._redo_stack == redo
    assert host._dirty is True
    assert host._field_form_dirty is True
    assert host._selected_field_key == "alpha"


def test_new_mode_add_uses_form_values_and_key_edit_does_not_add() -> None:
    host = _FieldHost()
    host.var_field_key.set("beta")
    assert host.on_add_field() is False
    assert host._rules.calls == []

    host.on_begin_new_field()
    assert host._field_form_is_new is True
    assert host._selected_field_key is None
    assert host._rules.calls == []
    host.var_field_key.set("gamma")
    host.var_field_regex.set(r"G:\s*(\w+)")
    host.var_field_excel_column.set("GAMMA")
    host.var_field_dedupe.set(True)
    host.var_search_mode.set("none")

    assert host.on_add_field() is True
    kind, key, regex, kwargs = host._rules.calls[0]
    assert (kind, key, regex) == ("add", "gamma", r"G:\s*(\w+)")
    assert kwargs["excel_column"] == "GAMMA"
    assert kwargs["dedupe_member"] is True
    assert kwargs["required"] is False
    assert host._selected_field_key == "gamma"
    assert host._field_form_is_new is False


def test_delete_uses_selected_key_not_edited_form_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("rule_editor.field_actions.messagebox.askyesno", lambda *_a, **_k: True)
    host = _FieldHost()
    host.var_field_key.set("edited")
    host.on_remove_field()
    assert host._rules.calls[0] == ("remove", "alpha")
    assert len(host._undo_stack) == 2


def test_field_guard_cancel_restores_tree_and_release_stops(monkeypatch: pytest.MonkeyPatch) -> None:
    host = _FieldHost()
    host._field_form_dirty = True
    host.tree_fields.rows.append(("row-beta", ("beta", "B", "Gesamter Assay-Text")))
    host.tree_fields.selected = ("row-beta",)
    monkeypatch.setattr("rule_editor.field_actions.messagebox.askyesnocancel", lambda *_a, **_k: None)

    host.on_field_selected()

    assert host.restored == "alpha"
    assert host._selected_field_key == "alpha"
    assert host._rules.calls == []

    release = ReleaseMixin.__new__(ReleaseMixin)
    release._resolve_dirty_field_form = lambda: False
    release.current_draft_path = "draft.json"
    release._rules = _Rules()
    called: list[str] = []
    release._quick_validate = lambda *_a, **_k: called.append("validate") or True
    release.on_activate()
    assert called == []


def test_meta_save_and_autosave_field_boundary() -> None:
    rules = _Rules()

    class Host(MetaMixin, FieldsMixin):
        def __init__(self) -> None:
            self.current_draft_path = "draft.json"
            self._rules = rules
            self.var_new_assay_key = _Var("(1)")
            self.var_new_assay_name = _Var("Neu")
            self.var_lot_regex = _Var("LOT-2")
            self.var_excel_filename = _Var("neu.xlsx")
            self.var_sheet_template = _Var("blatt")
            self.var_dedupe_fields = _Var("STALE")
            self.column_mapping_data = {"stale": "STALE"}
            self._dirty = True
            self._field_form_dirty = True
            self._suspend_dirty_tracking = False
            self._undo_stack: list[dict] = []
            self._redo_stack: list[dict] = [{"keep": True}]

        def _push_undo_snapshot(self) -> None:
            return None

        def _refresh_cols_tree(self) -> None:
            return None

    editor = Host()
    editor._redo_stack = [{"keep": True}]
    data = editor._save_meta_to_draft(push_undo=False)
    assert data["assay_name"] == "Neu"
    assert data["lot_rule"]["regex"] == "LOT-2"
    assert data["lot_rule"]["extra"] == 1
    assert data["excel_rules"]["column_mapping"] == {"alpha": "ALPHA"}
    assert data["excel_rules"]["extra_excel"] == "keep"
    assert data["extract_rules"]["dedupe_fields"] == ["alpha"]
    assert data["extract_rules"]["custom_rule"] == {"mode": "strict"}
    assert data["vendor_extension"] == {"keep": True}
    assert editor._dirty is False
    assert editor._field_form_dirty is True
    assert editor.var_dedupe_fields.get() == "alpha"
    assert editor._redo_stack == [{"keep": True}]

    class AutoHost(HistoryMixin):
        def __init__(self) -> None:
            self.var_autosave = _Var(True)
            self._dirty = True
            self._field_form_dirty = True
            self.current_draft_path = "draft.json"
            self._busy = False
            self.var_last_autosave = _Var("-")
            self._autosave_ms = 1
            self.saved = False

        def _save_meta_to_draft(self, push_undo: bool = False) -> dict:
            assert push_undo is False
            self.saved = True
            return {}

        def _log(self, _text: str) -> None:
            return None

        def after(self, _delay: int, _callback: object) -> None:
            return None

    auto = AutoHost()
    auto._autosave_tick()
    assert auto.saved is True
    assert auto._dirty is False
    assert auto._field_form_dirty is True


def test_invalid_receipt_blocks_undo_stack_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    errors: list[str] = []
    monkeypatch.setattr(
        "rule_editor.field_actions.messagebox.showerror",
        lambda *_a, **kwargs: errors.append(str(_a[-1] if _a else kwargs)),
    )
    monkeypatch.setattr("rule_editor.field_actions.messagebox.askyesno", lambda *_a, **_k: True)
    monkeypatch.setattr("rule_editor.field_actions.simpledialog.askstring", lambda *_a, **_k: "copy")
    host = _FieldHost()

    def _bad(*_args: object, **_kwargs: object) -> dict:
        return {"before": "not-a-draft"}

    host._rules.replace_field = _bad  # type: ignore[method-assign]
    host._rules.add_field = _bad  # type: ignore[method-assign]
    host._rules.duplicate_field = _bad  # type: ignore[method-assign]
    host._rules.move_field = _bad  # type: ignore[method-assign]
    host._rules.remove_field = _bad  # type: ignore[method-assign]
    undo = list(host._undo_stack)
    redo = list(host._redo_stack)
    assert host._commit_replace_field() is False
    host._field_form_is_new = True
    assert host._commit_new_field() is False
    host._field_form_is_new = False
    host.on_duplicate_field()
    host.on_move_field("up")
    host.on_remove_field()
    assert host._undo_stack == undo
    assert host._redo_stack == redo
    assert errors


def test_delete_no_and_search_mode_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("rule_editor.field_actions.messagebox.askyesno", lambda *_a, **_k: False)
    host = _FieldHost()
    undo = list(host._undo_stack)
    host.on_remove_field()
    assert host._rules.calls == []
    assert host._undo_stack == undo
    assert host._selected_field_key == "alpha"

    class _Entry:
        def __init__(self) -> None:
            self.state = tk.NORMAL

        def configure(self, **kwargs: object) -> None:
            if "state" in kwargs:
                self.state = kwargs["state"]

    host.ent_search_after = _Entry()
    host.ent_search_line = _Entry()
    host._field_form_dirty = False
    host._set_search_mode("after", after="MARK", line="")
    assert host.var_search_mode.get() == "after"
    assert host.var_search_mode_label.get() == "Ab Textmarker"
    assert host.ent_search_after.state == tk.NORMAL
    assert host.ent_search_line.state == tk.DISABLED
    assert host._field_form_dirty is True
    host._field_form_dirty = False
    host._set_search_mode("line", line="3", after="")
    assert host.var_search_mode_label.get() == "Ab Zeile"
    assert host.ent_search_line.state == tk.NORMAL
    assert host.ent_search_after.state == tk.DISABLED
    host._set_search_mode("none")
    assert host.var_search_mode_label.get() == "Gesamter Assay-Text"
    assert host.ent_search_after.state == tk.DISABLED
    assert host.ent_search_line.state == tk.DISABLED


def test_meta_push_undo_only_after_success() -> None:
    rules = _Rules()

    class Host(MetaMixin, FieldsMixin):
        def __init__(self) -> None:
            self.current_draft_path = "draft.json"
            self._rules = rules
            self.var_new_assay_key = _Var("(1)")
            self.var_new_assay_name = _Var("Neu")
            self.var_lot_regex = _Var("LOT-2")
            self.var_excel_filename = _Var("neu.xlsx")
            self.var_sheet_template = _Var("blatt")
            self.var_dedupe_fields = _Var("alpha")
            self.column_mapping_data = {}
            self._dirty = True
            self._suspend_dirty_tracking = False
            self._undo_stack: list[dict] = [{"old": True}]
            self._redo_stack: list[dict] = [{"redo": True}]

        def _refresh_cols_tree(self) -> None:
            return None

    editor = Host()
    editor._save_meta_to_draft(push_undo=True)
    assert editor._undo_stack == [
        {"old": True},
        {"snapshot": {"snap": True}, "expected_revision": "ab" * 32},
    ]
    assert editor._redo_stack == []
    assert rules.calls[-1][1]["return_receipt"] is True

    def _boom(*_args: object, **_kwargs: object) -> str:
        raise RuntimeError("locked")

    rules.update_draft_meta = _boom  # type: ignore[method-assign]
    editor._undo_stack = [{"old": True}]
    editor._redo_stack = [{"redo": True}]
    with pytest.raises(RuntimeError, match="locked"):
        editor._save_meta_to_draft(push_undo=True)
    assert editor._undo_stack == [{"old": True}]
    assert editor._redo_stack == [{"redo": True}]

    def _invalid(*_args: object, **_kwargs: object) -> dict:
        return {"before": "bad"}

    rules.update_draft_meta = _invalid  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="Undo-Beleg"):
        editor._save_meta_to_draft(push_undo=True)
    assert editor._undo_stack == [{"old": True}]
    assert editor._redo_stack == [{"redo": True}]


def test_field_editor_visible_contract(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from rule_editor_main import RuleEditorWindow

    root = tmp_path / "proj"
    rules = root / "rules"
    rules.mkdir(parents=True)
    (rules / "drafts").mkdir()
    (rules / "inactive").mkdir()
    (rules / "index.json").write_text('{"assays": []}', encoding="utf-8")
    monkeypatch.setenv("ARE_HOME", str(root))
    try:
        editor = RuleEditorWindow(project_root=root)
    except tk.TclError as exc:
        pytest.skip(f"Tk not available: {exc}")
    try:
        headings = [editor.tree_fields.heading(column)["text"] for column in editor.tree_fields["columns"]]
        assert headings == ["Feldschlüssel", "Suchmuster (Regex)", "Suchbereich"]
        texts = _widget_texts(editor)
        assert texts.count("Neues Feld") == 1
        assert "Markiertes Feld ersetzen" in texts
        assert "Bearbeitung abbrechen" in texts
        assert "In die Dublettenprüfung einbeziehen" in texts
        for blocked in (
            "Pflichtfeld",
            "Pflicht",
            "Uebernehmen",
            "Feld umbenennen",
            "Dedupe-Felder",
            "Mappings ergaenzen",
            "Feld hinzufuegen",
        ):
            assert blocked not in texts
        assert texts.count("Regex-Bibliothek …") == 1
        assert "Alle Felder testen" in texts
        assert "Bib" not in texts
        assert str(editor.btn_field_commit.cget("state")) == tk.DISABLED
        for column in editor.tree_fields["columns"]:
            assert editor.tree_fields.heading(column)["command"] == ""
        assert str(editor.tree_cols.cget("selectmode")) == "none"
        assert list(editor.cmb_search_mode.cget("values")) == [
            "Gesamter Assay-Text",
            "Ab Textmarker",
            "Ab Zeile",
        ]
    finally:
        editor.destroy()


def _widget_texts(widget: tk.Misc) -> list[str]:
    texts: list[str] = []
    for child in widget.winfo_children():
        if isinstance(child, (tk.Button, tk.Checkbutton, tk.Label)):
            texts.append(str(child.cget("text")))
        texts.extend(_widget_texts(child))
    return texts
