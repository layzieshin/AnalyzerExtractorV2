from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Sequence
from tkinter import ttk

from interfaces.tk.view_models import (
    iter_report_occurrences,
    occurrence_field_rows,
    occurrence_list_rows,
    report_detail_header_lines,
    report_summary_row_values,
    validation_history_rows,
    validation_status_line,
)
from interfaces.tk.widgets.common import Card, EmptyState, SectionHeader, create_scrollable_tree
from src.application.api import ReportDetail, ReportRunOccurrence, ReportSummaryItem


class ResultsView(ttk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        *,
        on_refresh: Callable[[], None],
        on_open_selected: Callable[[], None],
        on_open_pdf: Callable[[], None],
        on_open_output_folder: Callable[[], None],
        on_back: Callable[[], None],
        on_occurrence_selected: Callable[[str], None],
        on_save_validation: Callable[[], None] | None = None,
        on_correct_validation: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(master, style="Content.TFrame")
        self._on_refresh = on_refresh
        self._on_open_selected = on_open_selected
        self._on_open_pdf = on_open_pdf
        self._on_open_output_folder = on_open_output_folder
        self._on_back = on_back
        self._on_occurrence_selected = on_occurrence_selected
        self._on_save_validation = on_save_validation or (lambda: None)
        self._on_correct_validation = on_correct_validation or (lambda: None)
        self._detail_report_id: str = ""
        self._current_detail: ReportDetail | None = None
        self._occurrences: dict[str, ReportRunOccurrence] = {}
        self._default_operator_initials = ""
        self._initials_dirty = False
        self._suppress_initials = False
        self._build()

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self._list_panel = ttk.Frame(self, style="Content.TFrame")
        self._list_panel.grid(row=0, column=0, sticky="nsew")
        self._list_panel.columnconfigure(0, weight=1)
        self._list_panel.rowconfigure(0, weight=1)

        list_card = Card(self._list_panel)
        list_card.grid(row=0, column=0, sticky="nsew")
        lbody = list_card.body
        SectionHeader(lbody, "Ergebnisse", action_text="Aktualisieren", on_action=self._on_refresh).pack(
            fill="x", pady=(0, 8)
        )
        columns = ("file", "status", "assays", "time", "device")
        tree_frame, self._tree = create_scrollable_tree(
            lbody,
            columns,
            ("Bericht", "Status", "Assays", "Zeit", "Gerät"),
            height=12,
        )
        tree_frame.pack(fill="both", expand=True, pady=(0, 8))
        self._tree.bind("<Double-1>", lambda _e: self._on_open_selected())
        self._empty_list = EmptyState(lbody, "Keine Ergebnisse vorhanden.")
        actions = ttk.Frame(lbody, style="CardInner.TFrame")
        actions.pack(fill="x")
        ttk.Button(actions, text="Details anzeigen", command=self._on_open_selected).pack(side="left")
        ttk.Button(actions, text="Ausgabeordner öffnen", command=self._on_open_output_folder).pack(side="left", padx=(8, 0))

        self._detail_panel = ttk.Frame(self, style="Content.TFrame")
        detail_card = Card(self._detail_panel)
        detail_card.pack(fill="both", expand=True)
        dbody = detail_card.body
        header_row = ttk.Frame(dbody, style="CardInner.TFrame")
        header_row.pack(fill="x", pady=(0, 8))
        ttk.Button(header_row, text="Zurück", command=self._on_back).pack(side="left")
        ttk.Button(header_row, text="PDF öffnen", command=self._on_open_pdf).pack(side="left", padx=(8, 0))
        ttk.Button(header_row, text="Ausgabeordner öffnen", command=self._on_open_output_folder).pack(side="left", padx=(8, 0))
        ttk.Button(header_row, text="Aktualisieren", command=self._on_refresh).pack(side="left", padx=(8, 0))
        self._lbl_detail_title = ttk.Label(dbody, text="", style="SectionTitle.TLabel")
        self._lbl_detail_title.pack(anchor="w")
        self._lbl_detail_meta = ttk.Label(dbody, text="", style="Muted.TLabel", wraplength=700)
        self._lbl_detail_meta.pack(anchor="w", pady=(4, 8))

        occ_columns = ("assay", "lot", "device", "time")
        occ_frame, self._occ_tree = create_scrollable_tree(
            dbody,
            occ_columns,
            ("Assay", "Charge/Lot", "Gerät", "Zeit"),
            height=6,
        )
        occ_frame.pack(fill="both", expand=True, pady=(0, 8))
        self._occ_tree.bind("<<TreeviewSelect>>", self._handle_occurrence_select)

        ttk.Label(dbody, text="Felder der ausgewählten Messung", style="SectionTitle.TLabel").pack(anchor="w", pady=(0, 4))
        field_columns = ("field", "value")
        field_frame, self._field_tree = create_scrollable_tree(
            dbody,
            field_columns,
            ("Feld", "Wert"),
            height=8,
        )
        field_frame.pack(fill="both", expand=True, pady=(0, 8))

        panel = ttk.LabelFrame(dbody, text="Validierung", padding=8)
        panel.pack(fill="x")
        self._lbl_validation_status = ttk.Label(panel, text="Keine Messung ausgewählt.", wraplength=680)
        self._lbl_validation_status.pack(anchor="w")
        history_frame, self._validation_tree = create_scrollable_tree(
            panel,
            ("state", "initials", "time", "comment"),
            ("Stand", "Initialen", "Zeit", "Kommentar"),
            height=3,
        )
        history_frame.pack(fill="x", pady=(6, 6))
        form = ttk.Frame(panel)
        form.pack(fill="x")
        ttk.Label(form, text="Initialen").grid(row=0, column=0, sticky="w")
        self._var_initials = tk.StringVar()
        self._var_initials.trace_add("write", self._on_initials_edited)
        ttk.Entry(form, textvariable=self._var_initials, width=16).grid(row=0, column=1, sticky="w", padx=(8, 16))
        ttk.Label(form, text="Kommentar").grid(row=0, column=2, sticky="w")
        self._var_comment = tk.StringVar()
        ttk.Entry(form, textvariable=self._var_comment).grid(row=0, column=3, sticky="ew", padx=(8, 0))
        form.columnconfigure(3, weight=1)
        actions = ttk.Frame(panel)
        actions.pack(fill="x", pady=(8, 0))
        self._btn_save_validation = ttk.Button(
            actions,
            text="Validierung speichern",
            command=self._on_save_validation,
        )
        self._btn_save_validation.pack(side="left")
        self._btn_correct_validation = ttk.Button(
            actions,
            text="Validierung korrigieren",
            command=self._on_correct_validation,
        )
        self._btn_correct_validation.pack(side="left", padx=(8, 0))
        self._set_validation_actions(can_save=False, can_correct=False)

    def _on_initials_edited(self, *_args: object) -> None:
        if self._suppress_initials:
            return
        self._initials_dirty = True

    def _apply_default_initials_if_clean(self) -> None:
        if self._initials_dirty:
            return
        self._suppress_initials = True
        try:
            self._var_initials.set(self._default_operator_initials)
        finally:
            self._suppress_initials = False

    def set_default_operator_initials(self, initials: str) -> None:
        self._default_operator_initials = str(initials or "").strip()
        self._apply_default_initials_if_clean()

    def validation_run_id(self) -> int | None:
        selection = self._occ_tree.selection()
        if not selection:
            return None
        occurrence = self._occurrences.get(str(selection[0]))
        if occurrence is None or occurrence.run_id is None:
            return None
        return int(occurrence.run_id)

    def validation_initials(self) -> str:
        return self._var_initials.get()

    def validation_comment(self) -> str:
        return self._var_comment.get()

    def clear_validation_comment(self) -> None:
        self._var_comment.set("")

    def _set_validation_actions(self, *, can_save: bool, can_correct: bool) -> None:
        self._btn_save_validation.configure(state="normal" if can_save else "disabled")
        self._btn_correct_validation.configure(state="normal" if can_correct else "disabled")

    def _render_validation(self, occurrence: ReportRunOccurrence | None) -> None:
        self._lbl_validation_status.configure(text=validation_status_line(occurrence))
        for row in self._validation_tree.get_children():
            self._validation_tree.delete(row)
        for values in validation_history_rows(occurrence):
            self._validation_tree.insert("", "end", values=values)
        if occurrence is None or occurrence.run_id is None or occurrence.validation_ambiguous:
            self._set_validation_actions(can_save=False, can_correct=False)
            return
        has_current = occurrence.current_validation is not None
        self._set_validation_actions(can_save=not has_current, can_correct=has_current)

    def _handle_occurrence_select(self, _event: object) -> None:
        selection = self._occ_tree.selection()
        if not selection or self._current_detail is None:
            return
        occurrence_id = str(selection[0])
        self.render_occurrence_fields(self._current_detail, occurrence_id)
        self._on_occurrence_selected(occurrence_id)

    def show_list(self) -> None:
        self._detail_panel.grid_remove()
        self._list_panel.grid(row=0, column=0, sticky="nsew")

    def show_detail(self) -> None:
        self._list_panel.grid_remove()
        self._detail_panel.grid(row=0, column=0, sticky="nsew")

    def selected_report_id(self) -> str:
        selection = self._tree.selection()
        if not selection:
            return ""
        return str(selection[0])

    def current_detail_report_id(self) -> str:
        return self._detail_report_id

    def render_report_list(self, items: Sequence[ReportSummaryItem]) -> None:
        previous_selection = self.selected_report_id()
        for row in self._tree.get_children():
            self._tree.delete(row)
        if not items:
            self._empty_list.pack(anchor="w", pady=(8, 0))
            return
        self._empty_list.pack_forget()
        for item in items:
            values = report_summary_row_values(item)
            self._tree.insert("", "end", iid=item.report_id, values=values)
        if previous_selection and self._tree.exists(previous_selection):
            self._tree.selection_set(previous_selection)
            self._tree.focus(previous_selection)

    def render_report_detail(self, detail: ReportDetail) -> None:
        self._detail_report_id = detail.report_id
        self._current_detail = detail
        title, time_text, device_text, status = report_detail_header_lines(detail)
        self._lbl_detail_title.configure(text=title)
        processing = detail.display_status or "-"
        self._lbl_detail_meta.configure(
            text=f"{time_text} | Gerät: {device_text} | Status: {status} | Verarbeitung: {processing}"
        )
        previous = ""
        current_selection = self._occ_tree.selection()
        if current_selection:
            previous = str(current_selection[0])
        for row in self._occ_tree.get_children():
            self._occ_tree.delete(row)
        for row in self._field_tree.get_children():
            self._field_tree.delete(row)
        self._occurrences = {
            occ_id: occurrence for occ_id, _group, occurrence in iter_report_occurrences(detail)
        }
        rows = occurrence_list_rows(detail)
        for occ_id, assay, lot, device, created_at in rows:
            self._occ_tree.insert("", "end", iid=occ_id, values=(assay, lot, device, created_at))
        self._apply_default_initials_if_clean()
        target = previous if previous and self._occ_tree.exists(previous) else (rows[0][0] if rows else "")
        if target:
            self._occ_tree.selection_set(target)
            self._occ_tree.focus(target)
            self.render_occurrence_fields(detail, target)
        else:
            self._render_validation(None)

    def render_occurrence_fields(self, detail: ReportDetail, occurrence_id: str) -> None:
        for row in self._field_tree.get_children():
            self._field_tree.delete(row)
        for field_key, value in occurrence_field_rows(detail, occurrence_id):
            self._field_tree.insert("", "end", values=(field_key, value if value != "" else "(leer)"))
        self._render_validation(self._occurrences.get(occurrence_id))
