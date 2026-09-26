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
    "Neue Regel aus PDF …",
    "Aktion für Auswahl",
    "Weitere Aktionen …",
    "Aktualisieren",
    "Entwurf speichern",
    "Extraktion mit PDF testen",
    "Entwurf aktivieren",
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
    "tree_marking_legend",
    "lbl_loaded_assay_key",
    "lbl_loaded_assay_name",
    "frame_marking_panel",
    "ent_field_regex",
    "ent_marking_regex",
    "workspace_panes",
)


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
        assert buttons.count("Arbeitsordner wählen …") == 1
        assert "Regel aus PDF erstellen oder prüfen …" in buttons
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
    assert "minsize=" not in workspace_source


def test_phase6_select_tab_routes_without_notebook() -> None:
    from rule_editor_main import RuleEditorWindow

    calls: list[tuple[str, str | None]] = []
    host = type("Host", (), {})()
    host._show_page = lambda page: calls.append(("page", page))
    host._show_advanced = lambda section=None: calls.append(("advanced", section))
    host._hide_advanced = lambda: calls.append(("hide", None))
    host._set_active_step_button = lambda key: calls.append(("active", key))

    RuleEditorWindow._select_tab(host, "draft")
    RuleEditorWindow._select_tab(host, "pdf")
    RuleEditorWindow._select_tab(host, "meta")

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
        assert editor.tree_rulesets.cget("yscrollcommand")
        assert editor.ent_field_regex is editor.ent_marking_regex
        assert editor.txt_marking_regex_preview is None

        panes = editor.workspace_panes
        children = list(panes.panes())
        assert len(children) == 3
        assert str(panes.cget("orient")) == "horizontal"
        assert [int(panes.pane(child, "weight")) for child in children] == [1, 3, 2]
        assert editor.frame_advanced.winfo_manager() == ""
        assert panes.winfo_manager() == "grid"

        pane_names = set(children)
        left = _pane_of(editor.tree_fields, pane_names)
        middle = _pane_of(editor.txt_block, pane_names)
        right = _pane_of(editor.ent_field_regex, pane_names)
        assert left is not None and middle is not None and right is not None
        assert len({left, middle, right}) == 3

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
        assert editor.frame_marking_panel.winfo_manager() == ""
        assert str(editor.btn_toggle_markings.cget("text")) == "Markierungen einblenden"
        editor._toggle_marking_panel()
        assert editor.frame_marking_panel.winfo_manager() == "grid"

        editor._toggle_advanced()
        assert editor._advanced_visible is True
        assert editor.frame_advanced.winfo_manager() == "grid"
        assert editor.workspace_panes.winfo_manager() == ""
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
    assert "weight=1" in workspace and "weight=3" in workspace and "weight=2" in workspace
    assert 'state="readonly"' in toolbar
    assert 'command=""' in fields
    assert "Regex-Bibliothek …" in settings
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
