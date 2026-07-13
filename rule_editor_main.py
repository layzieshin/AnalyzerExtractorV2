"""Einstiegspunkt des Visual Rule Editors.

RuleEditorWindow haelt den gesamten Zustand (StringVars, Daten, Widget-Refs)
zentral im __init__; die Funktionalitaet kommt aus thematischen Mixins im
Paket rule_editor/ (UI-Aufbau, Draft-, Feld-, Meta-, PDF-, Markierungs-,
Regex-, History-, Release-Aktionen und Guide).
"""
from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import ttk

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
    def __init__(self) -> None:
        super().__init__()
        self.title("AnalyzerResultExtractorV2 - Visual Rule Editor")
        self.geometry("1520x940")

        self.project_root = Path(__file__).resolve().parent
        self.current_draft_path: str | None = None
        self.assay_block_text: str = ""

        self.fields_data: list[dict] = []
        self.column_mapping_data: dict[str, str] = {}

        self.var_root = tk.StringVar(value=str(self.project_root))
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
        self.var_search_mode = tk.StringVar(value="none")
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
        self.var_inventory_filter = tk.StringVar(value="Alle")
        self._inventory_by_iid: dict[str, dict[str, object]] = {}
        self.var_field_guidance = tk.StringVar(value="")

        self._build_ui()
        self._bind_shortcuts()
        self._reload_assays()
        self._refresh_ruleset_overview()
        self._install_dirty_watchers()
        self._schedule_autosave()

    def _select_tab(self, tab_key: str) -> None:
        tab = self._tab_frames.get(tab_key)
        if tab is None:
            return
        self.notebook.select(tab)

    def _on_tab_changed(self, _event: tk.Event | None) -> None:
        active_tab = self.notebook.nametowidget(self.notebook.select())
        active_key = ""
        for key, frame in self._tab_frames.items():
            if frame == active_tab:
                active_key = key
                break
        self._set_active_step_button(active_key)

    def _set_active_step_button(self, active_key: str) -> None:
        for key, btn in self._step_nav_buttons:
            if key == active_key:
                btn.config(relief=tk.SUNKEN)
            else:
                btn.config(relief=tk.RAISED)

    def _bind_shortcuts(self) -> None:
        self.bind("<Return>", self._on_enter)
        self.bind("<Escape>", lambda _event: self._reset_field_form())
        self.bind("<Control-z>", lambda _event: self.on_undo())
        self.bind("<Control-y>", lambda _event: self.on_redo())

    def _on_enter(self, _event: tk.Event) -> None:
        widget_name = str(self.focus_get())
        if "field_regex" in widget_name or "field_key" in widget_name:
            self.on_apply_field()
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
