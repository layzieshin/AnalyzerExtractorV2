from __future__ import annotations

from pathlib import Path

from rule_editor.draft_actions import DraftMixin


class _Var:
    def __init__(self, value: str = "") -> None:
        self.value = value

    def get(self) -> str:
        return self.value

    def set(self, value: str) -> None:
        self.value = value


class _DraftActions(DraftMixin):
    def __init__(self) -> None:
        self.var_root = _Var("I:/proj")
        self.var_new_assay_key = _Var("(9000)")
        self.var_new_assay_name = _Var("Header Assay")
        self.var_draft_path = _Var("")
        self.logs: list[str] = []
        self.hints: list[str] = []
        self.loaded = False

    def _set_hint(self, text: str) -> None:
        self.hints.append(text)

    def _log(self, text: str) -> None:
        self.logs.append(text)

    def on_load_draft_into_editor(self, target_path: str | None = None) -> bool:
        if target_path:
            self.var_draft_path.set(target_path)
        self.loaded = True
        return True


def test_on_create_blank_uses_template_header_contract() -> None:
    draft = _DraftActions()
    calls: list[tuple[str, str, str]] = []

    class _Rules:
        def create_draft_from_template(self, assay_key: str, assay_name: str) -> str:
            calls.append(("I:/proj", assay_key, assay_name))
            return str(Path("I:/proj") / "rules" / "drafts" / "(9000).draft.json")

    draft._rules = _Rules()

    draft.on_create_blank()

    assert calls == [("I:/proj", "(9000)", "Header Assay")]
    assert draft.var_draft_path.get().endswith("(9000).draft.json")
    assert draft.loaded is True
    assert any("Header-Vertrag" in line for line in draft.logs)
    assert draft.hints[-1] == "Draft mit Header-Vertrag erstellt."


class _AssayCombo(dict):
    pass


def test_reload_assays_uses_active_inventory_and_keeps_filename_labels() -> None:
    draft = _DraftActions()
    draft.var_assay = _Var("(2222) | AssayB")
    draft.cmb_assay = _AssayCombo()
    draft.assay_display_to_key = {}
    draft.known_assay_keys = set()
    seen: list[str] = []

    class _Item:
        def __init__(self, key: str, ruleset_file: str, assay_name: str) -> None:
            self.assay_key = key
            self.ruleset_file = ruleset_file
            self.assay_name = assay_name

    class _Rules:
        def list_inventory(self, *, kind: str = "all"):
            seen.append(kind)
            return [
                _Item("(1111)", "AssayA.json", "Different Name"),
                _Item("(2222)", "AssayB.json", "AssayB"),
                _Item("", "Skip.json", "Skip"),
            ]

    draft._rules = _Rules()
    draft._reload_assays()

    assert seen == ["active"]
    assert draft.cmb_assay["values"] == ["(1111) | AssayA", "(2222) | AssayB"]
    assert draft.assay_display_to_key["(1111) | AssayA"] == "(1111)"
    assert draft.known_assay_keys == {"(1111)", "(2222)"}
    assert draft.var_assay.get() == "(2222) | AssayB"
    assert draft.hints[-1] == "2 aktive Assays geladen."


def test_reload_assays_missing_index_clears_combo_without_dialog(monkeypatch) -> None:
    draft = _DraftActions()
    draft.var_assay = _Var("keep")
    draft.cmb_assay = _AssayCombo(values=["old"])
    dialogs: list[str] = []

    class _Rules:
        def list_inventory(self, *, kind: str = "all"):
            raise RuntimeError("json_read_failed: rules/index.json: [Errno 2] No such file or directory")

    monkeypatch.setattr(
        "rule_editor.draft_actions.messagebox.showerror",
        lambda *args, **kwargs: dialogs.append("error"),
    )
    draft._rules = _Rules()
    draft._reload_assays()

    assert dialogs == []
    assert draft.cmb_assay["values"] == []
    assert draft.var_assay.get() == "keep"
    assert draft.hints[-1] == "Kein rules/index.json gefunden."


def test_reload_assays_other_index_error_keeps_selection_and_shows_dialog(monkeypatch) -> None:
    draft = _DraftActions()
    draft.var_assay = _Var("keep")
    draft.cmb_assay = _AssayCombo(values=["old"])
    dialogs: list[tuple[str, str]] = []

    class _Rules:
        def list_inventory(self, *, kind: str = "all"):
            raise RuntimeError("json_read_failed: rules/index.json: Expecting value")

    monkeypatch.setattr(
        "rule_editor.draft_actions.messagebox.showerror",
        lambda title, message, **kwargs: dialogs.append((title, message)),
    )
    draft._rules = _Rules()
    draft._reload_assays()

    assert draft.cmb_assay["values"] == ["old"]
    assert draft.var_assay.get() == "keep"
    assert dialogs == [("Fehler", "index.json konnte nicht gelesen werden: json_read_failed: rules/index.json: Expecting value")]
    assert draft.hints == []


def test_reload_assays_without_combo_still_updates_known_keys() -> None:
    draft = _DraftActions()
    draft.var_assay = _Var("keep")
    draft.assay_display_to_key = {"old": "old"}
    draft.known_assay_keys = {"old"}

    class _Item:
        def __init__(self, key: str, ruleset_file: str) -> None:
            self.assay_key = key
            self.ruleset_file = ruleset_file

    class _Rules:
        def list_inventory(self, *, kind: str = "all"):
            assert kind == "active"
            return [_Item("(1111)", "AssayA.json")]

    draft._rules = _Rules()
    draft._reload_assays()
    assert not hasattr(draft, "cmb_assay")
    assert draft.known_assay_keys == {"(1111)"}
    assert draft.assay_display_to_key["(1111) | AssayA"] == "(1111)"
    assert draft.var_assay.get() == "keep"


def test_load_failure_keeps_previous_draft_and_success_clears_dirty(monkeypatch) -> None:
    from rule_editor.draft_actions import DraftMixin

    class _Host(DraftMixin):
        def __init__(self) -> None:
            self.var_draft_path = _Var(r"I:\rules\drafts\keep.draft.json")
            self.current_draft_path = self.var_draft_path.get()
            self.var_new_assay_key = _Var("(keep)")
            self.var_new_assay_name = _Var("Keep")
            self.var_lot_regex = _Var("old-lot")
            self.var_dedupe_fields = _Var("old")
            self.var_excel_filename = _Var("old.xlsx")
            self.var_sheet_template = _Var("old-sheet")
            self.fields_data = [{"key": "OLD"}]
            self.column_mapping_data = {"OLD": "OLD"}
            self._dirty = True
            self._suspend_dirty_tracking = False
            self._undo_stack = [{"assay_key": "(keep)"}]
            self._redo_stack = [{"assay_key": "redo"}]
            self.hints: list[str] = []
            self.logs: list[str] = []
            self.pages: list[str] = []

        def _set_hint(self, text: str) -> None:
            self.hints.append(text)

        def _log(self, text: str) -> None:
            self.logs.append(text)

        def _show_page(self, page: str) -> None:
            self.pages.append(page)

        def _refresh_fields_tree(self) -> None:
            return None

        def _refresh_cols_tree(self) -> None:
            return None

        def _clear_validation_list(self) -> None:
            return None

        def _reset_field_form(self) -> None:
            return None

        def _maybe_refresh_field_markings(self) -> None:
            return None

    class _Rules:
        def __init__(self, payload: dict | None, error: Exception | None = None) -> None:
            self.payload = payload
            self.error = error

        def load_draft(self, path: str) -> dict:
            if self.error is not None:
                raise self.error
            assert path == r"I:\rules\drafts\other.draft.json"
            assert self.payload is not None
            return self.payload

    failed = _Host()
    failed._rules = _Rules(None, RuntimeError("missing draft"))
    monkeypatch.setattr("rule_editor.draft_actions.messagebox.showerror", lambda *_a, **_k: None)
    assert failed.on_load_draft_into_editor(r"I:\rules\drafts\other.draft.json") is False
    assert failed.current_draft_path == r"I:\rules\drafts\keep.draft.json"
    assert failed.var_draft_path.get() == r"I:\rules\drafts\keep.draft.json"
    assert failed._dirty is True
    assert failed.var_new_assay_key.get() == "(keep)"
    assert failed.fields_data == [{"key": "OLD"}]
    assert failed._undo_stack == [{"assay_key": "(keep)"}]
    assert failed.pages == []
    assert failed.logs == []
    assert not any(hint.startswith("Draft geladen:") for hint in failed.hints)

    loaded = _Host()
    loaded._rules = _Rules({"assay_key": "(other)", "assay_name": "Other"})
    assert loaded.on_load_draft_into_editor(r"I:\rules\drafts\other.draft.json") is True
    assert loaded.current_draft_path == r"I:\rules\drafts\other.draft.json"
    assert loaded.var_draft_path.get() == r"I:\rules\drafts\other.draft.json"
    assert loaded._dirty is False
    assert loaded.var_new_assay_key.get() == "(other)"
    assert loaded._undo_stack == []
    assert loaded._redo_stack == []
    assert loaded.pages == ["workspace"]
    assert loaded.logs == [r"Draft geladen: I:\rules\drafts\other.draft.json"]


def test_pick_root_readonly_guards_and_rebind_once(monkeypatch) -> None:
    from rule_editor.draft_actions import DraftMixin
    from rule_editor.manage_actions import ManageMixin

    class _RootVar:
        def __init__(self, value: str, on_set) -> None:
            self.value = value
            self.on_set = on_set
            self.sets: list[str] = []

        def get(self) -> str:
            return self.value

        def set(self, value: str) -> None:
            self.sets.append(value)
            self.value = value
            self.on_set()

    class _Host(DraftMixin, ManageMixin):
        def __init__(self) -> None:
            self.project_root = "I:/old"
            self._rules = object()
            self.binds: list[str] = []
            self.var_root = _RootVar("I:/old", self._on_written)
            self.current_draft_path = "I:/old/rules/drafts/keep.draft.json"
            self.var_draft_path = _Var(self.current_draft_path)
            self._dirty = True
            self._field_form_dirty = False
            self._field_mutation_guard = False
            self._dialog_guard = False
            self._selected_field_key = "alpha"
            self._undo_stack = [{"snapshot": {"k": 1}, "expected_revision": "ab" * 32}]
            self._redo_stack = [{"snapshot": {"k": 2}, "expected_revision": "cd" * 32}]
            self.cleared = 0
            self.assays = 0
            self.overviews = 0
            self.saved: list[bool] = []

        def _on_written(self) -> None:
            self.binds.append(self.var_root.get())
            self._rules = object()

        def _resolve_dirty_field_form(self) -> bool:
            return self.field_ok

        def _clear_loaded_draft(self) -> None:
            self.cleared += 1
            self.current_draft_path = None
            self.var_draft_path.set("")
            self._dirty = False
            self._field_form_dirty = False
            self._selected_field_key = None
            self._undo_stack.clear()
            self._redo_stack.clear()

        def _reload_assays(self) -> None:
            self.assays += 1

        def _refresh_ruleset_overview(self) -> None:
            self.overviews += 1

        def _save_meta_to_draft(self, push_undo: bool = False) -> dict:
            self.saved.append(push_undo)
            if self.save_error:
                raise RuntimeError("meta-save")
            self._dirty = False
            return {}

        def _dialog_parent(self):
            return None

    dialogs: list[str] = []

    def _directory(**_kwargs: object) -> str:
        dialogs.append("dir")
        return chosen["path"]

    def _ask(*_args: object, **_kwargs: object):
        dialogs.append("meta")
        return chosen["meta"]

    monkeypatch.setattr("rule_editor.draft_actions.filedialog.askdirectory", _directory)
    monkeypatch.setattr("rule_editor.manage_actions.messagebox.askyesnocancel", _ask)
    monkeypatch.setattr("rule_editor.manage_actions.messagebox.showerror", lambda *_a, **_k: dialogs.append("error"))

    chosen = {"path": "I:/new", "meta": None}
    host = _Host()
    host.field_ok = False
    host.save_error = False
    host.on_pick_root()
    assert dialogs == []
    assert host.var_root.get() == "I:/old"
    assert host.binds == []

    host.field_ok = True
    chosen["path"] = ""
    host.on_pick_root()
    assert dialogs == ["dir"]
    assert host.binds == []
    assert host.current_draft_path.endswith("keep.draft.json")

    chosen["path"] = "I:/old"
    host.on_pick_root()
    assert host.binds == []
    assert host._undo_stack

    chosen["path"] = "I:/new"
    chosen["meta"] = None
    before_rules = host._rules
    undo = list(host._undo_stack)
    host.on_pick_root()
    assert "meta" in dialogs
    assert host.var_root.get() == "I:/old"
    assert host._rules is before_rules
    assert host._undo_stack == undo
    assert host.cleared == 0

    chosen["meta"] = True
    host.save_error = True
    host.on_pick_root()
    assert host.var_root.get() == "I:/old"
    assert host._rules is before_rules
    assert host.current_draft_path.endswith("keep.draft.json")
    assert "error" in dialogs

    host.save_error = False
    host.on_pick_root()
    assert host.saved == [True, True]
    assert host.var_root.sets == ["I:/new"]
    assert host.binds == ["I:/new"]
    assert host.cleared == 1
    assert host.current_draft_path is None
    assert host._undo_stack == []
    assert host._redo_stack == []
    assert host._selected_field_key is None
    assert host.assays == 1
    assert host.overviews == 1

    discard = _Host()
    discard.field_ok = True
    discard.save_error = False
    chosen["path"] = "I:/other"
    chosen["meta"] = False
    discard.on_pick_root()
    assert discard.saved == []
    assert discard.var_root.sets == ["I:/other"]
    assert discard.binds == ["I:/other"]
    assert discard.cleared == 1
    assert discard._undo_stack == []
    assert discard.assays == 1
