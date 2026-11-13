import json
import tkinter as tk
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.rulesuite.api import (
    REQUIRED_HEADER_FIELD_KEYS,
    check_required_fields,
    create_draft_from_template,
    load_draft,
)


class _Var:
    def __init__(self, value="") -> None:
        self.value = value

    def get(self):
        return self.value

    def set(self, value) -> None:
        self.value = value


@pytest.fixture
def tk_root():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk not available: {exc}")
    try:
        root.geometry("200x100+20+20")
        root.update_idletasks()
        yield root
    finally:
        root.destroy()


def _write_min_template(root: Path) -> None:
    fields = [
        {"key": key, "regex": rf"{key}:\s*(\S+)", "required": False}
        for key in REQUIRED_HEADER_FIELD_KEYS
    ]
    fields[-1]["search_from"] = {"line": 0}
    template = {
        "assay_name": "Template",
        "assay_key": "(0000)",
        "lot_rule": {"regex": r"Lot:\s*(\S+)"},
        "extract_rules": {"fields": fields},
        "excel_rules": {
            "excel_filename_template": "{assay_name}.xlsx",
            "sheetname_template": "{lot_id}",
            "column_mapping": {key: key for key in REQUIRED_HEADER_FIELD_KEYS},
        },
    }
    (root / "rules").mkdir(parents=True)
    (root / "rules" / "index.json").write_text(json.dumps({"assays": []}), encoding="utf-8")
    (root / "rules" / "template.json").write_text(json.dumps(template), encoding="utf-8")


def test_wizard_template_draft_and_required_status(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    _write_min_template(root)

    draft = create_draft_from_template(str(root), "(7777)", "Wizard Assay")
    data = load_draft(draft)
    assert [f["key"] for f in data["extract_rules"]["fields"]] == list(REQUIRED_HEADER_FIELD_KEYS)

    text = "\n".join(f"{key}: VALUE" for key in REQUIRED_HEADER_FIELD_KEYS)
    report = check_required_fields(draft, text, group=1)
    assert report["all_confirmed"] is True


def test_wizard_module_imports_focus_helpers() -> None:
    from rule_editor.wizard import NewRulesetWizard
    from rule_editor.wizard_ui import _REQUIRED_STATUS_LABELS, _SEARCH_MODE_LABELS

    assert NewRulesetWizard is not None
    assert "confirmed" in _REQUIRED_STATUS_LABELS
    assert _SEARCH_MODE_LABELS["none"] == "Gesamten Text durchsuchen"
    assert _SEARCH_MODE_LABELS["after"] == "ab Textmarker"
    assert _SEARCH_MODE_LABELS["line"] == "ab Zeile"


def test_wizard_maps_complete_first_step_before_modal_grab(monkeypatch) -> None:
    from rule_editor.wizard import NewRulesetWizard

    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk not available: {exc}")

    wizard = None
    observed_at_grab: dict[str, object] = {}
    original_grab_set = tk.Toplevel.grab_set

    def recording_grab_set(window) -> None:
        window.update_idletasks()
        observed_at_grab.update(
            title=window.lbl_title.cget("text"),
            title_manager=window.lbl_title.winfo_manager(),
            title_width=window.lbl_title.winfo_width(),
            card_manager=window._card_frames["target"].winfo_manager(),
            card_width=window._card_frames["target"].winfo_width(),
            status=window.var_status.get(),
            mapped=bool(window.winfo_ismapped()),
            viewable=bool(window.winfo_viewable()),
        )
        original_grab_set(window)

    monkeypatch.setattr(tk.Toplevel, "grab_set", recording_grab_set)
    try:
        root.geometry("200x100+20+20")
        root.update_idletasks()
        wizard = NewRulesetWizard(
            root,
            rules=object(),
            on_open_in_editor=lambda _path: None,
            on_activate_requested=lambda _path: None,
        )

        assert observed_at_grab["title"] == "Schritt 1 von 4: PDF und Ziel"
        assert observed_at_grab["title_manager"] == "pack"
        assert observed_at_grab["card_manager"] == "grid"
        assert "PDF" in str(observed_at_grab["status"])
        assert observed_at_grab["mapped"] is True
        assert observed_at_grab["viewable"] is True
        assert int(observed_at_grab["title_width"]) > 1
        assert int(observed_at_grab["card_width"]) > 1
        assert _target_widget_states(wizard) == {
            "rad_mode_new": tk.NORMAL,
            "rad_mode_existing": tk.NORMAL,
            "ent_assay_key": tk.DISABLED,
            "ent_assay_name": tk.DISABLED,
            "list_drafts": tk.DISABLED,
        }

        wizard.var_pdf.set("sample.pdf")
        wizard._finish_text_load("NORMALIZED", None, "sample.pdf", wizard._pdf_request_id)
        assert _target_widget_states(wizard) == {
            "rad_mode_new": tk.NORMAL,
            "rad_mode_existing": tk.NORMAL,
            "ent_assay_key": tk.DISABLED,
            "ent_assay_name": tk.DISABLED,
            "list_drafts": tk.DISABLED,
        }
        wizard.var_mode.set("new")
        assert _target_widget_states(wizard)["ent_assay_key"] == tk.NORMAL
        assert _target_widget_states(wizard)["ent_assay_name"] == tk.NORMAL
        assert _target_widget_states(wizard)["list_drafts"] == tk.DISABLED
        wizard.var_mode.set("existing")
        assert _target_widget_states(wizard)["ent_assay_key"] == tk.DISABLED
        assert _target_widget_states(wizard)["ent_assay_name"] == tk.DISABLED
        assert _target_widget_states(wizard)["list_drafts"] == tk.NORMAL
        wizard.destroy()
        wizard = None

        started = NewRulesetWizard(
            root,
            rules=object(),
            on_open_in_editor=lambda _path: None,
            on_activate_requested=lambda _path: None,
            start_intent="new",
        )
        wizard = started
        assert _target_widget_states(started) == {
            "rad_mode_new": tk.NORMAL,
            "rad_mode_existing": tk.NORMAL,
            "ent_assay_key": tk.NORMAL,
            "ent_assay_name": tk.NORMAL,
            "list_drafts": tk.DISABLED,
        }
        started.var_pdf.set("sample.pdf")
        started._finish_text_load("NORMALIZED", None, "sample.pdf", started._pdf_request_id)
        assert started.var_mode.get() == "new"
        assert _target_widget_states(started) == {
            "rad_mode_new": tk.NORMAL,
            "rad_mode_existing": tk.NORMAL,
            "ent_assay_key": tk.NORMAL,
            "ent_assay_name": tk.NORMAL,
            "list_drafts": tk.DISABLED,
        }
    finally:
        if wizard is not None:
            try:
                wizard.grab_release()
            except tk.TclError:
                pass
            wizard.destroy()
        root.destroy()


def _target_widget_states(wizard: object) -> dict[str, str]:
    names = ("rad_mode_new", "rad_mode_existing", "ent_assay_key", "ent_assay_name", "list_drafts")
    return {name: str(getattr(wizard, name).cget("state")) for name in names}


def test_wizard_has_no_candidate_or_source_assay_path() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "rule_editor" / "wizard.py").read_text(encoding="utf-8")
    ui = (root / "rule_editor" / "wizard_ui.py").read_text(encoding="utf-8")
    combined = source + ui
    for forbidden in (
        "create_draft_from_ruleset",
        "read_candidate_fields",
        "check_candidates",
        "adopt_candidate",
        "ähnlich wie Vorlage",
        "Aehnlich wie Vorlage",
        "_existing_assay",
        "Pflichtfeld",
    ):
        assert forbidden not in combined
    assert "assay_display_to_key" not in source
    assert "get_assay_text" not in source


def test_wizard_constructor_rejects_assay_display_to_key() -> None:
    import inspect

    from rule_editor.wizard import NewRulesetWizard

    assert "assay_display_to_key" not in inspect.signature(NewRulesetWizard.__init__).parameters
    manage = (Path(__file__).resolve().parents[1] / "rule_editor" / "manage_actions.py").read_text(encoding="utf-8")
    assert "assay_display_to_key=" not in manage


def test_stepwise_existing_draft_loads_all_configured_fields(tmp_path: Path) -> None:
    from rule_editor.wizard import NewRulesetWizard

    draft = tmp_path / "existing.draft.json"
    data = {
        "assay_key": "(1111)",
        "assay_name": "Existing",
        "extract_rules": {
            "fields": [
                {"key": "date", "regex": r"Date:\s*(\S+)", "required": True},
                {"key": "optional", "regex": r"Optional:\s*(\S+)", "required": False},
            ]
        },
    }

    class _Rules:
        def load_draft(self, path: str) -> dict:
            assert path == str(draft)
            return data

    wizard = NewRulesetWizard.__new__(NewRulesetWizard)
    wizard._rules = _Rules()
    wizard.var_key = _Var()
    wizard.var_name = _Var()
    wizard.var_mode = _Var("")
    wizard.var_pdf = _Var("")
    wizard.draft_path = None
    wizard._pending_draft_path = None
    wizard._fields = []
    wizard.assay_text = ""
    wizard._pdf_fingerprint = ""

    assert wizard._load_existing_draft(str(draft)) is True
    assert wizard.var_key.get() == "(1111)"
    assert wizard.var_name.get() == "Existing"
    assert [field["key"] for field in wizard._ordered_configured_fields()] == ["date", "optional"]


def test_stepwise_nonempty_match_contract_accepts_zero_only() -> None:
    from rule_editor.wizard import NewRulesetWizard

    assert NewRulesetWizard._row_has_nonempty_value({"matched": True, "value": "0", "error": None}) is True
    assert NewRulesetWizard._row_has_nonempty_value({"matched": True, "value": "  ", "error": None}) is False
    assert NewRulesetWizard._row_has_nonempty_value({"matched": True, "value": None, "error": None}) is False
    assert NewRulesetWizard._row_has_nonempty_value({"matched": False, "value": "x", "error": None}) is False


def test_stepwise_proof_requires_real_preview_then_returns_without_activation(monkeypatch) -> None:
    from rule_editor.wizard import NewRulesetWizard

    calls: list[tuple[str, str, str | None]] = []
    opened: list[str] = []
    errors: list[str] = []

    class _Rules:
        def create_authoring_proof(
            self,
            key: str,
            draft_path: str,
            pdf: str,
            reference_pdf: str | None = None,
        ) -> dict:
            assert reference_pdf is None
            calls.append((pdf, key, draft_path))
            if len(calls) == 1:
                raise RuntimeError("configured_fields_empty: optional")
            return {"draft_sha256": "ok"}

    wizard = NewRulesetWizard.__new__(NewRulesetWizard)
    wizard._rules = _Rules()
    wizard.draft_path = "draft.json"
    wizard.assay_text = "Assay text"
    wizard._normalized_pdf_text = "Assay text"
    wizard.var_finish_action = _Var("activate")
    wizard.var_pdf = _Var("sample.pdf")
    wizard.var_reference_pdf = _Var("")
    wizard.var_key = _Var("(1111)")
    wizard._pdf_fingerprint = "sample.pdf"
    wizard._all_fields_confirmed = lambda: True
    wizard._rules.validate_draft = lambda _path: {"ok": True, "errors": []}
    wizard._rules.diff_draft_vs_active = lambda _key, _path: {"mode": "create"}
    wizard.destroy = lambda: opened.append("destroyed")
    wizard._on_open_in_editor = lambda path: opened.append("editor:" + path)
    wizard._on_activate_requested = lambda _path: pytest.fail("proof success must not activate")
    monkeypatch.setattr(
        "rule_editor.wizard.messagebox.showerror",
        lambda _title, message, **_kwargs: errors.append(str(message)),
    )

    wizard._finish()
    assert errors and "configured_fields_empty" in errors[0]
    assert opened == []

    wizard._finish()
    assert calls == [
        ("sample.pdf", "(1111)", "draft.json"),
        ("sample.pdf", "(1111)", "draft.json"),
    ]
    assert opened == ["destroyed", "editor:draft.json"]


def test_stepwise_existing_rule_requires_reference_pdf(monkeypatch) -> None:
    from rule_editor.wizard import NewRulesetWizard

    warnings: list[str] = []

    class _Rules:
        def create_authoring_proof(self, *_args, **_kwargs) -> dict:
            raise AssertionError("proof must not run without the reference PDF")

    wizard = NewRulesetWizard.__new__(NewRulesetWizard)
    wizard._rules = _Rules()
    wizard.draft_path = "draft.json"
    wizard.assay_text = "Assay text"
    wizard._normalized_pdf_text = "Assay text"
    wizard.var_finish_action = _Var("activate")
    wizard.var_pdf = _Var("failing.pdf")
    wizard.var_reference_pdf = _Var("")
    wizard.var_key = _Var("(1111)")
    wizard._pdf_fingerprint = "failing.pdf"
    wizard._all_fields_confirmed = lambda: True
    wizard._rules.validate_draft = lambda _path: {"ok": True, "errors": []}
    wizard._rules.diff_draft_vs_active = lambda _key, _path: {"mode": "update"}
    monkeypatch.setattr(
        "rule_editor.wizard.messagebox.showwarning",
        lambda _title, message, **_kwargs: warnings.append(str(message)),
    )

    wizard._finish()

    assert warnings and "Referenz-PDF" in warnings[0]


class _SummaryList:
    def __init__(self) -> None:
        self.rows: list[str] = []

    def delete(self, *_args: object) -> None:
        self.rows.clear()

    def insert(self, _index: object, text: str) -> None:
        self.rows.append(text)


def _target_wizard(rules: object):
    from rule_editor.wizard import NewRulesetWizard

    wizard = NewRulesetWizard.__new__(NewRulesetWizard)
    wizard._rules = rules
    wizard.var_status = _Var("")
    wizard.var_mode = _Var("")
    wizard.var_key = _Var("")
    wizard.var_name = _Var("")
    wizard.var_pdf = _Var("")
    wizard.var_f_key = _Var("")
    wizard.var_f_regex = _Var("")
    wizard.var_f_mode = _Var("none")
    wizard.var_f_search_label = _Var("Gesamten Text durchsuchen")
    wizard.var_f_after = _Var("")
    wizard.var_f_line = _Var("")
    wizard.var_match = _Var("")
    wizard.var_custom_count = _Var("")
    wizard.draft_path = None
    wizard._pending_draft_path = None
    wizard._draft_choices = []
    wizard._fields = []
    wizard._field_idx = 0
    wizard._normalized_pdf_text = ""
    wizard.assay_text = ""
    wizard._derived_for = None
    wizard._pdf_fingerprint = ""
    wizard._pdf_request_id = 0
    wizard._closed = False
    wizard._busy = False
    return wizard


def test_new_rule_creates_template_draft_only_after_pdf() -> None:
    calls: list[tuple[str, str]] = []

    class _Rules:
        def list_inventory(self, kind: str = "all") -> list[object]:
            assert kind == "active"
            return []

        def create_draft_from_template_if_missing(self, key: str, name: str) -> dict[str, str]:
            calls.append((key, name))
            if key == "(exists)":
                return {"status": "exists", "draft_path": "old.json", "assay_key": key, "assay_name": name}
            return {"status": "created", "draft_path": "new.json", "assay_key": key, "assay_name": name}

        def load_draft(self, path: str) -> dict:
            assert path == "new.json"
            return {"extract_rules": {"fields": [{"key": "date", "regex": "a"}]}}

    wizard = _target_wizard(_Rules())
    wizard.var_mode.set("new")
    wizard.var_key.set("(7777)")
    wizard.var_name.set("Neu")
    assert wizard._commit_target() is False
    assert calls == []

    wizard.var_pdf.set("sample.txt")
    wizard._normalized_pdf_text = "text"
    wizard._pdf_fingerprint = "sample.txt"
    assert wizard._commit_target() is False
    assert calls == []

    wizard.var_pdf.set("sample.pdf")
    wizard._normalized_pdf_text = "normalized pdf"
    wizard._pdf_fingerprint = "sample.pdf"
    wizard.var_key.set("(exists)")
    assert wizard._commit_target() is False
    assert wizard.draft_path is None
    assert "nicht überschrieben" in wizard.var_status.get()
    assert calls == [("(exists)", "Neu")]

    wizard.var_key.set("(7777)")
    assert wizard._commit_target() is True
    assert wizard.draft_path == "new.json"
    assert calls == [("(exists)", "Neu"), ("(7777)", "Neu")]
    assert not hasattr(wizard._rules, "create_draft_from_ruleset")


def test_existing_mode_lists_only_drafts_and_does_not_create(tk_root) -> None:
    class _Item:
        def __init__(self, kind: str, key: str, path: str) -> None:
            self.kind = kind
            self.assay_key = key
            self.assay_name = key
            self.path = path

    class _Rules:
        def list_inventory(self, kind: str = "all") -> list[object]:
            assert kind == "draft"
            return [
                _Item("draft", "(d1)", "drafts/d1.json"),
                _Item("active", "(a1)", "rules/a1.json"),
                _Item("history", "(h1)", "history/h1.json"),
            ]

        def load_draft(self, path: str) -> dict:
            assert path == "drafts/d1.json"
            return {
                "assay_key": "(d1)",
                "assay_name": "Entwurf",
                "extract_rules": {"fields": [{"key": "date"}, {"key": "value"}]},
            }

        def create_draft_from_template_if_missing(self, *_args: object) -> dict:
            raise AssertionError("existing mode must not create a draft")

    wizard = _target_wizard(_Rules())
    wizard.list_drafts = tk.Listbox(tk_root, state=tk.DISABLED)
    wizard._refresh_draft_choices()
    assert wizard.list_drafts.get(0, tk.END) == ("(d1)  (d1)",)
    assert wizard.list_drafts.cget("state") == tk.DISABLED

    wizard.var_mode.set("existing")
    wizard._apply_target_control_states()
    assert wizard.list_drafts.cget("state") == tk.NORMAL
    assert wizard._pdf_ready() is False
    assert wizard._commit_target() is False
    assert wizard.draft_path is None

    wizard.list_drafts.selection_set(0)
    wizard._on_draft_selected()
    assert wizard._pending_draft_path == "drafts/d1.json"
    assert wizard.draft_path == "drafts/d1.json"
    assert wizard.var_key.get() == "(d1)"
    assert wizard.var_name.get() == "Entwurf"
    assert wizard._commit_target() is False

    wizard.var_pdf.set("problem.pdf")
    wizard._normalized_pdf_text = "PDF"
    wizard.assay_text = "PDF"
    wizard._pdf_fingerprint = "problem.pdf"
    assert wizard._commit_target() is True
    assert wizard.draft_path == "drafts/d1.json"
    assert [field["key"] for field in wizard._fields] == ["date", "value"]


@pytest.mark.parametrize("state", [tk.NORMAL, tk.DISABLED])
def test_real_draft_list_refresh_preserves_state_selection_and_clears_stale_rows(tk_root, state: str) -> None:
    other = SimpleNamespace(kind="draft", path="other.draft.json", assay_key="(1111)", assay_name="Other")
    wanted = SimpleNamespace(kind="draft", path="wanted.draft.json", assay_key="(1111)", assay_name="Wanted")

    class _Rules:
        items = [other, wanted]
        fail = False

        def list_inventory(self, *, kind: str) -> list:
            assert kind == "draft"
            if self.fail:
                raise RuntimeError("inventory unavailable")
            return self.items

    rules = _Rules()
    wizard = _target_wizard(rules)
    wizard._pending_draft_path = wanted.path
    wizard.list_drafts = tk.Listbox(tk_root)
    wizard.list_drafts.insert(tk.END, "stale row")
    wizard.list_drafts.configure(state=state)

    wizard._refresh_draft_choices()
    assert wizard.list_drafts.get(0, tk.END) == ("(1111)  Other", "(1111)  Wanted")
    assert wizard.list_drafts.curselection() == (1,)
    assert wizard.list_drafts.cget("state") == state
    assert [choice["path"] for choice in wizard._draft_choices] == [other.path, wanted.path]

    rules.items = [wanted]
    wizard._refresh_draft_choices()
    assert wizard.list_drafts.get(0, tk.END) == ("(1111)  Wanted",)
    assert wizard.list_drafts.curselection() == (0,)
    assert wizard.list_drafts.cget("state") == state
    assert [choice["path"] for choice in wizard._draft_choices] == [wanted.path]

    rules.fail = True
    wizard._refresh_draft_choices()
    assert wizard.list_drafts.size() == 0
    assert wizard._draft_choices == []
    assert wizard.list_drafts.cget("state") == state
    assert "inventory unavailable" in wizard.var_status.get()


@pytest.mark.parametrize("initial_draft_path", ["a.draft.json", None])
def test_failed_draft_selection_restores_loaded_context_or_disables_continuation(
    tk_root, monkeypatch, initial_draft_path: str | None
) -> None:
    from rule_editor.wizard import NewRulesetWizard

    errors: list[str] = []
    opened: list[str] = []

    class _Rules:
        def list_inventory(self, *, kind: str) -> list:
            assert kind == "draft"
            return [
                SimpleNamespace(kind="draft", path="a.draft.json", assay_key="(a)", assay_name="A"),
                SimpleNamespace(kind="draft", path="b.draft.json", assay_key="(b)", assay_name="B"),
            ]

        def load_draft(self, path: str) -> dict:
            if path == "b.draft.json":
                raise RuntimeError("B cannot be loaded")
            assert path == "a.draft.json"
            return {
                "assay_key": "(a)",
                "assay_name": "A",
                "extract_rules": {"fields": [{"key": "value", "regex": ""}]},
            }

        def diff_draft_vs_active(self, key: str, path: str) -> dict:
            assert (key, path) == ("(a)", "a.draft.json")
            return {"mode": "create"}

        def validate_draft(self, path: str) -> dict:
            assert path == "a.draft.json"
            return {"ok": False, "errors": ["unfinished"]}

    monkeypatch.setattr(
        "rule_editor.wizard.messagebox.showerror",
        lambda _title, message, **_kwargs: errors.append(str(message)),
    )
    wizard = NewRulesetWizard(
        tk_root,
        rules=_Rules(),
        initial_draft_path=initial_draft_path,
        on_open_in_editor=opened.append,
        on_activate_requested=lambda _path: pytest.fail("a failed draft switch must not activate"),
    )
    try:
        wizard.var_mode.set("existing")
        wizard.list_drafts.selection_clear(0, tk.END)
        wizard.list_drafts.selection_set(1)
        wizard._on_draft_selected()

        assert errors == ["B cannot be loaded"]
        assert wizard._pending_draft_path == initial_draft_path
        assert wizard.draft_path == initial_draft_path
        if initial_draft_path:
            assert wizard.list_drafts.curselection() == (0,)
            assert (wizard.var_key.get(), wizard.var_name.get()) == ("(a)", "A")
            assert wizard.btn_continue_draft.cget("state") == tk.NORMAL
            wizard.btn_continue_draft.invoke()
            assert wizard._step == 3
            wizard.btn_next.invoke()
            assert opened == [initial_draft_path]
        else:
            assert wizard.list_drafts.curselection() == ()
            assert wizard.btn_continue_draft.cget("state") == tk.DISABLED
            wizard.btn_continue_draft.invoke()
            assert wizard._step == 0
            assert opened == []
    finally:
        if not wizard._closed:
            wizard.destroy()


@pytest.mark.parametrize("start_intent", ["neutral", "new"])
def test_loaded_draft_is_preselected_and_can_continue_without_pdf(tk_root, start_intent: str) -> None:
    from rule_editor.wizard import NewRulesetWizard

    opened: list[str] = []
    activated: list[str] = []
    closed: list[str | None] = []
    checks: list[str] = []
    target = "loaded.draft.json"

    class _Rules:
        def list_inventory(self, *, kind: str) -> list:
            assert kind == "draft"
            return [
                SimpleNamespace(kind="draft", path="other.draft.json", assay_key="(1111)", assay_name="Other"),
                SimpleNamespace(kind="draft", path=target, assay_key="(1111)", assay_name="Loaded"),
            ]

        def load_draft(self, path: str) -> dict:
            assert path == target
            return {
                "assay_key": "(1111)",
                "assay_name": "Loaded",
                "extract_rules": {"fields": [{"key": "value", "regex": ""}]},
            }

        def diff_draft_vs_active(self, key: str, path: str) -> dict:
            assert (key, path) == ("(1111)", target)
            checks.append("diff")
            return {"mode": "update"}

        def validate_draft(self, path: str) -> dict:
            assert path == target
            checks.append("structure")
            return {"ok": False, "errors": ["unfinished draft"]}

        def create_authoring_proof(self, *_args, **_kwargs) -> dict:
            pytest.fail("continuing a draft must not create activation proof")

    wizard = NewRulesetWizard(
        tk_root,
        rules=_Rules(),
        initial_draft_path=target,
        start_intent=start_intent,
        on_open_in_editor=opened.append,
        on_activate_requested=activated.append,
        on_session_closed=closed.append,
    )
    try:
        assert isinstance(wizard.list_drafts, tk.Listbox)
        assert wizard.list_drafts.size() == 2
        assert wizard.list_drafts.curselection() == (1,)
        assert wizard.list_drafts.cget("state") == tk.NORMAL
        assert wizard.var_mode.get() == "existing"
        assert (wizard.var_key.get(), wizard.var_name.get()) == ("(1111)", "Loaded")
        assert wizard.draft_path == target
        assert wizard._pdf_ready() is False
        assert checks == []

        wizard.btn_continue_draft.invoke()
        assert wizard._step == 3
        assert wizard.var_finish_action.get() == "editor"
        assert checks == ["diff", "structure"]
        assert "weiterbearbeitet" in wizard.lbl_required_summary.cget("text")
        assert wizard.var_reference_pdf.get() == ""
        wizard.btn_back.invoke()
        assert wizard._step == 0
        assert wizard.draft_path == target
        assert wizard.list_drafts.curselection() == (1,)
        assert wizard._pdf_ready() is False
        wizard.btn_continue_draft.invoke()
        assert wizard._step == 3
        wizard.btn_next.invoke()
        assert opened == [target]
        assert closed == [target]
        assert activated == []
        assert checks == ["diff", "structure", "diff", "structure"]
    finally:
        if not wizard._closed:
            wizard.destroy()


def test_draft_selection_loads_identity_and_fields_once_even_if_a_second_read_would_fail(tk_root, monkeypatch) -> None:
    from rule_editor.wizard import NewRulesetWizard

    loads: list[str] = []
    errors: list[str] = []

    class _Rules:
        def list_inventory(self, *, kind: str) -> list:
            assert kind == "draft"
            return [
                SimpleNamespace(kind="draft", path="a.draft.json", assay_key="(a)", assay_name="A"),
                SimpleNamespace(kind="draft", path="b.draft.json", assay_key="(b)", assay_name="B"),
            ]

        def load_draft(self, path: str) -> dict:
            loads.append(path)
            if loads.count(path) > 1:
                raise RuntimeError("second read failed")
            identity = "a" if path == "a.draft.json" else "b"
            return {
                "assay_key": f"({identity})",
                "assay_name": identity.upper(),
                "extract_rules": {"fields": [{"key": f"{identity}_field", "regex": ""}]},
            }

    monkeypatch.setattr(
        "rule_editor.wizard.messagebox.showerror",
        lambda _title, message, **_kwargs: errors.append(str(message)),
    )
    wizard = NewRulesetWizard(tk_root, rules=_Rules(), initial_draft_path="a.draft.json")
    try:
        assert loads == ["a.draft.json"]
        wizard.list_drafts.selection_clear(0, tk.END)
        wizard.list_drafts.selection_set(1)
        wizard._on_draft_selected()

        assert loads == ["a.draft.json", "b.draft.json"]
        assert errors == []
        assert wizard.list_drafts.curselection() == (1,)
        assert wizard._pending_draft_path == wizard.draft_path == "b.draft.json"
        assert (wizard.var_key.get(), wizard.var_name.get()) == ("(b)", "B")
        assert wizard._fields == [{"key": "b_field", "regex": ""}]
        assert wizard.btn_continue_draft.cget("state") == tk.NORMAL
    finally:
        wizard.destroy()


@pytest.mark.parametrize("via_navigation", [False, True])
def test_existing_draft_field_testing_commits_one_consistent_read(via_navigation: bool) -> None:
    loads: list[str] = []
    fields = [{"key": "b_first", "regex": "first"}, {"key": "b_second", "regex": "second"}]

    class _Rules:
        def load_draft(self, path: str) -> dict:
            loads.append(path)
            if len(loads) > 1:
                raise RuntimeError("second read failed")
            return {"assay_key": "(b)", "assay_name": "B", "extract_rules": {"fields": fields}}

        def derive_assay_block(self, text: str, key: str, name: str) -> str:
            assert (text, key, name) == ("NORMALIZED", "(b)", "B")
            return "BLOCK B"

    wizard = _target_wizard(_Rules())
    wizard.draft_path = "a.draft.json"
    wizard._pending_draft_path = "b.draft.json"
    wizard.var_mode.set("existing")
    wizard.var_key.set("(a)")
    wizard.var_name.set("A")
    wizard._fields = [{"key": "a_field"}]
    wizard.var_pdf.set("sample.pdf")
    wizard._pdf_fingerprint = "sample.pdf"
    wizard._normalized_pdf_text = "NORMALIZED"
    shown: list[int] = []
    wizard._step = 0
    wizard._show_step = shown.append
    wizard._show_current_field = lambda: None

    if via_navigation:
        wizard._on_next()
        assert shown == [1]
    else:
        assert wizard._commit_existing_draft() is True

    assert loads == ["b.draft.json"]
    assert wizard._pending_draft_path == wizard.draft_path == "b.draft.json"
    assert (wizard.var_key.get(), wizard.var_name.get()) == ("(b)", "B")
    assert wizard._fields == fields
    assert wizard.assay_text == "BLOCK B"
    assert wizard._derived_for == ("existing", "(b)", "B")


def test_failed_existing_draft_preparation_keeps_previous_identity_fields_and_text() -> None:
    loads: list[str] = []

    class _Rules:
        def load_draft(self, path: str) -> dict:
            loads.append(path)
            return {"assay_key": "(b)", "assay_name": "B", "extract_rules": {"fields": [{"key": "b_field"}]}}

        def derive_assay_block(self, *_args) -> str:
            raise RuntimeError("derive failed")

    wizard = _target_wizard(_Rules())
    wizard._pending_draft_path = wizard.draft_path = "a.draft.json"
    wizard.var_mode.set("existing")
    wizard.var_key.set("(a)")
    wizard.var_name.set("A")
    wizard._fields = [{"key": "a_field"}]
    wizard.assay_text = "BLOCK A"
    wizard._derived_for = ("existing", "(a)", "A")
    wizard.var_pdf.set("sample.pdf")
    wizard._pdf_fingerprint = "sample.pdf"
    wizard._normalized_pdf_text = "NORMALIZED"

    assert wizard._load_existing_draft("b.draft.json") is False

    assert loads == ["b.draft.json"]
    assert wizard._pending_draft_path == wizard.draft_path == "a.draft.json"
    assert (wizard.var_key.get(), wizard.var_name.get()) == ("(a)", "A")
    assert wizard._fields == [{"key": "a_field"}]
    assert wizard.assay_text == "BLOCK A"
    assert wizard._derived_for == ("existing", "(a)", "A")
    assert "derive failed" in wizard.var_status.get()


@pytest.mark.parametrize("regex", ["", r"Missing:\s*(\S+)", "("])
def test_unfinished_field_edits_are_saved_before_continuing_to_summary(tmp_path: Path, regex: str) -> None:
    from src.rulesuite.api import update_field as update_draft_field

    path = tmp_path / "unfinished.draft.json"
    path.write_text(json.dumps({"extract_rules": {"fields": [{"key": "value", "regex": "old"}]}}), encoding="utf-8")

    class _Rules:
        load_draft = staticmethod(load_draft)
        update_field = staticmethod(update_draft_field)

        def test_regex(self, *_args, **_kwargs) -> dict:
            pytest.fail("saving an unfinished field must not require a match")

    wizard = _target_wizard(_Rules())
    wizard.draft_path = str(path)
    wizard._reload_fields()
    wizard._step = 1
    wizard.var_f_key.set("value")
    wizard.var_f_regex.set(regex)
    wizard.var_f_mode.set("after")
    wizard.var_f_after.set("anchor")
    wizard.var_finish_action = _Var("activate")
    shown: list[int] = []
    wizard._show_step = shown.append

    wizard._on_continue_draft()

    assert shown == [3]
    assert wizard.var_finish_action.get() == "editor"
    saved = load_draft(str(path))["extract_rules"]["fields"][0]
    assert saved["regex"] == regex
    assert saved["search_from"] == {"after": "anchor"}


def test_failed_unfinished_field_save_keeps_form_and_does_not_leave_fields(monkeypatch) -> None:
    class _Rules:
        def update_field(self, *_args, **_kwargs) -> str:
            raise RuntimeError("save failed")

    wizard = _target_wizard(_Rules())
    wizard.draft_path = "draft.json"
    wizard._fields = [{"key": "value", "regex": "old"}]
    wizard._step = 1
    wizard.var_f_key.set("value")
    wizard.var_f_regex.set("unfinished change")
    shown: list[int] = []
    errors: list[str] = []
    wizard._show_step = shown.append
    monkeypatch.setattr(
        "rule_editor.wizard.messagebox.showerror",
        lambda _title, message, **_kwargs: errors.append(str(message)),
    )

    wizard._on_continue_draft()

    assert shown == []
    assert errors == ["save failed"]
    assert wizard.var_f_regex.get() == "unfinished change"
    assert wizard._fields == [{"key": "value", "regex": "old"}]


def test_custom_step_reaches_summary_without_confirmed_fields() -> None:
    wizard = _target_wizard(object())
    wizard._step = 2
    wizard.draft_path = "draft.json"
    wizard._all_fields_confirmed = lambda: pytest.fail("summary must allow unfinished fields")
    shown: list[int] = []
    wizard._show_step = shown.append

    wizard._on_next()

    assert shown == [3]


@pytest.mark.parametrize(
    ("step", "pdf_ready", "expected_step"),
    [(3, False, 0), (2, False, 0), (1, False, 0), (3, True, 2), (2, True, 1)],
)
def test_back_navigation_enters_field_testing_only_with_loaded_pdf(
    step: int, pdf_ready: bool, expected_step: int
) -> None:
    wizard = _target_wizard(object())
    wizard._step = step
    wizard._fields = [{"key": "value"}]
    wizard._pdf_ready = lambda: pdf_ready
    wizard._reload_fields = lambda: None
    shown: list[int] = []
    field_visits: list[str] = []
    wizard._show_step = shown.append
    wizard._show_current_field = lambda: field_visits.append("field")

    wizard._on_back()

    assert shown == [expected_step]
    assert field_visits == (["field"] if expected_step == 1 else [])


def test_editor_continuation_retains_draft_without_any_activation_checks(tmp_path: Path) -> None:
    path = tmp_path / "unfinished.draft.json"
    path.write_text('{"extract_rules":{"fields":[]}}', encoding="utf-8")
    before = path.read_bytes()
    wizard = _target_wizard(object())
    wizard.draft_path = str(path)
    wizard.var_finish_action = _Var("editor")
    wizard._pdf_ready = lambda: pytest.fail("continuation must not require a PDF")
    wizard._all_fields_confirmed = lambda: pytest.fail("continuation must not require field hits")
    opened: list[str] = []
    closed: list[str | None] = []
    wizard._on_open_in_editor = opened.append
    wizard._on_session_closed = closed.append
    wizard._on_activate_requested = lambda _path: pytest.fail("continuation must never activate")
    wizard.destroy = lambda: None

    wizard._finish()

    assert wizard._closed is True
    assert opened == [str(path)]
    assert closed == [str(path)]
    assert path.read_bytes() == before


@pytest.mark.parametrize("blocker", ["pdf", "structure", "structure_error", "mode"])
def test_activation_stays_blocked_on_missing_pdf_or_readiness_errors(monkeypatch, blocker: str) -> None:
    proofs: list[str] = []
    messages: list[str] = []

    class _Rules:
        def validate_draft(self, _path: str) -> dict:
            if blocker == "structure_error":
                raise RuntimeError("validation failed")
            return {"ok": blocker != "structure", "errors": ["unfinished"]}

        def diff_draft_vs_active(self, *_args) -> dict:
            return {"mode": "unknown"}

        def create_authoring_proof(self, *_args, **_kwargs) -> dict:
            proofs.append("proof")
            return {}

    wizard = _target_wizard(_Rules())
    wizard.draft_path = "draft.json"
    wizard.var_finish_action = _Var("activate")
    wizard._pdf_ready = lambda: blocker != "pdf"
    wizard._all_fields_confirmed = lambda: True
    wizard._shutdown = lambda _action: pytest.fail("activation must remain blocked")
    monkeypatch.setattr(
        "rule_editor.wizard.messagebox.showwarning",
        lambda _title, message, **_kwargs: messages.append(str(message)),
    )
    monkeypatch.setattr(
        "rule_editor.wizard.messagebox.showerror",
        lambda _title, message, **_kwargs: messages.append(str(message)),
    )

    wizard._finish()

    assert proofs == []
    assert len(messages) == 1


def test_configured_fields_are_checked_in_order_and_empty_blocks_save() -> None:
    updates: list[str] = []

    class _Rules:
        def test_regex(self, text: str, regex: str, *, group: int = 1, search_from: object = None) -> dict:
            assert text == "PDF"
            if regex == "empty":
                return {"matched": True, "value": "", "error": None}
            if regex == "zero":
                return {"matched": True, "value": "0", "error": None, "span": [0, 1]}
            return {"matched": False, "value": None, "error": "bad"}

        def update_field(self, draft_path: str, key: str, *, regex: str, search_from: object = None) -> str:
            updates.append(key)
            return draft_path

        def locate_fields(self, draft_path: str, assay_text: str, *, group: int = 1) -> dict:
            return {
                "results": [
                    {"key": "date", "matched": True, "value": "0", "error": None},
                    {"key": "note", "matched": True, "value": "", "error": None},
                ]
            }

        def load_draft(self, _path: str) -> dict:
            return {
                "extract_rules": {
                    "fields": [
                        {"key": "date", "regex": "zero"},
                        {"key": "note", "regex": "empty"},
                    ]
                }
            }

    wizard = _target_wizard(_Rules())
    wizard.draft_path = "draft.json"
    wizard.assay_text = "PDF"
    wizard._reload_fields()
    wizard._field_idx = 0
    wizard._apply_search_from_value(None)
    wizard.var_f_key.set("date")
    wizard.var_f_regex.set("zero")
    assert wizard._save_current_field() is True
    wizard._field_idx = 1
    wizard.var_f_key.set("note")
    wizard.var_f_regex.set("empty")
    assert wizard._save_current_field() is False
    assert updates == ["date"]
    assert wizard._all_fields_confirmed() is False


def test_custom_field_can_be_tested_added_and_repeated() -> None:
    added: list[str] = []

    class _Rules:
        def test_regex(self, _text: str, regex: str, *, group: int = 1, search_from: object = None) -> dict:
            if not regex:
                return {"matched": False, "value": None, "error": None}
            return {"matched": True, "value": "0", "error": None}

        def add_field(self, draft_path: str, key: str, regex: str, *, required: bool = False, search_from: object = None) -> str:
            added.append(key)
            return draft_path

        def load_draft(self, _path: str) -> dict:
            return {"extract_rules": {"fields": [{"key": key, "regex": "x"} for key in added]}}

    wizard = _target_wizard(_Rules())
    wizard.draft_path = "draft.json"
    wizard.assay_text = "PDF"
    wizard.var_f_regex.set("bad")
    assert wizard._test_current_pattern()["value"] == "0"
    wizard.var_f_key.set("extra")
    wizard._on_add_custom()
    assert added == ["extra"]
    assert wizard.var_f_key.get() == ""
    wizard.var_f_key.set("extra2")
    wizard.var_f_regex.set("also")
    wizard._on_add_custom()
    assert added == ["extra", "extra2"]


def test_update_reference_must_differ_and_create_skips_it(monkeypatch) -> None:
    from rule_editor.wizard import NewRulesetWizard

    proofs: list[tuple[str, str | None]] = []
    warnings: list[str] = []

    class _Rules:
        def validate_draft(self, _path: str) -> dict:
            return {"ok": True, "errors": []}

        def diff_draft_vs_active(self, key: str, draft_path: str) -> dict:
            assert (key, draft_path) == ("(1111)", "draft.json")
            return {"mode": self.mode}

        def locate_fields(self, *_args: object, **_kwargs: object) -> dict:
            return {"results": [{"key": "date", "matched": True, "value": "0", "error": None}]}

        def load_draft(self, _path: str) -> dict:
            return {"extract_rules": {"fields": [{"key": "date"}]}}

        def create_authoring_proof(self, _key: str, _draft: str, pdf: str, reference: str | None = None) -> dict:
            proofs.append((pdf, reference))
            return {"ok": True}

        mode = "update"

    wizard = NewRulesetWizard.__new__(NewRulesetWizard)
    wizard._rules = _Rules()
    wizard.draft_path = "draft.json"
    wizard.assay_text = "PDF"
    wizard._normalized_pdf_text = "PDF"
    wizard.var_pdf = _Var(r"I:\pdfs\problem.pdf")
    wizard.var_reference_pdf = _Var(r"I:\pdfs\problem.pdf")
    wizard._pdf_fingerprint = r"I:\pdfs\problem.pdf"
    wizard.var_key = _Var("(1111)")
    wizard.var_finish_action = _Var("activate")
    wizard._on_session_closed = None
    wizard._on_open_in_editor = lambda _path: None
    wizard._on_activate_requested = lambda _path: proofs.append(("activated", None))
    wizard.destroy = lambda: None
    monkeypatch.setattr(
        "rule_editor.wizard.messagebox.showwarning",
        lambda _title, message, **_kwargs: warnings.append(str(message)),
    )
    monkeypatch.setattr("rule_editor.wizard.messagebox.showerror", lambda *_args, **_kwargs: None)

    wizard._finish()
    assert proofs == []
    assert warnings and "andere Datei" in warnings[0]

    wizard._rules.mode = "create"
    wizard.var_reference_pdf.set(r"I:\pdfs\problem.pdf")
    wizard._finish()
    assert proofs == [(r"I:\pdfs\problem.pdf", None)]  # Proof success has no activation callback.


def test_proof_is_blocked_until_every_configured_field_hits(monkeypatch) -> None:
    proofs: list[str] = []

    class _Rules:
        def validate_draft(self, _path: str) -> dict:
            return {"ok": True, "errors": []}

        def diff_draft_vs_active(self, *_args: object) -> dict:
            return {"mode": "create"}

        def create_authoring_proof(self, *_args: object, **_kwargs: object) -> dict:
            proofs.append("proof")
            return {}

    from rule_editor.wizard import NewRulesetWizard

    wizard = NewRulesetWizard.__new__(NewRulesetWizard)
    wizard._rules = _Rules()
    wizard.draft_path = "draft.json"
    wizard.assay_text = "PDF"
    wizard._normalized_pdf_text = "PDF"
    wizard.var_pdf = _Var("problem.pdf")
    wizard.var_reference_pdf = _Var("")
    wizard._pdf_fingerprint = "problem.pdf"
    wizard.var_key = _Var("(1111)")
    wizard.var_finish_action = _Var("activate")
    wizard._all_fields_confirmed = lambda: False
    monkeypatch.setattr(
        "rule_editor.wizard.messagebox.showwarning",
        lambda *_args, **_kwargs: None,
    )

    wizard._finish()
    assert proofs == []


def test_neutral_pdf_load_precedes_mode_key_and_draft() -> None:
    calls: list[str] = []

    class _Rules:
        def load_normalized_pdf_text(self, pdf: str) -> str:
            calls.append(pdf)
            return "NORMALIZED"

        def get_assay_text(self, *_args: object, **_kwargs: object) -> dict:
            raise AssertionError("neutral load must not call get_assay_text")

        def list_inventory(self, *_args: object, **_kwargs: object) -> list:
            raise AssertionError("neutral load must not read the rule index")

    wizard = _target_wizard(_Rules())
    assert wizard.var_mode.get() == ""
    assert wizard.var_key.get() == ""
    assert wizard.var_name.get() == ""
    wizard.var_pdf.set("sample.pdf")
    wizard._pdf_request_id = 1
    wizard._closed = False

    published: list[object] = []

    def _after(_delay: int, callback) -> None:
        published.append(callback)
        callback()

    wizard.after = _after
    wizard._load_text_thread(wizard._rules, "sample.pdf", 1)
    assert calls == ["sample.pdf"]
    assert wizard._normalized_pdf_text == "NORMALIZED"
    assert wizard._pdf_fingerprint == "sample.pdf"
    assert wizard.assay_text == ""
    assert wizard._pdf_ready() is True

    wizard.var_mode.set("new")
    wizard.var_key.set("(7777)")
    wizard.var_name.set("Neu")
    assert wizard._pdf_ready() is True
    assert wizard._normalized_pdf_text == "NORMALIZED"


def test_stale_pdf_callback_does_not_publish_ready_state() -> None:
    wizard = _target_wizard(object())
    wizard.var_pdf.set("sample.pdf")
    wizard._pdf_request_id = 2
    wizard._finish_text_load("NEU", None, "sample.pdf", 1)
    assert wizard._normalized_pdf_text == ""
    assert wizard._pdf_fingerprint == ""
    assert wizard._pdf_ready() is False

    wizard._pdf_request_id = 3
    wizard.var_pdf.set("other.pdf")
    wizard._finish_text_load("NEU", None, "sample.pdf", 3)
    assert wizard._normalized_pdf_text == ""
    assert wizard._pdf_ready() is False

    wizard._closed = True
    wizard.var_pdf.set("sample.pdf")
    wizard._pdf_request_id = 4
    wizard._finish_text_load("NEU", None, "sample.pdf", 4)
    assert wizard._normalized_pdf_text == ""

    def _after_tcl(_delay: int, _callback: object) -> None:
        raise tk.TclError("application has been destroyed")

    wizard.after = _after_tcl
    wizard._schedule_ui(lambda: (_ for _ in ()).throw(AssertionError("callback ran")))

    def _after_runtime(_delay: int, _callback: object) -> None:
        raise RuntimeError("main thread is not in main loop")

    wizard.after = _after_runtime
    wizard._schedule_ui(lambda: (_ for _ in ()).throw(AssertionError("callback ran")))


def test_target_block_uses_normalized_text_and_fulltext_fallback() -> None:
    seen: list[tuple[str, str, str]] = []

    class _Rules:
        def list_inventory(self, kind: str = "all") -> list[object]:
            return []

        def derive_assay_block(self, text: str, key: str, name: str) -> str:
            seen.append((text, key, name))
            if key == "(miss)":
                return ""
            if key == "(boom)":
                raise RuntimeError("derive_internal")
            return f"BLOCK {key}"

        def create_draft_from_template_if_missing(self, key: str, name: str) -> dict[str, str]:
            seen.append(("create", key, name))
            return {"status": "created", "draft_path": "new.json", "assay_key": key, "assay_name": name}

        def load_draft(self, _path: str) -> dict:
            return {"extract_rules": {"fields": []}}

        def get_assay_text(self, *_args: object, **_kwargs: object) -> dict:
            raise AssertionError("target split must not call get_assay_text")

    wizard = _target_wizard(_Rules())
    wizard.var_mode.set("new")
    wizard.var_pdf.set("sample.pdf")
    wizard._normalized_pdf_text = "FULL"
    wizard._pdf_fingerprint = "sample.pdf"
    wizard.var_key.set("(7777)")
    wizard.var_name.set("Neu")
    assert wizard._commit_target() is True
    assert seen[:2] == [("FULL", "(7777)", "Neu"), ("create", "(7777)", "Neu")]
    assert wizard.assay_text == "BLOCK (7777)"
    wizard.var_key.set("(other)")
    wizard._on_target_identity_changed()
    assert wizard.assay_text == ""
    assert wizard._normalized_pdf_text == "FULL"
    assert wizard._pdf_ready() is True

    wizard.draft_path = None
    wizard.var_key.set("(miss)")
    wizard.var_name.set("Fehlt")
    assert wizard._commit_target() is True
    assert wizard.assay_text == "FULL"
    assert "Assay-Abschnitt nicht gefunden" in wizard.var_status.get()
    assert "Authoring-Hilfe" in wizard.var_status.get()
    assert wizard._using_fulltext_fallback is True
    assert wizard._normalized_pdf_text == "FULL"
    created_before = [item for item in seen if item[0] == "create"]
    wizard.draft_path = None
    wizard.var_key.set("(boom)")
    wizard.var_name.set("Fehler")
    assert wizard._commit_target() is False
    assert wizard.draft_path is None
    assert [item for item in seen if item[0] == "create"] == created_before
    assert "nicht abgeleitet" in wizard.var_status.get()


def test_existing_draft_unexpected_derive_blocks_without_writing(tmp_path: Path) -> None:
    draft = tmp_path / "existing.draft.json"
    draft.write_text('{"assay_key":"(1111)","assay_name":"Alt"}', encoding="utf-8")
    before = draft.read_bytes()
    writes: list[str] = []

    class _Rules:
        def load_draft(self, path: str) -> dict:
            assert path == str(draft)
            return {"assay_key": "(1111)", "assay_name": "Alt", "extract_rules": {"fields": []}}

        def save_draft(self, path: str, _data: dict) -> str:
            writes.append(path)
            return path

        def derive_assay_block(self, _text: str, _key: str, _name: str) -> str:
            raise RuntimeError("derive_internal")

    wizard = _target_wizard(_Rules())
    wizard.var_mode.set("existing")
    wizard.var_pdf.set("sample.pdf")
    wizard._normalized_pdf_text = "FULL"
    wizard._pdf_fingerprint = "sample.pdf"
    wizard._pending_draft_path = str(draft)
    assert wizard._commit_target() is False
    assert wizard.draft_path is None
    assert writes == []
    assert draft.read_bytes() == before
    assert "nicht abgeleitet" in wizard.var_status.get()


def test_fulltext_warning_stays_visible_and_proof_explains_split(monkeypatch) -> None:
    from rule_editor.wizard import NewRulesetWizard, _FULLTEXT_FALLBACK_WARNING

    errors: list[str] = []

    class _Config:
        def config(self, **_kwargs: object) -> None:
            return None

        def configure(self, **_kwargs: object) -> None:
            return None

    class _Card:
        def tkraise(self) -> None:
            return None

    class _Rules:
        def diff_draft_vs_active(self, *_args: object) -> dict:
            return {"mode": "create"}

        def locate_fields(self, *_args: object, **_kwargs: object) -> dict:
            return {"results": [{"key": "lot", "matched": True, "value": "A", "error": None}]}

        def validate_draft(self, _path: str) -> dict:
            return {"ok": True, "errors": []}

        def create_authoring_proof(self, *_args: object, **_kwargs: object) -> dict:
            raise RuntimeError("assay_block_empty")

    wizard = NewRulesetWizard.__new__(NewRulesetWizard)
    wizard._rules = _Rules()
    wizard._using_fulltext_fallback = True
    wizard.var_status = _Var("")
    wizard.var_progress = _Var("")
    wizard.var_f_key = _Var("")
    wizard.var_f_regex = _Var("")
    wizard.var_f_mode = _Var("none")
    wizard.var_f_search_label = _Var("Gesamten Text durchsuchen")
    wizard.var_f_after = _Var("")
    wizard.var_f_line = _Var("")
    wizard.var_match = _Var("")
    wizard.var_key = _Var("(9000)")
    wizard.var_name = _Var("Neu")
    wizard.var_pdf = _Var("sample.pdf")
    wizard.var_reference_pdf = _Var("")
    wizard.var_finish_action = _Var("activate")
    wizard.var_custom_count = _Var("")
    wizard.draft_path = "draft.json"
    wizard.assay_text = "FULL"
    wizard._normalized_pdf_text = "FULL"
    wizard._pdf_fingerprint = "sample.pdf"
    wizard._fields = [{"key": "lot", "regex": "Lot", "search_from": None}]
    wizard._field_idx = 0
    wizard._step = 0
    wizard._busy = False
    wizard.lbl_title = _Config()
    wizard.btn_back = _Config()
    wizard.btn_next = _Config()
    wizard._card_frames = {"fields": _Card(), "custom": _Card(), "finish": _Card()}
    wizard.list_summary = _SummaryList()
    wizard.lbl_mode_summary = _Config()
    wizard.frm_reference = type("Frame", (), {"pack_forget": lambda self: None})()
    wizard.lbl_required_summary = _Config()
    wizard._clear_highlight = lambda: None
    wizard._highlight_span = lambda *_args: None
    wizard._clear_field_form = lambda: None
    wizard._reload_fields = lambda: None
    wizard._all_fields_confirmed = lambda: True

    wizard._show_step(1)
    wizard._show_current_field()
    assert _FULLTEXT_FALLBACK_WARNING in wizard.var_status.get()
    wizard._show_step(3)
    assert _FULLTEXT_FALLBACK_WARNING in wizard.var_status.get()
    assert any(_FULLTEXT_FALLBACK_WARNING in row for row in wizard.list_summary.rows)
    monkeypatch.setattr(
        "rule_editor.wizard.messagebox.showerror",
        lambda _title, message, **_kwargs: errors.append(str(message)),
    )
    wizard._finish()
    assert errors
    assert "Blocktrennung" in errors[0]
    assert "Kein erfolgreicher Abschluss" in wizard.var_status.get()
    assert "erfolgreich" not in wizard.var_status.get().lower() or "kein erfolgreicher" in wizard.var_status.get().lower()


def test_new_mode_blocks_active_key_before_draft_creation() -> None:
    created: list[str] = []

    class _Item:
        kind = "active"
        assay_key = "(1111)"

    class _Rules:
        def list_inventory(self, kind: str = "all") -> list[object]:
            assert kind == "active"
            return [_Item()]

        def create_draft_from_template_if_missing(self, key: str, name: str) -> dict:
            created.append(key)
            return {"status": "created", "draft_path": "new.json", "assay_key": key, "assay_name": name}

    wizard = _target_wizard(_Rules())
    wizard.var_mode.set("new")
    wizard.var_pdf.set("sample.pdf")
    wizard._normalized_pdf_text = "FULL"
    wizard._pdf_fingerprint = "sample.pdf"
    wizard.var_key.set("(1111)")
    wizard.var_name.set("Aktiv")
    assert wizard._commit_target() is False
    assert created == []
    assert wizard.draft_path is None
    assert "Assay-Verwaltung" in wizard.var_status.get()
    assert "Vorhandenen Entwurf" in wizard.var_status.get()


def test_cancel_shutdown_reloads_same_draft_without_callbacks() -> None:
    from rule_editor.manage_actions import ManageMixin
    from rule_editor.wizard import NewRulesetWizard

    reloaded: list[str] = []
    opened: list[str] = []
    activated: list[str] = []
    proofs: list[str] = []
    same = r"I:\rules\drafts\same.draft.json"

    host = ManageMixin.__new__(ManageMixin)
    host.current_draft_path = same
    host.on_load_draft_into_editor = lambda path: reloaded.append(path) or True

    wizard = NewRulesetWizard.__new__(NewRulesetWizard)
    wizard._closed = False
    wizard._pdf_request_id = 4
    wizard.draft_path = same
    wizard.destroy = lambda: None
    wizard._on_session_closed = host._sync_editor_after_wizard
    wizard._on_open_in_editor = opened.append
    wizard._on_activate_requested = activated.append
    wizard._rules = type("Rules", (), {"create_authoring_proof": staticmethod(lambda *_a, **_k: proofs.append("proof"))})()

    wizard._shutdown(None)

    assert reloaded == [same]
    assert opened == []
    assert activated == []
    assert proofs == []
