"""Einstiegspunkt des Visual Rule Editors.

RuleEditorWindow haelt den gesamten Zustand (StringVars, Daten, Widget-Refs)
und genau einen RuleSuiteController zentral im __init__. Die Oberflaeche
besteht aus Inventar und Arbeitsbereich; die Funktionalitaet kommt aus
thematischen Mixins im Paket rule_editor/.
"""
from __future__ import annotations

from pathlib import Path
import sys
import tkinter as tk
from tkinter import ttk

from interfaces.tk.desktop_theme import configure_desktop_theme
from src.application.api import RuleSuiteController
from src.runtime.api import resolve_app_root

from rule_editor.draft_actions import DraftMixin
from rule_editor.field_actions import FieldsMixin
from rule_editor.guide import GuideMixin
from rule_editor.history_actions import HistoryMixin
from rule_editor.manage_actions import ManageMixin
from rule_editor.marking_actions import MarkingsMixin
from rule_editor.meta_actions import MetaMixin
from rule_editor.pdf_text_actions import PdfTextMixin
from rule_editor.regex_actions import RegexMixin
from rule_editor.release_actions import ReleaseMixin
from rule_editor.ui_builder import UiBuilderMixin


class RuleEditorWindow(
    UiBuilderMixin,
    GuideMixin,
    HistoryMixin,
    DraftMixin,
    FieldsMixin,
    MetaMixin,
    PdfTextMixin,
    MarkingsMixin,
    RegexMixin,
    ReleaseMixin,
    ManageMixin,
    tk.Tk,
):
    def __init__(self, project_root: str | Path | None = None) -> None:
        super().__init__()
        self.title("Analyzer Result Extractor – Regelverwaltung")
        self.minsize(1024, 768)
        self.geometry("1440x900")
        self._maximize_on_windows()

        self.project_root = Path(project_root) if project_root is not None else resolve_app_root(Path(__file__))
        self._rules = RuleSuiteController(self.project_root)
        self.current_draft_path: str | None = None
        self.assay_block_text: str = ""

        self.fields_data: list[dict] = []
        self.column_mapping_data: dict[str, str] = {}

        self.var_root = tk.StringVar(value=str(self.project_root))
        self.var_root.trace_add("write", self._on_var_root_written)
        self.var_assay = tk.StringVar(value="")
        self.var_new_assay_key = tk.StringVar(value="")
        self.var_new_assay_name = tk.StringVar(value="")
        self.var_draft_path = tk.StringVar(value="")
        self.var_pdf = tk.StringVar(value="")
        self.var_lot_regex = tk.StringVar(value="")
        self.var_dedupe_fields = tk.StringVar(value="")
        self.var_excel_filename = tk.StringVar(value="{assay_name}.xlsx")
        self.var_sheet_template = tk.StringVar(value="{lot_id}")

        self.var_field_key = tk.StringVar(value="")
        self.var_field_regex = tk.StringVar(value="")
        self.var_field_required = tk.BooleanVar(value=False)
        self.var_field_excel_column = tk.StringVar(value="")
        self.var_field_dedupe = tk.BooleanVar(value=False)
        self.var_search_mode = tk.StringVar(value="none")
        self.var_search_mode_label = tk.StringVar(value="Gesamter Assay-Text")
        self.var_search_after = tk.StringVar(value="")
        self.var_search_line = tk.StringVar(value="")
        self.var_regex_group = tk.StringVar(value="1")

        self.var_col_key = tk.StringVar(value="")
        self.var_col_name = tk.StringVar(value="")

        self.var_hint = tk.StringVar(value="Bereit")

        self.assay_display_to_key: dict[str, str] = {}
        self.known_assay_keys: set[str] = set()
        self._busy = False
        self._suspend_dirty_tracking = False
        self._dirty = False
        self._selected_field_key: str | None = None
        self._field_form_dirty = False
        self._field_form_loading = False
        self._field_form_is_new = False
        self._field_form_return_key: str | None = None
        self._suppress_field_select = False
        self._field_selection_guard = False
        self._field_mutation_guard = False
        self._dialog_guard = False
        self._search_mode_applying = False
        self._undo_stack: list[dict] = []
        self._redo_stack: list[dict] = []
        self.var_autosave = tk.BooleanVar(value=True)
        self.var_last_autosave = tk.StringVar(value="-")
        self._autosave_ms = 45000
        self._guide_window: tk.Toplevel | None = None
        self._guide_idx = 0
        self._guide_title_var: tk.StringVar | None = None
        self._guide_text_widget: tk.Text | None = None
        self.txt_field_preview: tk.Text | None = None
        self.tree_regex_results: ttk.Treeview | None = None
        self._regex_result_data: dict[str, dict[str, object]] = {}
        self._regex_result_counter = 0
        self._marking_panel_visible = True
        self._marking_sync_guard = False
        self._field_marking_data: dict[str, dict[str, object]] = {}
        self._field_marking_tags: set[str] = set()
        self._active_marking_key: str | None = None
        self.frame_marking_panel: tk.Frame | None = None
        self.tree_marking_legend: ttk.Treeview | None = None
        self.var_marking_status = tk.StringVar(value="Kein Assay-Text geladen.")
        self.btn_toggle_markings: tk.Button | None = None
        self.var_marking_selection = tk.StringVar(value="(keine Auswahl)")
        self.tree_rulesets: ttk.Treeview | None = None
        self.inventory_filter_vars = {
            "active": tk.BooleanVar(value=True),
            "draft": tk.BooleanVar(value=True),
            "inactive": tk.BooleanVar(value=True),
            "history": tk.BooleanVar(value=True),
            "trash": tk.BooleanVar(value=True),
        }
        self._inventory_by_iid: dict[str, dict[str, object]] = {}
        self.var_field_guidance = tk.StringVar(value="")

        configure_desktop_theme(self)
        self._build_ui()
        self._bind_shortcuts()
        self._reload_assays()
        self._refresh_ruleset_overview()
        self._install_dirty_watchers()
        self._schedule_autosave()

    def _maximize_on_windows(self) -> None:
        if sys.platform != "win32":
            return
        try:
            self.state("zoomed")
        except tk.TclError:
            self.geometry("1440x900")

    def _on_var_root_written(self, *_args: object) -> None:
        text = self.var_root.get().strip()
        if not text:
            return
        self._bind_rules_controller(text)

    def _bind_rules_controller(self, root: str | Path) -> None:
        chosen = Path(root)
        resolved = chosen.resolve()
        current = getattr(self, "_rules", None)
        if current is not None and Path(current.project_root) == resolved:
            return
        self.project_root = chosen
        self._rules = RuleSuiteController(chosen)

    def _select_tab(self, tab_key: str) -> None:
        if tab_key == "draft":
            self._show_page("inventory")
        elif tab_key in {"meta", "validate", "log"}:
            self._show_advanced(tab_key)
        else:
            self._show_page("workspace")
            self._hide_advanced()
        self._set_active_step_button(tab_key)

    def _set_active_step_button(self, active_key: str) -> None:
        for key, btn in self._step_nav_buttons:
            if key == active_key:
                btn.config(relief=tk.SUNKEN)
            else:
                btn.config(relief=tk.RAISED)

    def _bind_shortcuts(self) -> None:
        self.bind("<Return>", self._on_enter)
        self.bind("<Escape>", lambda _event: self.on_cancel_field_edit())
        self.protocol("WM_DELETE_WINDOW", self._on_editor_close)
        self.bind("<Control-z>", lambda _event: self.on_undo())
        self.bind("<Control-y>", lambda _event: self.on_redo())

    def _on_enter(self, _event: tk.Event) -> None:
        widget_name = str(self.focus_get())
        field_names = (
            "field_regex",
            "field_key",
            "field_excel",
            "field_search_mode",
            "field_search_after",
            "field_search_line",
        )
        if any(name in widget_name for name in field_names):
            self.on_commit_field_form()
            return
        self.on_test_regex()

    def _set_status(self, text: str) -> None:
        self.lbl_status.config(text=text)

    def _set_hint(self, text: str) -> None:
        self.var_hint.set(text)

    def _log(self, text: str) -> None:
        self.txt_log.insert(tk.END, text + "\n")
        self.txt_log.see(tk.END)

    def _set_busy(self, busy: bool, status: str) -> None:
        self._busy = busy
        self._set_status(status)


if __name__ == "__main__":
    RuleEditorWindow().mainloop()
