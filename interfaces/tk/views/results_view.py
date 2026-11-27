from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from collections.abc import Callable, Sequence
from tkinter import ttk

from interfaces.tk.view_models import (
    format_timestamp,
    filter_report_summaries,
    iter_report_occurrences,
    occurrence_field_rows,
    occurrence_list_rows,
    report_detail_header_lines,
    report_summary_row_values,
    validation_history_rows,
    validation_status_line,
)
from interfaces.tk.scroll_helpers import bind_mousewheel
from interfaces.tk.widgets.common import Card, EmptyState, MultiSelectFilter, ScrollableFrame, StatusBadge, create_scrollable_tree
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
        on_open_validation: Callable[[], None] | None = None,
        on_monthly_archive: Callable[[], None] | None = None,
        on_find_pdf: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(master, style="Content.TFrame")
        self._on_refresh = on_refresh
        self._on_open_selected = on_open_selected
        self._on_open_pdf = on_open_pdf
        self._on_open_output_folder = on_open_output_folder
        self._on_back = on_back
        self._on_occurrence_selected = on_occurrence_selected
        self._on_open_validation = on_open_validation or (lambda: None)
        self._on_monthly_archive = on_monthly_archive or (lambda: None)
        self._on_find_pdf = on_find_pdf or (lambda: None)
        self._detail_report_id: str = ""
        self._current_detail: ReportDetail | None = None
        self._occurrences: dict[str, ReportRunOccurrence] = {}
        self._reports: tuple[ReportSummaryItem, ...] = ()
        self._report_store_path = ""
        self._layout_after_id = None
        self._read_compact = None
        self._header_compact = None
        self._configure_styles()
        self._build()

    def _configure_styles(self) -> None:
        style = ttk.Style(self)
        style.configure("Results.TButton", font=("Segoe UI", 9), padding=(8, 5), background="#ffffff",
            foreground="#21486f", bordercolor="#cbdbea", lightcolor="#ffffff", darkcolor="#ffffff",
            borderwidth=1, relief="solid", focuscolor="#175ba4")
        style.map("Results.TButton", background=[("active", "#eef5fd")],
            foreground=[("disabled", "#8b9bad")], bordercolor=[("focus", "#8bb2df")])
        style.configure("Ghost.Results.TButton", bordercolor="#ffffff")
        style.configure("Results.Primary.TButton", font=("Segoe UI", 9, "bold"), padding=(10, 5), focuscolor="#ffffff")
        style.configure("Results.TMenubutton", font=("Segoe UI", 9), padding=(8, 5), background="#ffffff",
            foreground="#21486f", bordercolor="#cbdbea", lightcolor="#ffffff", darkcolor="#ffffff")
        style.configure("Results.Filter.TEntry", padding=(8, 6), fieldbackground="#ffffff", bordercolor="#cbdbea",
            lightcolor="#ffffff", darkcolor="#ffffff", borderwidth=1)
        style.configure("Results.Muted.TLabel", font=("Segoe UI", 9), background="#ffffff", foreground="#53677a")
        style.configure("Results.DetailTitle.TLabel", font=("Segoe UI", 16, "bold"), background="#ffffff", foreground="#16293c")
        style.configure("Results.Treeview", rowheight=42, font=("Segoe UI", 9), bordercolor="#dbe4ed")
        style.configure("Results.Treeview.Heading", font=("Segoe UI", 9, "bold"), background="#f0f5fb", padding=(8, 6))
        style.map("Results.Treeview", background=[("selected", "#eaf3fd")], foreground=[("selected", "#175ba4")])
        style.configure("Results.Values.Treeview", rowheight=30, font=("Segoe UI", 9))
        style.configure("Results.Values.Treeview.Heading", font=("Segoe UI", 9, "bold"), padding=(8, 4), background="#f0f5fb")

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        header = ttk.Frame(self, style="Content.TFrame", padding=(12, 12, 12, 10))
        self._page_header = header
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        self._page_eyebrow = ttk.Label(header, text="RECHERCHE", style="Eyebrow.TLabel")
        self._page_eyebrow.grid(row=0, column=0, sticky="w")
        self._page_title = ttk.Label(header, text="Ergebnisse", style="PageTitle.TLabel")
        self._page_title.grid(row=1, column=0, sticky="w", pady=(4, 2))
        subtitle = ttk.Label(header, text="Berichte, Messwerte und Validierungshistorie nachschlagen.", style="PageSubtitle.TLabel", wraplength=700)
        subtitle.grid(row=2, column=0, sticky="w")
        header_actions = ttk.Frame(header, style="Content.TFrame")
        header_actions.grid(row=1, column=1, sticky="e", padx=(10, 0))
        self._btn_monthly_archive = ttk.Button(header_actions, text="Eingang aufräumen", command=self._on_monthly_archive, style="Results.TButton")
        self._btn_monthly_archive.pack(side="left", padx=(0, 8))
        ttk.Button(header_actions, text="Aktualisieren", command=self._on_refresh, style="Results.TButton").pack(side="left")
        header.bind("<Configure>", lambda event: subtitle.configure(wraplength=max(200, event.width - 140)))

        self._list_panel = ttk.Frame(self, style="Content.TFrame")
        self._list_panel.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self._list_panel.columnconfigure(0, weight=1)
        self._list_panel.rowconfigure(1, weight=1)

        list_card = Card(self._list_panel, padding=16, rounded=True)
        self._list_card = list_card
        list_card.grid(row=0, column=0, sticky="new")
        lbody = list_card.body
        filters = ttk.Frame(lbody, style="CardInner.TFrame")
        self._filterbar = filters
        filters.columnconfigure(1, weight=1)
        filters.pack(fill="x", pady=(0, 12))
        self._filter_group = ttk.Frame(filters, style="CardInner.TFrame")
        self._filters = {key: MultiSelectFilter(self._filter_group, title, on_change=self._apply_filters)
                         for key, title in (("status", "Status"), ("assay", "Assay"), ("device", "Gerät"))}
        for widget in self._filters.values():
            widget.configure(style="Results.TMenubutton")
        self._btn_reset_filters = ttk.Button(self._filter_group, text="Filter löschen", command=self._reset_filters, style="Ghost.Results.TButton")
        self._btn_more_filters = ttk.Button(self._filter_group, text="Weitere Filter", command=self._toggle_advanced_filters, style="Results.TButton")
        query = ttk.Frame(filters, style="CardInner.TFrame")
        self._search_group = query
        query.columnconfigure(1, weight=1)
        ttk.Label(query, text="Suche", style="Results.Muted.TLabel").grid(row=0, column=0, sticky="nsw", padx=(0, 8))
        self._var_search = tk.StringVar()
        entry = ttk.Entry(query, textvariable=self._var_search, width=1, font=("Segoe UI", 9), style="Results.Filter.TEntry")
        self._search_entry = entry
        entry.grid(row=0, column=1, sticky="nsew", padx=(0, 8))
        entry.bind("<Return>", lambda _event: self._apply_filters())
        self._search_button = ttk.Button(query, text="Suchen", command=self._apply_filters, style="Results.TButton", width=0)
        self._search_button.grid(row=0, column=2, sticky="nsew")
        self._advanced_filters = ttk.Frame(lbody, style="CardInner.TFrame")
        self._var_lot, self._var_date_from, self._var_date_to = tk.StringVar(), tk.StringVar(), tk.StringVar()
        for column, (title, variable) in enumerate((("Charge", self._var_lot), ("Von (JJJJ-MM-TT)", self._var_date_from), ("Bis (JJJJ-MM-TT)", self._var_date_to))):
            field = ttk.Frame(self._advanced_filters, style="CardInner.TFrame")
            field.grid(row=0, column=column, sticky="ew", padx=(0, 10))
            self._advanced_filters.columnconfigure(column, weight=1)
            ttk.Label(field, text=title, style="Results.Muted.TLabel").pack(anchor="w")
            ttk.Entry(field, textvariable=variable, width=14, font=("Segoe UI", 9), style="Results.Filter.TEntry").pack(fill="x", pady=(3, 0))
        ttk.Button(self._advanced_filters, text="Anwenden", command=self._apply_filters, style="Results.TButton").grid(row=0, column=3, sticky="s")
        self._lbl_filter_status = ttk.Label(lbody, text="Filter der geladenen Berichte", style="Results.Muted.TLabel")
        self._lbl_filter_status.pack(fill="x", pady=(0, 8))
        columns = ("file", "status", "assays", "time", "device", "lot")
        tree_frame, self._tree = create_scrollable_tree(
            lbody,
            columns,
            ("Bericht", "Status", "Assay", "Datum / Zeit", "Gerät", "Charge"),
            height=4, autohide=True,
        )
        self._tree.configure(style="Results.Treeview", displaycolumns=("file", "assays", "device", "lot", "time", "status"))
        tree_frame.pack(fill="both", expand=True, pady=(0, 8))
        self._tree.column("assays", width=260, minwidth=200, stretch=True)
        self._tree.bind("<Double-1>", lambda _e: self._on_open_selected())
        self._empty_list = EmptyState(lbody, "Keine Ergebnisse vorhanden.")
        actions = ttk.Frame(lbody, style="CardInner.TFrame")
        self._list_actions = actions
        actions.pack(fill="x")
        self._btn_open_selected = ttk.Button(actions, text="Details anzeigen", command=self._on_open_selected, state="disabled", style="Results.Primary.TButton")
        self._btn_open_selected.pack(side="left")
        self._tree.bind("<<TreeviewSelect>>", lambda _event: self._btn_open_selected.configure(state="normal" if self.selected_report_id() else "disabled"))
        ttk.Button(actions, text="Ausgabeordner öffnen", command=self._on_open_output_folder, style="Ghost.Results.TButton").pack(side="left", padx=(8, 0))

        self._detail_panel = ttk.Frame(self, style="Content.TFrame")
        detail_card = Card(self._detail_panel, padding=16, rounded=True)
        self._detail_card = detail_card
        detail_card.pack(fill="both", expand=True)
        dbody = detail_card.body
        self._detail_context = ScrollableFrame(dbody, autohide=True)
        self._detail_context.pack(fill="x")
        self._detail_context.pack_propagate(False)
        self._detail_context._canvas.configure(takefocus=True)
        context_body = self._detail_context.body
        header_row = ttk.Frame(context_body, style="CardInner.TFrame")
        header_row.pack(fill="x", pady=(0, 8))
        header_row.columnconfigure(0, weight=1)
        self._lbl_detail_title = ttk.Label(header_row, text="", style="Results.DetailTitle.TLabel")
        self._lbl_detail_title.grid(row=0, column=0, sticky="w")
        self._detail_status = StatusBadge(header_row, "")
        self._detail_status.grid(row=0, column=1, sticky="ne", padx=(12, 0))
        self._lbl_detail_meta = ttk.Label(context_body, text="", style="Results.Muted.TLabel", wraplength=700)
        self._lbl_detail_meta.pack(anchor="w", pady=(4, 8))
        self._detail_actions = ttk.Frame(context_body, style="CardInner.TFrame")
        self._detail_actions.pack(fill="x", pady=(0, 10))
        self._btn_open_validation = ttk.Button(self._detail_actions, text="Im Prüfplatz öffnen", style="Results.Primary.TButton",
                                              command=self._on_open_validation, state="disabled")
        self._btn_open_pdf = ttk.Button(self._detail_actions, text="Original-PDF öffnen", command=self._on_open_pdf, state="disabled", style="Results.TButton")
        self._detail_action_buttons = (
            self._btn_open_validation, self._btn_open_pdf,
            ttk.Button(self._detail_actions, text="PDF wiederfinden", command=self._on_find_pdf, style="Results.TButton"),
            ttk.Button(self._detail_actions, text="Ausgabeordner öffnen", command=self._on_open_output_folder, style="Ghost.Results.TButton"),
            ttk.Button(self._detail_actions, text="Detail schließen", command=self._on_back, style="Ghost.Results.TButton"),
            ttk.Button(self._detail_actions, text="Aktualisieren", command=self._on_refresh, style="Results.TButton"),
        )
        self._occ_label = ttk.Label(context_body, text="Messungen / Fassungen", style="Results.Muted.TLabel")
        self._occ_label.pack(anchor="w", pady=(0, 4))

        occ_columns = ("assay", "lot", "device", "time")
        occ_frame, self._occ_tree = create_scrollable_tree(
            context_body,
            occ_columns,
            ("Assay", "Charge/Lot", "Gerät", "Zeit"),
            height=1, autohide=True,
        )
        self._occ_tree.configure(style="Results.Values.Treeview")
        self._occ_frame = occ_frame
        occ_frame.pack(fill="x", pady=(0, 8))
        self._occ_tree.column("assay", width=260, minwidth=200, stretch=True)
        self._occ_tree.bind("<<TreeviewSelect>>", self._handle_occurrence_select)

        self._lbl_validation_status = ttk.Label(context_body, text="Keine Messung ausgewählt.", style="Results.Muted.TLabel", wraplength=680)
        self._lbl_validation_status.pack(anchor="w", pady=(0, 8))
        for widget in (self._detail_context._canvas, context_body, header_row, self._lbl_detail_title,
                       self._detail_status, self._lbl_detail_meta, self._lbl_validation_status):
            bind_mousewheel(widget, self._detail_context._canvas)
        self._read_body = ttk.Frame(dbody, style="CardInner.TFrame")
        self._read_body.pack(fill="both", expand=True)
        self._read_body.rowconfigure(0, weight=1)
        self._read_body.columnconfigure(0, weight=1)
        self._read_body.columnconfigure(1, weight=1)
        tabs = ttk.Notebook(self._read_body)
        self._read_tabs = tabs
        tabs.pack(fill="both", expand=True)
        values_panel, history_panel = ttk.Frame(self._read_body, style="CardInner.TFrame"), ttk.Frame(self._read_body, style="CardInner.TFrame")
        self._values_panel, self._history_panel = values_panel, history_panel
        tabs.add(values_panel, text="Werte (Lesen)")
        tabs.add(history_panel, text="Validierungsverlauf")
        self._values_heading = ttk.Label(values_panel, text="Werte", style="SectionTitle.TLabel")
        self._history_heading = ttk.Label(history_panel, text="Validierungsverlauf", style="SectionTitle.TLabel")
        field_columns = ("field", "value")
        field_frame, self._field_tree = create_scrollable_tree(
            values_panel,
            field_columns,
            ("Feld", "Extrahierter Wert"),
            height=6, autohide=True,
        )
        self._field_tree.configure(style="Results.Values.Treeview")
        field_frame.pack(fill="both", expand=True)
        history_frame, self._validation_tree = create_scrollable_tree(
            history_panel,
            ("state", "initials", "time", "comment"),
            ("Stand", "Initialen", "Zeit", "Kommentar"),
            height=5, autohide=True,
        )
        self._validation_tree.configure(style="Results.Values.Treeview")
        history_frame.pack(fill="both", expand=True)
        self._values_frame, self._history_frame = field_frame, history_frame
        self.bind("<Configure>", self._schedule_layout)
        self._filterbar.bind("<Configure>", self._schedule_layout)
        self._detail_actions.bind("<Configure>", self._schedule_layout)
        context_body.bind("<Configure>", self._schedule_layout, add="+")
        dbody.bind("<Configure>", self._schedule_layout)
        self._list_panel.bind("<Configure>", self._schedule_layout)
        for tree in (self._tree, self._field_tree, self._validation_tree, self._occ_tree):
            tree.bind("<Configure>", self._schedule_layout)
            for column in tree.cget("columns"):
                tree.heading(column, anchor="w")
        self.bind("<Destroy>", self._cancel_layout)
        self._schedule_layout()

    def _reset_filters(self) -> None:
        for widget in self._filters.values():
            widget.select_values(())
        for variable in (self._var_search, self._var_lot, self._var_date_from, self._var_date_to):
            variable.set("")
        self._apply_filters()

    def _schedule_layout(self, _event=None) -> None:
        if self._layout_after_id is None:
            self._layout_after_id = self.after_idle(self._layout_results)

    def _cancel_layout(self, event) -> None:
        if event.widget is self and self._layout_after_id is not None:
            self.after_cancel(self._layout_after_id)
            self._layout_after_id = None

    def _layout_results(self) -> None:
        self._layout_after_id = None
        width = self.winfo_width() - 56
        if width < 40:
            return
        compact = width < 900
        if compact != self._header_compact:
            self._page_header.configure(padding=(12, 4, 12, 6) if compact else (12, 12, 12, 10))
            self._page_title.configure(style="CompactPageTitle.TLabel" if compact else "PageTitle.TLabel")
            self._page_title.grid_configure(pady=(0, 2) if compact else (4, 2))
            if compact:
                self._page_eyebrow.grid_remove()
            else:
                self._page_eyebrow.grid()
            self._header_compact = compact
        controls = (*self._filters.values(), self._btn_reset_filters, self._btn_more_filters)
        required = sum(widget.winfo_reqwidth() + 6 for widget in controls)
        inline = width >= required + 310
        self._filter_group.grid(row=0, column=0, columnspan=1 if inline else 2, sticky="nw", padx=(0, 16) if inline else 0)
        search_height = max(self._search_entry.winfo_reqheight(), self._search_button.winfo_reqheight())
        self._search_group.rowconfigure(0, minsize=search_height)
        self._search_group.grid(row=0 if inline else 1, column=1 if inline else 0, columnspan=1 if inline else 2,
                               sticky="nsew", pady=0 if inline else (10, 0))
        for index, widget in enumerate(controls):
            widget.grid(row=0 if inline or index < 3 else 1, column=index if inline or index < 3 else index - 3,
                        sticky="nsew", padx=(0, 6), pady=(0, 6) if not inline and index < 3 else 0)
        font = tkfont.Font(self, font=ttk.Style(self).lookup("Results.Treeview", "font"))
        rows = [self._tree.item(row, "values") for row in self._tree.get_children()]
        desired = {}
        for column, index, minimum, maximum in (("file", 0, 210, 280), ("assays", 2, 180, 280), ("device", 4, 90, 140),
                                                ("lot", 5, 90, 150), ("time", 3, 150, 180), ("status", 1, 110, 200)):
            desired[column] = max(minimum, min(maximum, max((font.measure(str(row[index])) + 24 for row in rows), default=minimum)))
        available = max(1, self._tree.winfo_width() - 4)
        if available < 900:
            heading_font = tkfont.Font(self, font=ttk.Style(self).lookup("Results.Treeview.Heading", "font"))
            desired = {column: heading_font.measure(self._tree.heading(column, "text")) + 24 for column in desired}
            extra = max(0, available - sum(desired.values()))
            remaining = extra
            for column, share in (("file", .3), ("assays", .25), ("device", .08), ("lot", .1), ("time", .2)):
                growth = int(extra * share)
                desired[column] += growth
                remaining -= growth
            desired["status"] += remaining
        else:
            extra = max(0, available - sum(desired.values()))
            desired["file"] += extra // 2
            desired["assays"] += extra - extra // 2
        for column, value in desired.items():
            self._tree.column(column, width=value, minwidth=value, stretch=False)
        if self._list_panel.winfo_height() > 60:
            row_height = 42
            heading_height = max(24, self._tree.winfo_reqheight() - int(self._tree.cget("height")) * row_height)
            # Sum only the fixed controls: subtracting a changing card request
            # from a changing tree request can retain a stale, one-row estimate.
            fixed = 34 + self._filterbar.winfo_reqheight() + 12 + self._lbl_filter_status.winfo_reqheight() + 8
            fixed += self._list_actions.winfo_reqheight() + 8
            if self._advanced_filters.winfo_manager():
                fixed += self._advanced_filters.winfo_reqheight() + 8
            if self._empty_list.winfo_manager():
                fixed += self._empty_list.winfo_reqheight() + 8
            count = max(1, min(8, max(3, len(rows)), (self._list_panel.winfo_height() - fixed - heading_height) // row_height))
            if int(self._tree.cget("height")) != count:
                self._tree.configure(height=count)
        used = top = line_height = 0
        for button in self._detail_action_buttons:
            requested, height = button.winfo_reqwidth(), button.winfo_reqheight()
            if used and used + requested > width:
                top += line_height + 6
                used = line_height = 0
            button.place(x=used, y=top, width=min(requested, width), height=height)
            used += requested + 6
            line_height = max(line_height, height)
        self._detail_actions.configure(height=top + line_height)
        self._lbl_detail_title.configure(wraplength=max(180, width - 180))
        self._lbl_detail_meta.configure(wraplength=width)
        self._lbl_validation_status.configure(wraplength=width)
        self._layout_read_panels(compact)
        occurrence_count = len(self._occurrences)
        if compact and occurrence_count == 1:
            self._occ_label.pack_forget()
            self._occ_frame.pack_forget()
        elif not self._occ_frame.winfo_manager():
            self._occ_label.pack(anchor="w", pady=(0, 4), before=self._lbl_validation_status)
            self._occ_frame.pack(fill="x", pady=(0, 8), before=self._lbl_validation_status)
        self._occ_tree.configure(height=max(1, min(2 if compact else 4, occurrence_count)))
        context_height = self._detail_context.body.winfo_reqheight()
        if compact:
            # Keep the existing read tabs and at least one complete data row
            # visible; unusually long context remains reachable by its rail.
            context_height = min(context_height, max(1, self._detail_card.body.winfo_height() - 116))
        self._detail_context.configure(height=context_height)

    def _layout_read_panels(self, compact: bool) -> None:
        if compact != self._read_compact:
            if compact:
                for panel, title in ((self._values_panel, "Werte (Lesen)"), (self._history_panel, "Validierungsverlauf")):
                    panel.grid_remove()
                    if str(panel) not in self._read_tabs.tabs():
                        self._read_tabs.add(panel, text=title)
                self._values_heading.pack_forget()
                self._history_heading.pack_forget()
                self._read_tabs.pack(fill="both", expand=True)
            else:
                for panel in (self._values_panel, self._history_panel):
                    if str(panel) in self._read_tabs.tabs():
                        self._read_tabs.forget(panel)
                self._read_tabs.pack_forget()
                self._values_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
                self._history_panel.grid(row=0, column=1, sticky="nsew")
                self._values_heading.pack(anchor="w", pady=(0, 6), before=self._values_frame)
                self._history_heading.pack(anchor="w", pady=(0, 6), before=self._history_frame)
            self._read_compact = compact
        for tree in (self._field_tree, self._validation_tree, self._occ_tree):
            columns = tuple(tree.cget("columns"))
            available = max(1, tree.winfo_width() - 4)
            if tree is self._field_tree:
                widths = (max(100, int(available * .47)), max(120, available - max(100, int(available * .47))))
            elif tree is self._occ_tree:
                widths = (max(200, available - 340), 100, 100, 140)
            else:
                widths = (95, 75, 135, max(120, available - 305))
            for column, value in zip(columns, widths):
                flexible = column == ("assay" if tree is self._occ_tree else columns[-1])
                tree.column(column, width=value, minwidth=value, stretch=flexible)

    def validation_run_id(self) -> int | None:
        selection = self._occ_tree.selection()
        if not selection:
            return None
        occurrence = self._occurrences.get(str(selection[0]))
        if occurrence is None or occurrence.run_id is None:
            return None
        return int(occurrence.run_id)

    def validation_result_binding(self) -> tuple[str, str]:
        selection = self._occ_tree.selection()
        occurrence = self._occurrences.get(str(selection[0])) if selection else None
        if occurrence is None:
            return "", ""
        return occurrence.selection_token, occurrence.store_path

    def selected_validation_target(self) -> tuple[str, int, str, str] | None:
        run_id = self.validation_run_id()
        if run_id is None or not self._detail_report_id:
            return None
        token, store = self.validation_result_binding()
        return self._detail_report_id, run_id, store or (self._current_detail.store_path if self._current_detail else ""), token

    def _render_validation(self, occurrence: ReportRunOccurrence | None) -> None:
        self._lbl_validation_status.configure(text=validation_status_line(occurrence))
        for row in self._validation_tree.get_children():
            self._validation_tree.delete(row)
        for values in validation_history_rows(occurrence):
            self._validation_tree.insert("", "end", values=values)
        self._btn_open_validation.configure(state="normal" if occurrence is not None and occurrence.run_id is not None else "disabled")
        self._btn_open_validation.configure(text="Validierung korrigieren" if occurrence is not None and occurrence.current_validation is not None
                                            and not occurrence.validation_ambiguous and not occurrence.reanalysis_pending else "Im Prüfplatz öffnen")
        status = self._current_detail.report_status or self._current_detail.display_status if self._current_detail else ""
        lowered = status.casefold()
        kind = "error" if "fehl" in lowered else "warning" if any(word in lowered for word in ("teil", "offen", "nacharbeit")) else "success" if lowered == "validiert" else "neutral"
        self._detail_status.set_status(status, kind=kind)
        self._schedule_layout()

    def _handle_occurrence_select(self, _event: object) -> None:
        selection = self._occ_tree.selection()
        if not selection or self._current_detail is None:
            return
        occurrence_id = str(selection[0])
        self.render_occurrence_fields(self._current_detail, occurrence_id)
        self._on_occurrence_selected(occurrence_id)

    def show_list(self) -> None:
        self._detail_panel.grid_remove()
        self._list_panel.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self._schedule_layout()

    def show_detail(self) -> None:
        self._list_panel.grid_remove()
        self._detail_panel.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self._schedule_layout()

    def selected_report_id(self) -> str:
        selection = self._tree.selection()
        if not selection:
            return ""
        return str(selection[0])

    def current_detail_report_id(self) -> str:
        return self._detail_report_id

    def selected_report_descriptor(self) -> tuple[str, str]:
        return self.selected_report_id(), self._report_store_path

    def current_detail_descriptor(self) -> tuple[str, str]:
        detail = self._current_detail
        return (detail.report_id, detail.store_path) if detail is not None else ("", "")

    def invalidate_store_context(self) -> None:
        self._detail_report_id = ""
        self._current_detail = None
        self._occurrences.clear()
        for tree in (self._occ_tree, self._field_tree, self._validation_tree):
            tree.delete(*tree.get_children())
        self._lbl_detail_title.configure(text="")
        self._lbl_detail_meta.configure(text="")
        self._btn_open_pdf.configure(state="disabled")
        self._render_validation(None)
        self.render_report_list((), store_path="")
        self.show_list()

    def render_report_list(self, items: Sequence[ReportSummaryItem], *, store_path: str = "") -> None:
        self._report_store_path = store_path
        self._reports = tuple(items)
        self._filters["status"].set_options(tuple(item.report_status or item.display_status or "–" for item in items))
        self._filters["assay"].set_options(tuple(name for item in items for name in (item.assay_names or ("Assayname fehlt",))))
        self._filters["device"].set_options(tuple(device for item in items for device in (item.device_ids or ("–",))))
        self._apply_filters()

    def _toggle_advanced_filters(self) -> None:
        if self._advanced_filters.winfo_manager():
            self._advanced_filters.pack_forget()
        else:
            self._advanced_filters.pack(fill="x", pady=(0, 8), before=self._lbl_filter_status)
        self._schedule_layout()

    def _apply_filters(self) -> None:
        try:
            items = filter_report_summaries(self._reports, statuses=self._filters["status"].selected_values,
                assays=self._filters["assay"].selected_values, devices=self._filters["device"].selected_values,
                search=self._var_search.get(), lot=self._var_lot.get(), date_from=self._var_date_from.get(), date_to=self._var_date_to.get())
        except ValueError as exc:
            self._lbl_filter_status.configure(text=str(exc))
            return
        self._lbl_filter_status.configure(text=f"{len(items)} von {len(self._reports)} geladenen Berichten · Recherche ist schreibgeschützt")
        previous_selection = self.selected_report_id()
        for row in self._tree.get_children():
            self._tree.delete(row)
        self._btn_open_selected.configure(state="disabled")
        if not items:
            self._empty_list.pack(anchor="w", pady=(8, 0), before=self._list_actions)
            self._schedule_layout()
            return
        self._empty_list.pack_forget()
        for item in items:
            values = report_summary_row_values(item)
            self._tree.insert("", "end", iid=item.report_id, values=(*values, ", ".join(item.lot_ids) or "—"))
        if previous_selection and self._tree.exists(previous_selection):
            self._tree.selection_set(previous_selection)
            self._tree.focus(previous_selection)
            self._btn_open_selected.configure(state="normal")
        self._schedule_layout()

    def render_report_detail(self, detail: ReportDetail) -> None:
        self._detail_report_id = detail.report_id
        self._current_detail = detail
        self._btn_open_pdf.configure(state="normal" if detail.store_path else "disabled")
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
        target = previous if previous and self._occ_tree.exists(previous) else (rows[0][0] if rows else "")
        if target:
            self._occ_tree.selection_set(target)
            self._occ_tree.focus(target)
            self.render_occurrence_fields(detail, target)
        else:
            self._render_validation(None)
        self._occ_tree.configure(height=max(1, min(4, len(rows))))
        self._update_detail_identity(target)
        self._schedule_layout()

    def render_occurrence_fields(self, detail: ReportDetail, occurrence_id: str) -> None:
        for row in self._field_tree.get_children():
            self._field_tree.delete(row)
        for field_key, value in occurrence_field_rows(detail, occurrence_id):
            self._field_tree.insert("", "end", values=(field_key, value if value != "" else "(leer)"))
        self._render_validation(self._occurrences.get(occurrence_id))
        self._update_detail_identity(occurrence_id)

    def _update_detail_identity(self, occurrence_id: str) -> None:
        detail = self._current_detail
        if detail is None:
            return
        selected = next(((group, occurrence) for key, group, occurrence in iter_report_occurrences(detail) if key == occurrence_id), None)
        if selected is not None:
            group, occurrence = selected
            title = occurrence.assay_name or group.assay_display_label or "Assayname fehlt"
            charge = occurrence.charge or occurrence.lot_id or "—"
        else:
            title, charge = detail.file_name or "Bericht", "—"
        _file, time_text, device_text, status = report_detail_header_lines(detail)
        if selected is not None:
            device_text = occurrence.device_id or device_text
            time_text = format_timestamp(occurrence.created_at) if occurrence.created_at else time_text
        self._lbl_detail_title.configure(text=title)
        self._lbl_detail_meta.configure(text=f"{detail.file_name} · {time_text} | Gerät: {device_text} | Charge: {charge} | Status: {status} | Verarbeitung: {detail.display_status or '-'}")
