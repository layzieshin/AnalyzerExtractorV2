from __future__ import annotations

import math
import tkinter as tk
import tkinter.font as tkfont
from collections.abc import Callable, Sequence
from tkinter import ttk

from interfaces.tk.desktop_theme import FONT_FAMILY
from interfaces.tk.view_models import filter_validation_cases, format_timestamp, validation_case_status, validation_history_rows, validation_status_line
from interfaces.tk.widgets.common import Card, EmptyState, MultiSelectFilter, OverflowScrollbar, StatusBadge, create_scrollable_tree
from src.application.api import ReportPdfPage, ValidationQueueItem


PdfPreviewRequest = tuple[int, str, int, int, float]

_FIELD_LABELS = {
    "PLATTE": "Platte", "DATUM": "Messdatum", "ZEIT": "Uhrzeit", "TEST": "Testdatei", "FILE_NAME": "Dateiname",
    "CHARGE": "Charge", "ANWENDER": "Anwender", "MEASURED": "Messzeitpunkt",
    "PC_IST": "Positive Kontrolle · IST", "NC_IST": "Negative Kontrolle · IST",
    "PC_SOLL": "Positive Kontrolle · SOLL", "PC_MIN": "Positive Kontrolle · MIN", "PC_MAX": "Positive Kontrolle · MAX",
    "NC_SOLL": "Negative Kontrolle · SOLL", "NC_MIN": "Negative Kontrolle · MIN", "NC_MAX": "Negative Kontrolle · MAX",
}
_COMPACT_FIELD_LABELS = {
    "PC_IST": "Positiv · IST", "PC_SOLL": "Positiv · SOLL", "PC_MIN": "Positiv · MIN", "PC_MAX": "Positiv · MAX",
    "NC_IST": "Negativ · IST", "NC_SOLL": "Negativ · SOLL", "NC_MIN": "Negativ · MIN", "NC_MAX": "Negativ · MAX",
    "MEASURED": "Messzeit",
}


class ValidationView(ttk.Frame):
    """Primary work queue for human first validation of assay runs."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_refresh: Callable[[], None],
        on_save: Callable[[], None],
        on_open_pdf: Callable[[], None],
        on_preview: Callable[[PdfPreviewRequest], None] | None = None,
        on_reanalyze: Callable[[], None] | None = None,
        on_choose: Callable[[str], None] | None = None,
        on_edit_rules: Callable[[], None] | None = None,
        on_case_selected: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(master, style="Content.TFrame")
        self._on_refresh = on_refresh
        self._on_save = on_save
        self._on_open_pdf = on_open_pdf
        self._on_preview = on_preview
        self._on_reanalyze = on_reanalyze
        self._on_choose = on_choose
        self._on_edit_rules = on_edit_rules
        self._on_case_selected = on_case_selected
        self._reanalysis_busy = False
        self._items: dict[str, ValidationQueueItem] = {}
        self._all_items: tuple[ValidationQueueItem, ...] = ()
        self._direct_case: ValidationQueueItem | None = None
        self._selection_generation = 0
        self._active_selection = None
        self._focus_mode = False
        self._field_keys_by_row: dict[str, str] = {}
        self._field_labels_by_row: dict[str, str] = {}
        self._case_context_full = ""
        self._case_context_short = ""
        self._case_context_status = ""
        self._split_ratio = 0.52
        self._default_operator_initials = ""
        self._pdf_generation = 0
        self._pdf_identity: tuple[str, int] | None = None
        self._pdf_page_index = 0
        self._pdf_page_count = 0
        self._pdf_zoom = 1.0
        self._pdf_photo: tk.PhotoImage | None = None
        self._pdf_width = 0
        self._pdf_active = True
        self._pdf_initial_fit_pending = True
        self._pdf_initial_fit_after: str | None = None
        self._build()
        self.bind("<Destroy>", lambda event: self._cancel_initial_fit() if event.widget is self else None, add="+")

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        self._heading = heading = ttk.Frame(self, style="Content.TFrame")
        heading.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        heading.columnconfigure(0, weight=1)
        self._heading_eyebrow = ttk.Label(heading, text="F A C H L I C H E  P R Ü F U N G", style="Eyebrow.TLabel")
        self._heading_eyebrow.grid(row=0, column=0, sticky="w")
        self._heading_title = ttk.Label(heading, text="Prüfplatz", style="PageTitle.TLabel")
        self._heading_title.grid(row=1, column=0, sticky="w", pady=(6, 4))
        self._heading_description = ttk.Label(heading, text="Original und extrahierte Werte nebeneinander. Jede Freigabe gilt für eine konkrete Ergebnisfassung.",
                                              style="PageSubtitle.TLabel", wraplength=720)
        self._heading_description.grid(row=2, column=0, sticky="w")
        self._btn_focus = ttk.Button(heading, text="Fokusansicht", command=lambda: self.set_focus_mode(not self._focus_mode))
        self._btn_focus.grid(row=1, column=1, rowspan=2, sticky="se", padx=(12, 0))

        self._list_card = Card(self, rounded=True)
        self._list_card.grid(row=1, column=0, sticky="ew", pady=(0, 14))
        list_body = self._list_card.body
        self._list_bar = ttk.Frame(list_body, style="CardInner.TFrame")
        self._list_bar.pack(fill="x", pady=(0, 8))
        self._list_title = ttk.Label(self._list_bar, text="Arbeitsliste", style="SectionTitle.TLabel")
        self._list_title.grid(row=0, column=0, sticky="w", padx=(0, 8))
        self._filter_bar = filters = ttk.Frame(self._list_bar, style="CardInner.TFrame")
        filters.grid(row=0, column=1, sticky="w")
        self._list_bar.columnconfigure(1, weight=1)
        self._filters = {key: MultiSelectFilter(filters, title, on_change=self._apply_filters)
                         for key, title in (("status", "Status"), ("assay", "Assay"), ("device", "Gerät"))}
        for widget in self._filters.values():
            widget.pack(side="left", padx=(0, 8))
        self._lbl_list_count = ttk.Label(self._list_bar, text="", style="Muted.TLabel")
        self._lbl_list_count.grid(row=0, column=2, sticky="e", padx=(8, 8))
        self._btn_list_refresh = ttk.Button(self._list_bar, text="Aktualisieren", style="Toolbar.TButton", command=self._on_refresh)
        self._btn_list_refresh.grid(row=0, column=3, sticky="e")
        self._list_bar.bind("<Configure>", self._layout_list_bar)
        list_frame, self._tree = create_scrollable_tree(
            list_body, ("report", "assay", "lot", "device", "time", "status"),
            ("Bericht", "Assay", "Charge", "Gerät", "Zeit", "Status"), height=3, autohide=True,
        )
        list_frame.pack(fill="both", expand=True)
        self._tree.configure(selectmode="extended")
        self._tree.column("assay", width=260, minwidth=160, stretch=True)
        self._tree.bind("<<TreeviewSelect>>", self._on_select)
        self._tree.bind("<Double-1>", lambda _event: self.set_focus_mode(True))
        self._tree.bind("<Configure>", lambda _event: self._resize_list_columns(), add="+")
        self._empty = EmptyState(list_body, "Keine offenen Messungen in dieser Auswahl.")

        self._split = ttk.Panedwindow(self, orient="horizontal")
        self._split.grid(row=2, column=0, sticky="nsew")
        self._pdf_card = pdf_card = Card(self._split, padding=12, rounded=True)
        self._workflow_card = workflow_card = Card(self._split, padding=16, rounded=True)
        self._pdf_panel = pdf_card.body
        workflow = workflow_card.body
        workflow.columnconfigure(0, weight=1)
        workflow.rowconfigure(5, weight=1, minsize=32)
        self._split.add(pdf_card, weight=52)
        self._split.add(workflow_card, weight=48)
        self._split.bind("<Configure>", self._on_split_configure)
        self._split.bind("<ButtonRelease-1>", self._remember_split_ratio)
        self._build_pdf_panel()
        self._case_title_bar = title = ttk.Frame(workflow, style="CardInner.TFrame")
        title.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self._lbl_case_title = ttk.Label(title, text="Keine Messung ausgewählt", style="SectionTitle.TLabel", wraplength=350)
        self._lbl_case_title.pack(side="left", fill="x", expand=True)
        self._case_status = StatusBadge(title)
        self._case_status.pack(side="right", padx=(8, 0))
        self._lbl_context = ttk.Label(workflow, text="Keine Messung ausgewaehlt.", style="Muted.TLabel", wraplength=460)
        self._lbl_context.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        workflow.bind("<Configure>", self._layout_workflow_text)

        self._validation_form = form = ttk.Frame(workflow, style="CardInner.TFrame")
        form.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        form.columnconfigure(0, weight=1)
        form.columnconfigure(1, weight=1)
        self._lbl_initials = ttk.Label(form, text="Initialen")
        self._lbl_comment = ttk.Label(form, text="Kommentar (optional)")
        self._var_initials = tk.StringVar()
        self._var_comment = tk.StringVar()
        self._entry_initials = ttk.Entry(form, textvariable=self._var_initials, width=8)
        self._entry_comment = ttk.Entry(form, textvariable=self._var_comment, width=10)

        self._case_actions = actions = ttk.Frame(workflow, style="CardInner.TFrame")
        actions.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        self._btn_save = ttk.Button(actions, text="Validierung speichern", style="Primary.TButton", command=self._on_save)
        self._btn_save.grid(row=0, column=0, sticky="w")
        self._btn_reanalyze = ttk.Button(actions, text="Erneut analysieren", command=lambda: self._on_reanalyze and self._on_reanalyze())
        self._btn_reanalyze.grid(row=0, column=1, sticky="w", padx=(8, 0))
        self._btn_edit_rules = ttk.Button(actions, text="Regelwerk bearbeiten", command=lambda: self._on_edit_rules and self._on_edit_rules())
        self._btn_edit_rules.grid(row=1, column=0, columnspan=2, sticky="w", pady=(5, 0))
        actions.bind("<Configure>", self._layout_case_actions)
        self._choices = ttk.Frame(workflow, style="CardInner.TFrame")
        self._choices.grid(row=4, column=0, sticky="ew", pady=(0, 10))
        self._btn_keep_old = ttk.Button(self._choices, text="Alte Werte behalten", command=lambda: self._on_choose and self._on_choose("keep_old"))
        self._btn_keep_old.pack(side="left")
        self._btn_accept_new = ttk.Button(self._choices, text="Neue Werte übernehmen", command=lambda: self._on_choose and self._on_choose("accept_new"))
        self._btn_accept_new.pack(side="left", padx=(8, 0))

        self._tabs = ttk.Notebook(workflow)
        self._tabs.grid(row=5, column=0, sticky="nsew")
        values_panel, history_panel = ttk.Frame(self._tabs, style="CardInner.TFrame"), ttk.Frame(self._tabs, style="CardInner.TFrame")
        self._tabs.add(values_panel, text="Werte")
        self._tabs.add(history_panel, text="Verlauf")
        fields_frame, self._fields = create_scrollable_tree(
            values_panel,
            ("field", "old", "new"),
            ("Feld / Nachweis", "Gewaehlte Werte", "Neue Werte"),
            height=4, autohide=True,
        )
        fields_frame.pack(fill="both", expand=True)
        self._fields.bind("<Configure>", self._resize_value_columns)
        self._field_metadata_menu = tk.Menu(self._fields, tearoff=False)
        self._fields.bind("<<TreeviewSelect>>", self._show_selected_field_key)
        self._fields.bind("<Button-3>", self._open_field_metadata)
        self._fields.bind("<Shift-F10>", self._open_field_metadata)
        self._fields.tag_configure("changed", background="#fff3cd")
        self._fields.tag_configure("metadata", foreground="#526171")
        history_frame, self._history = create_scrollable_tree(history_panel, ("state", "initials", "time", "comment"),
                                                            ("Stand / Ereignis", "Initialen", "Zeit", "Kommentar / Nachweis"), height=5, autohide=True)
        history_frame.pack(fill="both", expand=True)
        self._btn_save.configure(state="disabled")
        self._btn_open_pdf.configure(state="disabled")
        for button in (self._btn_reanalyze, self._btn_keep_old, self._btn_accept_new, self._btn_edit_rules):
            button.configure(state="disabled")
        self._choices.grid_remove()
        self.set_focus_mode(False)
        self.bind("<Configure>", self._layout_validation_view)

    def _build_pdf_panel(self) -> None:
        panel = self._pdf_panel
        self._pdf_toolbar = ttk.Frame(panel, style="CardInner.TFrame")
        self._pdf_toolbar.pack(fill="x", pady=(0, 6))
        self._pdf_toolbar.columnconfigure(0, weight=1)
        self._pdf_title = ttk.Label(self._pdf_toolbar, text="Original-PDF", style="ToolbarTitle.TLabel")
        self._pdf_navigation = navigation = ttk.Frame(self._pdf_toolbar, style="CardInner.TFrame")
        self._btn_pdf_previous = ttk.Button(navigation, text="‹", width=2, style="Toolbar.TButton", command=lambda: self._change_pdf_page(-1))
        self._btn_pdf_previous.pack(side="left")
        self._lbl_pdf_page = ttk.Label(navigation, text="Seite - / -", style="Toolbar.TLabel")
        self._lbl_pdf_page.pack(side="left", padx=4)
        self._btn_pdf_next = ttk.Button(navigation, text="›", width=2, style="Toolbar.TButton", command=lambda: self._change_pdf_page(1))
        self._btn_pdf_next.pack(side="left")
        self._btn_open_pdf = ttk.Button(self._pdf_toolbar, text="Extern öffnen", style="Toolbar.TButton", command=self._on_open_pdf)
        self._pdf_zoom_bar = zoom = ttk.Frame(self._pdf_toolbar, style="CardInner.TFrame")
        self._btn_pdf_zoom_out = ttk.Button(zoom, text="-", width=2, style="Toolbar.TButton", command=lambda: self._set_pdf_zoom(self._pdf_zoom - 0.25))
        self._btn_pdf_zoom_out.pack(side="left")
        self._lbl_pdf_zoom = ttk.Label(zoom, text="100 %", width=5, anchor="center", style="Toolbar.TLabel")
        self._lbl_pdf_zoom.pack(side="left")
        self._btn_pdf_zoom_in = ttk.Button(zoom, text="+", width=2, style="Toolbar.TButton", command=lambda: self._set_pdf_zoom(self._pdf_zoom + 0.25))
        self._btn_pdf_zoom_in.pack(side="left")
        self._btn_pdf_fit = ttk.Button(zoom, text="Breite", style="Toolbar.TButton", command=self._fit_pdf_width)
        self._btn_pdf_fit.pack(side="left", padx=(4, 0))
        self._lbl_pdf_status = ttk.Label(panel, text="Keine Messung ausgewaehlt.", style="Muted.TLabel", wraplength=450)
        self._lbl_pdf_filename = ttk.Label(panel, text="Keine PDF ausgewählt.", style="CompactMuted.TLabel", wraplength=450)
        self._lbl_pdf_filename.pack(anchor="w", fill="x", pady=(0, 4))
        self._lbl_pdf_status.pack(anchor="w", fill="x", pady=(0, 6))
        self._pdf_viewport = viewport = ttk.Frame(panel, style="CardInner.TFrame")
        viewport.pack(fill="both", expand=True)
        viewport.rowconfigure(0, weight=1)
        viewport.columnconfigure(0, weight=1)
        self._pdf_canvas = tk.Canvas(viewport, background="#e3eaf2", highlightthickness=0, width=400, height=400,
                                     takefocus=True, xscrollincrement=20, yscrollincrement=20)
        vertical = OverflowScrollbar(viewport, orient="vertical", command=self._pdf_canvas.yview)
        horizontal = OverflowScrollbar(viewport, orient="horizontal", command=self._pdf_canvas.xview)
        self._pdf_canvas.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self._pdf_canvas.grid(row=0, column=0, sticky="nsew")
        self._pdf_canvas.bind("<MouseWheel>", self._scroll_pdf)
        self._pdf_canvas.bind("<Shift-MouseWheel>", lambda event: self._scroll_pdf(event, axis="x"))
        self._pdf_canvas.bind("<Next>", lambda _event: self._pdf_canvas.yview_scroll(1, "pages") or "break")
        self._pdf_canvas.bind("<Prior>", lambda _event: self._pdf_canvas.yview_scroll(-1, "pages") or "break")
        panel.bind("<Configure>", self._layout_pdf_panel)
        self._layout_pdf_panel()
        self._update_pdf_controls()

    def _layout_pdf_panel(self, event: tk.Event | None = None) -> None:
        width = event.width if event is not None else self._pdf_panel.winfo_width()
        self._lbl_pdf_status.configure(wraplength=max(180, width - 12))
        self._lbl_pdf_filename.configure(wraplength=max(180, width - 12))
        title, pages, zoom, external = self._pdf_title, self._pdf_navigation, self._pdf_zoom_bar, self._btn_open_pdf
        for widget in (title, pages, zoom, external):
            widget.grid_forget()
        full = sum(widget.winfo_reqwidth() for widget in (title, pages, zoom, external)) + 24
        if width >= full:
            for column, widget in enumerate((title, pages, zoom, external)):
                widget.grid(row=0, column=column, sticky="w" if column == 0 else "e", padx=(0, 6) if column < 3 else 0)
        else:
            title.grid(row=0, column=0, columnspan=3, sticky="w")
            external.grid(row=0, column=3, sticky="e")
            if width >= pages.winfo_reqwidth() + zoom.winfo_reqwidth() + 8:
                pages.grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))
                zoom.grid(row=1, column=2, columnspan=2, sticky="e", pady=(4, 0))
            else:
                pages.grid(row=1, column=0, columnspan=4, sticky="w", pady=(4, 0))
                zoom.grid(row=2, column=0, columnspan=4, sticky="w", pady=(4, 0))

    def _scroll_pdf(self, event: tk.Event, *, axis: str = "y") -> str:
        view = self._pdf_canvas.xview if axis == "x" else self._pdf_canvas.yview
        scroll = self._pdf_canvas.xview_scroll if axis == "x" else self._pdf_canvas.yview_scroll
        if event.delta and view() != (0.0, 1.0):
            units = int(event.delta / 120) or (1 if event.delta > 0 else -1)
            scroll(-units * 3, "units")
        return "break"

    def _layout_workflow_text(self, event: tk.Event | None = None) -> None:
        width = event.width if event is not None else self._workflow_card.body.winfo_width()
        self._lbl_context.configure(wraplength=max(160, width - 8))
        self._lbl_case_title.configure(wraplength=max(100, width - self._case_status.winfo_reqwidth() - 12),
                                       style="ToolbarTitle.TLabel" if width < 380 else "SectionTitle.TLabel")
        compact = width < 380
        self._lbl_context.configure(style="CompactMuted.TLabel" if compact else "Muted.TLabel")
        item = self.selected_item()
        if item is not None:
            meta = self._case_context_short if compact else self._case_context_full
            self._lbl_context.configure(text=meta + (f"\n{self._case_context_status}" if self._case_context_status else ""))
            identity = f"{item.file_name or 'Original-PDF'} · Revision {item.revision_id}"
            if compact:
                identity += f"\n{format_timestamp(item.created_at)}"
            self._lbl_pdf_filename.configure(text=identity)
        self._case_title_bar.grid_configure(pady=(0, 4 if compact else 8))
        self._lbl_context.grid_configure(pady=(0, 2 if compact else 12))
        self._validation_form.grid_configure(pady=(0, 4 if compact else 10))
        self._case_actions.grid_configure(pady=(0, 4 if compact else 10))
        self._tabs.configure(style="Compact.TNotebook" if compact else "TNotebook")
        self._layout_validation_form(compact)

    def _layout_validation_form(self, compact: bool) -> None:
        for widget in (self._lbl_initials, self._lbl_comment, self._entry_initials, self._entry_comment):
            widget.grid_forget()
        for column in range(4):
            self._validation_form.columnconfigure(column, weight=0)
        self._lbl_initials.configure(style="Toolbar.TLabel" if compact else "TLabel")
        self._lbl_comment.configure(text="Kommentar" if compact else "Kommentar (optional)", style="Toolbar.TLabel" if compact else "TLabel")
        self._entry_initials.configure(width=4 if compact else 8, font=(FONT_FAMILY, 9 if compact else 10))
        self._entry_comment.configure(width=8 if compact else 10, font=(FONT_FAMILY, 9 if compact else 10))
        if compact:
            self._lbl_initials.grid(row=0, column=0, sticky="w")
            self._entry_initials.grid(row=0, column=1, sticky="w", padx=(5, 8))
            self._lbl_comment.grid(row=0, column=2, sticky="w")
            self._entry_comment.grid(row=0, column=3, sticky="ew", padx=(5, 0))
            self._validation_form.columnconfigure(3, weight=1)
        else:
            self._lbl_initials.grid(row=0, column=0, sticky="w")
            self._lbl_comment.grid(row=0, column=1, sticky="w", padx=(10, 0))
            self._entry_initials.grid(row=1, column=0, sticky="ew", pady=(4, 0))
            self._entry_comment.grid(row=1, column=1, sticky="ew", padx=(10, 0), pady=(4, 0))
            self._validation_form.columnconfigure(0, weight=1)
            self._validation_form.columnconfigure(1, weight=1)

    def _layout_case_actions(self, event: tk.Event | None = None) -> None:
        width = event.width if event is not None else self._case_actions.winfo_width()
        if width < 20:
            return
        item = self.selected_item()
        self._btn_save.configure(text=("Korrigieren" if item is not None and item.current_validation is not None else "Validieren") if width < 380
                                 else ("Validierung korrigieren" if item is not None and item.current_validation is not None else "Validierung speichern"))
        self._btn_reanalyze.configure(text="Neu analysieren" if width < 380 else "Erneut analysieren")
        self._btn_save.configure(style="Compact.Primary.TButton" if width < 540 else "Primary.TButton")
        for button in (self._btn_reanalyze, self._btn_edit_rules):
            button.configure(style="Toolbar.TButton" if width < 540 else "TButton")
        buttons = (self._btn_save, self._btn_reanalyze, self._btn_edit_rules)
        for button in buttons:
            button.grid_forget()
        if width >= sum(button.winfo_reqwidth() for button in buttons) + 16:
            for column, button in enumerate(buttons):
                button.grid(row=0, column=column, sticky="w", padx=(8, 0) if column else 0)
        elif width >= self._btn_save.winfo_reqwidth() + self._btn_reanalyze.winfo_reqwidth() + 8:
            self._btn_save.grid(row=0, column=0, sticky="w")
            self._btn_reanalyze.grid(row=0, column=1, sticky="w", padx=(8, 0))
            self._btn_edit_rules.grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))
        else:
            for row, button in enumerate(buttons):
                button.grid(row=row, column=0, sticky="w", pady=(4, 0) if row else 0)

    def _layout_list_bar(self, event: tk.Event | None = None) -> None:
        width = event.width if event is not None else self._list_bar.winfo_width()
        compact = width < 800
        self._list_title.configure(style="ToolbarTitle.TLabel" if compact else "SectionTitle.TLabel")
        self._lbl_list_count.configure(text=f"{len(self._items)}/{len(self._all_items)}" if compact else f"{len(self._items)} / {len(self._all_items)} offen",
                                       style="Toolbar.TLabel" if compact else "Muted.TLabel")
        for widget in self._filters.values():
            widget.configure(style="Compact.TMenubutton" if compact else "TMenubutton")
        needed = self._list_title.winfo_reqwidth() + self._filter_bar.winfo_reqwidth() + self._btn_list_refresh.winfo_reqwidth() + self._lbl_list_count.winfo_reqwidth() + 36
        if width >= needed:
            self._filter_bar.grid_configure(row=0, column=1, columnspan=1, pady=0)
        else:
            self._filter_bar.grid_configure(row=1, column=0, columnspan=4, pady=(5, 0))

    def _layout_validation_view(self, event: tk.Event | None = None) -> None:
        if event is not None and event.widget is not self:
            return
        compact = self.winfo_height() < 650
        if compact:
            self._heading_eyebrow.grid_remove()
            self._heading_description.grid_remove()
        else:
            self._heading_eyebrow.grid()
            self._heading_description.grid()
        self._heading_title.grid_configure(pady=0 if compact else (6, 4))
        self._heading_title.configure(style="CompactPageTitle.TLabel" if compact else "PageTitle.TLabel")
        self._heading.grid_configure(pady=(0, 2 if compact else 16))
        if self._list_card.winfo_manager() == "grid":
            self._list_card.grid_configure(pady=(0, 4 if compact else 14))
        self._heading_description.configure(wraplength=max(180, self.winfo_width() - self._btn_focus.winfo_reqwidth() - 20))
        self._tree.configure(height=min(max(1, len(self._items)), 2 if compact else 3))
        self._resize_list_columns()
        self._layout_list_bar()

    def _resize_list_columns(self) -> None:
        font = tkfont.Font(self, font=ttk.Style(self).lookup("Treeview", "font"))
        available = self._tree.winfo_width() - 4
        if available < 30:
            return
        values = {
            "report": (210, [item.file_name for item in self._items.values()]),
            "lot": (90, [item.lot_id for item in self._items.values()]),
            "device": (110, [item.device_id for item in self._items.values()]),
            "time": (145, [format_timestamp(item.created_at) for item in self._items.values()]),
            "status": (110, [validation_case_status(item) for item in self._items.values()]),
        }
        widths = {column: max(minimum, max((font.measure(text) + 20 for text in texts), default=0))
                  for column, (minimum, texts) in values.items()}
        assay_min = max(130, min(200, max((font.measure(item.assay_name or "Assayname fehlt") + 20 for item in self._items.values()), default=160)))
        if available >= sum(widths.values()) + assay_min:
            visible = ("report", "assay", "lot", "device", "time", "status")
        else:
            widths["report"] = min(widths["report"], max(190, int(available * 0.45)))
            visible = ("report", "assay", "lot", "status") if available >= widths["report"] + widths["status"] + widths["lot"] + assay_min else ("report", "assay", "status")
        self._tree.configure(displaycolumns=visible)
        fixed = sum(widths[column] for column in visible if column != "assay")
        for column in visible:
            self._tree.column(column, width=max(50, available - fixed) if column == "assay" else widths[column], minwidth=1, stretch=False)

    @staticmethod
    def _field_label(field: object) -> str:
        key = str(field.field_key)
        configured = getattr(field, "display_label", "") or getattr(field, "label", "")
        label = configured.strip() if isinstance(configured, str) else ""
        label = label or _FIELD_LABELS.get(key, "")
        return label or key

    def _show_selected_field_key(self, _event: object = None) -> None:
        selection = self._fields.selection()
        key = self._field_keys_by_row.get(str(selection[0])) if selection else None
        self._field_metadata_menu.delete(0, "end")
        if key is not None:
            self._field_metadata_menu.add_command(label=self._field_labels_by_row[str(selection[0])], state="disabled")
            self._field_metadata_menu.add_command(label=f"Feldschlüssel: {key}", state="disabled")

    def _open_field_metadata(self, event: tk.Event) -> str:
        if getattr(event, "num", None) == 3:
            row = self._fields.identify_row(event.y)
            if row:
                self._fields.selection_set(row)
        self._show_selected_field_key()
        if self._field_metadata_menu.index("end") is not None:
            try:
                self._field_metadata_menu.tk_popup(event.x_root, event.y_root)
            finally:
                self._field_metadata_menu.grab_release()
        return "break"

    def _resize_value_columns(self, _event: tk.Event | None = None) -> None:
        width = self._fields.winfo_width() - 4
        if width < 20:
            return
        compact = width < 380
        self._fields.configure(style="CompactValues.Treeview" if compact else "Treeview")
        for row, key in self._field_keys_by_row.items():
            full = self._field_labels_by_row[row]
            label = _COMPACT_FIELD_LABELS.get(key, full) if compact and full == _FIELD_LABELS.get(key) else full
            self._fields.set(row, "field", label)
        columns = tuple(self._fields.cget("displaycolumns"))
        self._fields.heading("field", text="Feld")
        if "new" not in columns:
            self._fields.heading("old", text="Wert" if width < 450 else "Extrahierter Wert")
        font = tkfont.Font(self, font=ttk.Style(self).lookup(self._fields.cget("style"), "font"))
        padding = 12 if compact else 16
        natural = {column: max([font.measure(str(self._fields.heading(column, "text"))) + padding,
                                *(font.measure(str(self._fields.set(key, column))) + padding for key in self._fields.get_children())])
                   for column in columns}
        remaining = max(0, width - sum(natural.values()))
        field_extra = int(remaining * 0.6)
        value_extra = remaining - field_extra
        value_columns = [column for column in columns if column != "field"]
        for column in columns:
            extra = field_extra if column == "field" else (value_extra // len(value_columns) + (value_columns.index(column) < value_extra % len(value_columns)))
            self._fields.column(column, width=max(50, natural[column] + extra), minwidth=50, stretch=False)

    def _on_split_configure(self, event: tk.Event) -> None:
        if event.width > 1:
            self._split.sashpos(0, round(event.width * self._split_ratio))

    def _remember_split_ratio(self, _event: object) -> None:
        if self._split.winfo_width() > 1:
            self._split_ratio = max(0.2, min(0.8, self._split.sashpos(0) / self._split.winfo_width()))

    def set_focus_mode(self, enabled: bool) -> None:
        self._focus_mode = bool(enabled)
        if enabled:
            self._list_card.grid_remove()
        else:
            self._list_card.grid()
        self._btn_focus.configure(text="Arbeitsliste anzeigen" if enabled else "Fokusansicht")
        self._layout_validation_view()

    def selection_context(self) -> tuple:
        # The immutable displayed binding is also safe to compare in preview/open workers.
        return self._selection_generation, self._active_selection

    def is_direct_case(self) -> bool:
        return self._direct_case is not None

    def begin_direct_loading(self, *, focus: bool = True) -> None:
        self._direct_case = None
        self._tree.selection_remove(self._tree.selection())
        self._render_item(None, refresh_pdf=True)
        self._lbl_context.configure(text="Die ausgewählte Messung wird geladen …")
        if focus:
            self.set_focus_mode(True)

    def end_direct_loading(self, message: str) -> None:
        self._direct_case = None
        self._tree.selection_remove(self._tree.selection())
        self._render_item(None, refresh_pdf=True)
        self._lbl_case_title.configure(text="Messung nicht verfügbar")
        self._lbl_context.configure(text=message)
        self.set_focus_mode(False)

    def invalidate_store_context(self) -> None:
        self.render_cases(())
        self.clear_comment()
        self._lbl_context.configure(text="Ergebnisspeicher gewechselt. Bitte aktualisieren.")

    def next_visible_run_id(self) -> int | None:
        current = self.selected_item()
        keys = list(self._tree.get_children())
        if not keys:
            return None
        key = str(current.run_id) if current else ""
        if key in keys:
            keys = keys[keys.index(key) + 1:] + keys[:keys.index(key)]
        return next((int(key) for key in keys if self._first_validation_ready(self._items[key])), None)

    @staticmethod
    def _first_validation_ready(item: ValidationQueueItem) -> bool:
        return not (item.current_validation or item.validation_ambiguous or item.comparison or
                    item.missing_fields or item.revision_error or item.activation_blocked_reason)

    def pdf_request(self) -> PdfPreviewRequest | None:
        if self._pdf_identity is None or not self._pdf_active:
            return None
        report_id, run_id = self._pdf_identity
        return self._pdf_generation, report_id, run_id, self._pdf_page_index, self._pdf_zoom

    def _clear_pdf_image(self) -> None:
        self._cancel_initial_fit()
        self._pdf_canvas.delete("all")
        self._pdf_canvas.configure(scrollregion=(0, 0, 0, 0))
        self._pdf_photo = None

    def _request_pdf_page(self) -> None:
        self._pdf_generation += 1
        self._clear_pdf_image()
        request = self.pdf_request()
        if request is not None:
            self._lbl_pdf_status.configure(text="PDF wird geladen …")
            self._lbl_pdf_status.pack(anchor="w", fill="x", pady=(0, 6), before=self._pdf_viewport)
            if self._on_preview is not None:
                self._on_preview(request)
        self._update_pdf_controls()

    def _update_pdf_controls(self) -> None:
        selected = self._pdf_identity is not None and self._pdf_active
        known_page = selected and 0 <= self._pdf_page_index < self._pdf_page_count
        self._lbl_pdf_page.configure(text=f"Seite {self._pdf_page_index + 1} / {self._pdf_page_count}" if self._pdf_page_count else "Seite - / -")
        self._lbl_pdf_zoom.configure(text=f"{self._pdf_zoom:.0%}")
        self._btn_pdf_previous.configure(state="normal" if known_page and self._pdf_page_index > 0 else "disabled")
        self._btn_pdf_next.configure(state="normal" if known_page and self._pdf_page_index + 1 < self._pdf_page_count else "disabled")
        self._btn_pdf_zoom_out.configure(state="normal" if selected and self._pdf_zoom > 0.25 else "disabled")
        self._btn_pdf_zoom_in.configure(state="normal" if selected and self._pdf_zoom < 3.0 else "disabled")
        self._btn_pdf_fit.configure(state="normal" if selected and self._pdf_photo is not None else "disabled")
        self._layout_pdf_panel()

    def _change_pdf_page(self, delta: int) -> None:
        target = self._pdf_page_index + delta
        if self._pdf_identity is not None and 0 <= target < self._pdf_page_count:
            self._pdf_page_index = target
            self._request_pdf_page()

    def _set_pdf_zoom(self, zoom: float, *, automatic: bool = False) -> None:
        if not math.isfinite(zoom) or zoom <= 0:
            return
        if not automatic:
            self._pdf_initial_fit_pending = False
            self._cancel_initial_fit()
        target = min(3.0, zoom if automatic else max(0.25, zoom))
        if self._pdf_identity is not None and not math.isclose(target, self._pdf_zoom, rel_tol=1e-9, abs_tol=0.0):
            self._pdf_zoom = target
            self._request_pdf_page()

    def _fit_pdf_width(self) -> None:
        self._pdf_initial_fit_pending = False
        if self._pdf_width > 0 and self._pdf_photo is not None:
            # Reserve the canvas padding plus two pixels for outward raster rounding.
            width = max(1, self._pdf_canvas.winfo_width() - 18)
            self._set_pdf_zoom(self._pdf_zoom * width / self._pdf_width, automatic=True)

    def _cancel_initial_fit(self) -> None:
        if self._pdf_initial_fit_after is not None:
            self.after_cancel(self._pdf_initial_fit_after)
            self._pdf_initial_fit_after = None

    def _fit_initial_page(self, request: PdfPreviewRequest) -> None:
        self._pdf_initial_fit_after = None
        if request == self.pdf_request() and self._pdf_photo is not None and self._pdf_canvas.winfo_ismapped():
            if self._pdf_width > self._pdf_canvas.winfo_width() - 16:
                self._fit_pdf_width()

    def render_pdf_page(self, request: PdfPreviewRequest, page: ReportPdfPage) -> None:
        if request != self.pdf_request():
            return
        if page.report_id != request[1] or page.page_index != request[3]:
            self.render_pdf_error(request, "Die PDF-Vorschau passt nicht zur gewaehlten Messung. Bitte aktualisieren.")
            return
        try:
            photo = tk.PhotoImage(master=self, data=page.image_data, format="PPM")
        except tk.TclError:
            self.render_pdf_error(request, "Die PDF-Seite konnte nicht angezeigt werden.")
            return
        self._clear_pdf_image()
        self._pdf_photo = photo
        self._pdf_width = page.width
        self._pdf_page_count = page.page_count
        self._pdf_zoom = page.zoom
        self._pdf_canvas.create_image(8, 8, anchor="nw", image=photo)
        self._pdf_canvas.configure(scrollregion=(0, 0, page.width + 16, page.height + 16))
        self._pdf_canvas.xview_moveto(0)
        self._pdf_canvas.yview_moveto(0)
        item = self.selected_item()
        self._lbl_pdf_status.configure(text=item.file_name if item is not None else "Original-PDF")
        self._lbl_pdf_status.pack_forget()
        self._update_pdf_controls()
        if self._pdf_initial_fit_pending and self._pdf_canvas.winfo_ismapped() and self._pdf_canvas.winfo_width() > 100:
            self._pdf_initial_fit_pending = False
            if page.width > self._pdf_canvas.winfo_width() - 16:
                self._pdf_initial_fit_after = self.after_idle(lambda: self._fit_initial_page(request))

    def render_pdf_error(self, request: PdfPreviewRequest, message: str) -> None:
        if request != self.pdf_request():
            return
        self._clear_pdf_image()
        # Keep the last successful page bounds so Previous can recover from a
        # later-page timeout. Unknown documents remain at page zero with no nav.
        if self._pdf_page_count <= 0:
            self._pdf_page_index = 0
        self._lbl_pdf_status.configure(text=message)
        self._lbl_pdf_status.pack(anchor="w", fill="x", pady=(0, 6), before=self._pdf_viewport)
        self._update_pdf_controls()

    def suspend_pdf_preview(self) -> None:
        self._pdf_active = False
        self._pdf_generation += 1
        self._clear_pdf_image()
        self._update_pdf_controls()

    def resume_pdf_preview(self) -> None:
        self._pdf_active = True
        self._request_pdf_page()

    def set_default_operator_initials(self, initials: str) -> None:
        self._default_operator_initials = str(initials or "").strip()
        if not str(self._var_initials.get() or "").strip():
            self._var_initials.set(self._default_operator_initials)

    def selected_item(self) -> ValidationQueueItem | None:
        if self._direct_case is not None:
            return self._direct_case
        selection = self._tree.selection()
        focused = self._tree.focus()
        target = focused if focused in selection else (selection[0] if selection else "")
        return self._items.get(str(target))

    def selected_items(self) -> tuple[ValidationQueueItem, ...]:
        if self._direct_case is not None:
            return (self._direct_case,)
        selected = set(self._tree.selection())
        return tuple(self._items[str(key)] for key in self._tree.get_children() if key in selected)

    def set_reanalysis_busy(self, busy: bool) -> None:
        self._reanalysis_busy = busy
        self._render_item(self.selected_item())

    def validation_initials(self) -> str:
        return self._var_initials.get()

    def validation_comment(self) -> str:
        return self._var_comment.get()

    def clear_comment(self) -> None:
        self._var_comment.set("")

    def render_cases(self, items: Sequence[ValidationQueueItem], *, direct_case: ValidationQueueItem | None = None,
                     preferred_run_id: int | None = None, advance: bool = False) -> None:
        self._all_items = tuple(items)
        self._direct_case = direct_case
        self._filters["status"].set_options(tuple(validation_case_status(item) for item in items))
        self._filters["assay"].set_options(tuple(item.assay_name or "Assayname fehlt" for item in items))
        self._filters["device"].set_options(tuple(item.device_id or "–" for item in items))
        self._apply_filters(preferred_run_id=preferred_run_id, advance=advance)

    def reconcile_cases(self, items: Sequence[ValidationQueueItem]) -> None:
        """Reconcile a completed action without replacing a newer user selection/draft."""
        self._all_items = tuple(items)
        self._filters["status"].set_options(tuple(validation_case_status(item) for item in items))
        self._filters["assay"].set_options(tuple(item.assay_name or "Assayname fehlt" for item in items))
        self._filters["device"].set_options(tuple(item.device_id or "–" for item in items))
        self._apply_filters(preserve_context=True)

    def _apply_filters(self, *, preferred_run_id: int | None = None, advance: bool = False,
                       preserve_context: bool = False) -> None:
        selected = self.selected_item()
        previous_selection = tuple(self._tree.selection())
        previous_run_id = preferred_run_id if preferred_run_id is not None else (selected.run_id if selected is not None else None)
        items = filter_validation_cases(self._all_items, statuses=self._filters["status"].selected_values,
                                        assays=self._filters["assay"].selected_values, devices=self._filters["device"].selected_values)
        if not preserve_context:
            self._selection_generation += 1
        for row in self._tree.get_children():
            self._tree.delete(row)
        self._items = {str(item.run_id): item for item in items}
        self._lbl_list_count.configure(text=f"{len(items)} von {len(self._all_items)} offen")
        if not items:
            self._empty.pack(anchor="w", pady=(8, 0))
            self._render_item(self._direct_case, refresh_pdf=not preserve_context)
            self._layout_validation_view()
            return
        self._empty.pack_forget()
        for item in items:
            status = validation_case_status(item)
            self._tree.insert(
                "",
                "end",
                iid=str(item.run_id),
                values=(item.file_name or "-", item.assay_name or "Assayname fehlt", item.lot_id or "-", item.device_id or "-", format_timestamp(item.created_at), status),
            )
        if self._direct_case is not None:
            self._tree.selection_remove(self._tree.selection())
            self._render_item(self._direct_case, refresh_pdf=not preserve_context)
            self._layout_validation_view()
            return
        target = str(previous_run_id) if previous_run_id is not None and self._tree.exists(str(previous_run_id)) else ""
        if advance:
            eligible = [str(item.run_id) for item in items if self._first_validation_ready(item)]
            target = target if target in eligible else next(iter(eligible), "")
        elif not target and not preserve_context:
            target = str(items[0].run_id)
        retained = tuple(key for key in previous_selection if key in self._items)
        self._tree.selection_set(((target,) if target else ()) if advance or preferred_run_id is not None else (retained or ((target,) if target else ())))
        self._tree.focus(target)
        self._render_item(self._items.get(target), refresh_pdf=not preserve_context)
        self._layout_validation_view()

    def _on_select(self, _event: object) -> None:
        if self._direct_case is not None and not self._tree.selection():
            return
        if self._tree.selection() and self._on_case_selected is not None:
            self._on_case_selected()
        self._direct_case = None
        self._render_item(self.selected_item())

    def _render_item(self, item: ValidationQueueItem | None, *, refresh_pdf: bool = False) -> None:
        binding = (item.store_path, item.report_id, item.run_id, item.selection_token) if item else None
        rebind_pending_pdf = binding != self._active_selection and self._pdf_identity is not None and self._pdf_photo is None
        if binding != self._active_selection:
            self._active_selection = binding
            self._selection_generation += 1
        identity = (item.report_id, item.run_id) if item is not None else None
        changed = identity != self._pdf_identity
        if changed:
            self._pdf_identity = identity
            self._pdf_zoom = 1.0
            self._pdf_initial_fit_pending = True
        if changed or refresh_pdf or rebind_pending_pdf:
            # Refresh rediscovers the source from page one: the same report may
            # now resolve to a shorter PDF, so an old page index is not reusable.
            if changed or refresh_pdf:
                self._pdf_page_index = 0
                self._pdf_page_count = 0
                self._pdf_width = 0
            self._request_pdf_page()
        for row in self._fields.get_children():
            self._fields.delete(row)
        self._field_keys_by_row.clear()
        self._field_labels_by_row.clear()
        self._field_metadata_menu.delete(0, "end")
        for row in self._history.get_children():
            self._history.delete(row)
        if item is None:
            self._lbl_pdf_filename.configure(text="Keine PDF ausgewählt.")
            self._lbl_case_title.configure(text="Keine Messung ausgewählt")
            self._case_status.set_status("")
            self._choices.grid_remove()
            self._lbl_context.configure(text="Keine Messung ausgewaehlt.")
            self._btn_save.configure(state="disabled")
            self._btn_open_pdf.configure(state="disabled")
            for button in (self._btn_reanalyze, self._btn_keep_old, self._btn_accept_new, self._btn_edit_rules):
                button.configure(state="disabled")
            self._lbl_pdf_status.configure(text="Keine offenen Validierungen." if not self._items else "Keine Messung ausgewaehlt.")
            self._fields.configure(displaycolumns=("field", "old"))
            self._resize_value_columns()
            return
        self._lbl_case_title.configure(text=item.assay_name or "Assayname fehlt")
        self._lbl_pdf_filename.configure(text=f"{item.file_name or 'Original-PDF'} · Revision {item.revision_id}")
        status_name = validation_case_status(item)
        self._case_status.set_status(status_name, kind="success" if status_name == "Validiert" else "warning" if status_name != "Offen" else "neutral")
        status = validation_status_line(item) if item.current_validation or item.validation_ambiguous else f"Revision {item.revision_id}: bereit zur Erstvalidierung."
        comparison = item.comparison
        if comparison:
            status = "Vergleich offen. Alte oder neue Werte auswaehlen, danach separat validieren."
            if comparison.error:
                status += " Nacharbeit: " + comparison.error
        elif item.revision_error or item.missing_fields:
            status = "Nacharbeit erforderlich: " + (item.revision_error or ", ".join(item.missing_fields))
        if item.activation_blocked_reason:
            status = item.activation_blocked_reason
        meta = f"Charge {item.lot_id or '-'} · {item.device_id or '-'} · {format_timestamp(item.created_at)}"
        needs_explanation = item.current_validation or item.validation_ambiguous or comparison or item.revision_error or item.missing_fields or item.activation_blocked_reason
        self._case_context_full = meta
        self._case_context_short = f"Charge {item.lot_id or '-'} · {item.device_id or '-'}"
        self._case_context_status = status if needs_explanation else ""
        self._lbl_context.configure(text=meta + (f"\n{status}" if needs_explanation else ""))
        self._fields.heading("old", text="Alte Werte" if comparison else "Gewaehlte Werte")
        self._fields.configure(displaycolumns=("field", "old", "new") if comparison else ("field", "old"))
        self._btn_save.configure(text="Validierung korrigieren" if item.current_validation is not None else "Validierung speichern")
        if comparison:
            self._choices.grid()
        else:
            self._choices.grid_remove()
        if comparison:
            for field in comparison.fields:
                row = self._fields.insert("", "end", values=(self._field_label(field), field.old_value or "(leer)", field.new_value or "(leer)"), tags=("changed",) if field.changed else ())
                self._field_keys_by_row[row] = field.field_key
                self._field_labels_by_row[row] = self._field_label(field)
            for field in comparison.metadata:
                row = self._fields.insert("", "end", values=("Nachweis: " + field.field_key, field.old_value or "-", field.new_value or "-"), tags=("metadata",))
                self._field_keys_by_row[row] = field.field_key
                self._field_labels_by_row[row] = "Nachweis: " + field.field_key
        else:
            for field in item.fields:
                row = self._fields.insert("", "end", values=(self._field_label(field), field.value if field.value != "" else "(leer)", ""))
                self._field_keys_by_row[row] = field.field_key
                self._field_labels_by_row[row] = self._field_label(field)
        for event in item.reanalysis_history:
            self._history.insert("", "end", values=(event.field_key, "", "", event.value))
        for values in validation_history_rows(item):
            self._history.insert("", "end", values=values)
        available = not item.validation_ambiguous and not item.revision_error and not item.activation_blocked_reason and not self._reanalysis_busy
        self._btn_save.configure(state="normal" if available and not comparison and not item.missing_fields else "disabled")
        self._btn_reanalyze.configure(state="normal" if available else "disabled")
        self._btn_keep_old.configure(state="normal" if available and comparison and comparison.can_keep_old else "disabled")
        self._btn_accept_new.configure(state="normal" if available and comparison and comparison.can_accept_new else "disabled")
        self._btn_edit_rules.configure(state="normal" if available else "disabled")
        self._btn_open_pdf.configure(state="normal")
        self._layout_workflow_text()
        self._layout_case_actions()
        self._resize_value_columns()
