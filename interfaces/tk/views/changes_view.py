from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

from interfaces.tk.widgets.common import Card, EmptyState, MultiSelectFilter, ScrollableFrame, StatusBadge, create_scrollable_tree


class ChangesView(ttk.Frame):
    """Real store-bound ID cases, using only immutable application items."""

    def __init__(self, master, *, on_refresh, on_confirm, on_open_editor, on_open_pdf, on_retry, on_find_pdf=None):
        super().__init__(master, style="Content.TFrame")
        self._on_refresh, self._on_confirm = on_refresh, on_confirm
        self._on_open_editor, self._on_open_pdf, self._on_retry = on_open_editor, on_open_pdf, on_retry
        self._on_find_pdf = on_find_pdf or (lambda: None)
        self._items, self._by_id, self._store_path = (), {}, ""
        self._selected_id, self._source_id, self._selection_generation = "", "", 0
        self._busy, self._layout_id, self._compact = False, None, None
        self._configure_styles()
        self._build()

    def _configure_styles(self):
        style = ttk.Style(self)
        style.configure("Changes.TButton", font=("Segoe UI", 9), padding=(9, 6), background="#ffffff", foreground="#21486f", bordercolor="#cbdbea", lightcolor="#ffffff", darkcolor="#ffffff", relief="solid", borderwidth=1)
        style.map("Changes.TButton", background=[("active", "#eef5fd")], foreground=[("disabled", "#8b9bad")])
        style.configure("Changes.Primary.TButton", font=("Segoe UI", 9, "bold"), padding=(10, 7))
        style.configure("Changes.Title.TLabel", font=("Segoe UI", 12, "bold"), foreground="#16293c", background="#ffffff")
        style.configure("Changes.Muted.TLabel", font=("Segoe UI", 9), foreground="#53677a", background="#ffffff")
        style.configure("Changes.Treeview", rowheight=40, font=("Segoe UI", 9), bordercolor="#dbe4ed")
        style.configure("Changes.Treeview.Heading", font=("Segoe UI", 9, "bold"), padding=(7, 6), background="#f0f5fb")
        style.map("Changes.Treeview", background=[("selected", "#eaf3fd")], foreground=[("selected", "#175ba4")])

    def _build(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self._header = ttk.Frame(self, style="Content.TFrame", padding=(12, 10, 12, 12))
        self._header.grid(row=0, column=0, sticky="ew")
        self._eyebrow = ttk.Label(self._header, text="ASSAY-KENNUNGEN", style="Eyebrow.TLabel")
        self._eyebrow.pack(anchor="w")
        self._title = ttk.Label(self._header, text="Änderungen", style="PageTitle.TLabel")
        self._title.pack(anchor="w", pady=(4, 2))
        self._subtitle = ttk.Label(self._header, text="Neue Herstellerkennungen bewusst zuordnen und betroffene Berichte erneut verarbeiten.", style="PageSubtitle.TLabel")
        self._subtitle.pack(anchor="w")
        self._page = ScrollableFrame(self, autohide=True)
        self._page.grid(row=1, column=0, sticky="nsew")
        self._page.body.configure(style="Content.TFrame")
        self._page._canvas.configure(background="#f3f6fa")
        self._left = Card(self._page.body, rounded=True, padding=16)
        self._right = Card(self._page.body, rounded=True, padding=16)
        self._build_list(self._left.body)
        self._build_detail(self._right.body)
        self.bind("<Configure>", self._schedule_layout)
        self.bind("<Destroy>", self._cancel_layout)
        self._render_detail()

    def _tree(self, parent, columns, titles, height):
        frame, tree = create_scrollable_tree(parent, columns, titles, height=height, autohide=True)
        tree.configure(style="Changes.Treeview")
        for column in columns:
            tree.heading(column, anchor="w")
        tree.bind("<Configure>", self._schedule_layout)
        return frame, tree

    def _build_list(self, body):
        ttk.Label(body, text="Kennungsfälle", style="Changes.Title.TLabel").pack(anchor="w")
        self._count = ttk.Label(body, text="Fälle werden geladen …", style="Changes.Muted.TLabel")
        self._count.pack(anchor="w", pady=(4, 12))
        toolbar = ttk.Frame(body, style="CardInner.TFrame")
        toolbar.pack(fill="x", pady=(0, 10))
        self.status_filter = MultiSelectFilter(toolbar, "Status", on_change=self._apply_filters)
        self.status_filter.pack(side="left")
        self.btn_clear_filters = ttk.Button(toolbar, text="Filter löschen", command=lambda: self.status_filter.select_values(()), style="Changes.TButton")
        self.btn_clear_filters.pack(side="left", padx=7)
        self.btn_refresh = ttk.Button(body, text="Aktualisieren", command=self._on_refresh, style="Changes.TButton")
        self.btn_refresh.pack(anchor="e", pady=(0, 10))
        self._list_frame, self.tree_cases = self._tree(body, ("assay", "key", "pdfs", "status"), ("Assay", "Neue ID", "PDFs", "Status"), 3)
        self._list_frame.pack(fill="x")
        self.tree_cases.bind("<<TreeviewSelect>>", self._select_case)
        self._empty = EmptyState(body, "Keine Kennungsfälle in dieser Auswahl.", hint="Nur tatsächlich beobachtete neue Herstellerkennungen.")

    def _build_detail(self, body):
        heading = ttk.Frame(body, style="CardInner.TFrame")
        heading.pack(fill="x")
        heading.columnconfigure(0, weight=1)
        self._detail_title = ttk.Label(heading, text="Kennungsfall auswählen", style="Changes.Title.TLabel")
        self._detail_title.grid(row=0, column=0, sticky="w")
        self._badge = StatusBadge(heading)
        self._badge.grid(row=0, column=1, sticky="ne", padx=(8, 0))
        self._detail_body = ttk.Frame(body, style="CardInner.TFrame")
        self._detail_body.pack(fill="x", pady=(9, 0))
        context = ttk.Frame(self._detail_body, style="CardInner.TFrame")
        context.pack(fill="x", pady=(0, 10))
        context.columnconfigure(0, weight=1, uniform="identity")
        context.columnconfigure(1, weight=1, uniform="identity")
        for column, title in enumerate(("Bisherige Kennung(en)", "Beobachtete Kennung")):
            ttk.Label(context, text=title, style="Changes.Muted.TLabel").grid(row=0, column=column, sticky="w", padx=(0 if not column else 10, 0))
        self._old_keys = ttk.Label(context, style="Changes.Title.TLabel")
        self._old_keys.grid(row=1, column=0, sticky="w", pady=(3, 0))
        self._new_key = ttk.Label(context, style="Changes.Title.TLabel")
        self._new_key.grid(row=1, column=1, sticky="w", padx=(10, 0), pady=(3, 0))
        self._hint = ttk.Label(self._detail_body, style="Changes.Muted.TLabel", text="Der Name ist nur ein Hinweis – keine automatische Zuordnung und kein Alias.")
        self._hint.pack(fill="x", pady=(0, 12))
        ttk.Label(self._detail_body, text="Betroffene PDFs", style="Changes.Title.TLabel").pack(anchor="w", pady=(0, 6))
        self._source_frame, self.tree_sources = self._tree(self._detail_body, ("file", "status"), ("Datei", "Verarbeitung"), 2)
        self._source_frame.pack(fill="x")
        self.tree_sources.bind("<<TreeviewSelect>>", self._select_source)
        self.tree_sources.bind("<Double-1>", lambda _e: self._on_open_pdf() if self.selected_source() and self.selected_source().available else None)
        self._source_context = ttk.Label(self._detail_body, style="Changes.Muted.TLabel")
        self._source_context.pack(fill="x", pady=(6, 7))
        pdf_actions = ttk.Frame(self._detail_body, style="CardInner.TFrame")
        pdf_actions.pack(fill="x", pady=(0, 14))
        self.btn_open_pdf = ttk.Button(pdf_actions, text="PDF öffnen", command=self._on_open_pdf, style="Changes.TButton")
        self.btn_open_pdf.pack(side="left")
        self.btn_find_pdf = ttk.Button(pdf_actions, text="PDF wiederfinden", command=self._on_find_pdf, style="Changes.TButton")
        self.btn_find_pdf.pack(side="left", padx=(8, 0))
        self._assignment = ttk.Frame(self._detail_body, style="CardInner.TFrame")
        ttk.Label(self._assignment, text="Bekannten Assay ausdrücklich zuordnen", style="Changes.Title.TLabel").pack(anchor="w", pady=(0, 6))
        self._candidate_var = tk.StringVar(self)
        self._candidate_choice = ""
        self._candidate_var.trace_add("write", self._candidate_changed)
        self.candidate_combo = ttk.Combobox(self._assignment, textvariable=self._candidate_var, state="readonly")
        self.candidate_combo.pack(fill="x", pady=(0, 9))
        self.candidate_combo.bind("<<ComboboxSelected>>", lambda _e: self._sync_actions())
        self.btn_confirm_copy = ttk.Button(self._assignment, text="Zuordnen · Kopie anlegen", command=lambda: self._on_confirm("copy"), style="Changes.Primary.TButton")
        self.btn_confirm_copy.pack(anchor="w", pady=(0, 7))
        self.btn_confirm_blank = ttk.Button(self._assignment, text="Zuordnen · leer beginnen", command=lambda: self._on_confirm("blank"), style="Changes.TButton")
        self.btn_confirm_blank.pack(anchor="w")
        self.btn_open_draft = ttk.Button(self._detail_body, text="Entwurf im Regelarbeitsplatz öffnen", command=self._on_open_editor, style="Changes.Primary.TButton")
        self.btn_retry = ttk.Button(self._detail_body, text="Betroffene PDFs erneut verarbeiten", command=self._on_retry, style="Changes.Primary.TButton")
        self._workflow_hint = ttk.Label(self._detail_body, style="Changes.Muted.TLabel")
        self._workflow_hint.pack(fill="x", pady=(10, 0))
        self._feedback = ttk.Label(body, style="Changes.Muted.TLabel")
        self._feedback.pack(fill="x", pady=(8, 0))

    def render_cases(self, items, *, store_path):
        if self._store_path and self._store_path.casefold() != store_path.casefold():
            self.invalidate_store_context()
        self._store_path = store_path
        self._items = tuple(item for item in items if item.store_path.casefold() == store_path.casefold())
        self._by_id = {item.case_id: item for item in self._items}
        self.status_filter.set_options(item.status for item in self._items)
        self._apply_filters()

    def _apply_filters(self):
        visible = [item for item in self._items if not self.status_filter.selected_values or item.status in self.status_filter.selected_values]
        selected = self._selected_id if self._selected_id in {item.case_id for item in visible} else (visible[0].case_id if visible else "")
        self.tree_cases.delete(*self.tree_cases.get_children())
        for item in visible:
            self.tree_cases.insert("", "end", iid=item.case_id, values=(item.assay_name, item.assay_key, len(item.sources), "Aktiv · offen" if item.can_retry else item.status))
        self._count.configure(text=f"{len(visible)} {'Fall' if len(visible) == 1 else 'Fälle'} in dieser Auswahl")
        self.tree_cases.configure(height=max(1, min(5, len(visible))))
        self._empty.pack_forget()
        self._list_frame.pack_forget()
        if visible:
            self._list_frame.pack(fill="x")
            self.tree_cases.selection_set(selected)
            self.tree_cases.focus(selected)
        else:
            self._empty.pack(fill="x", pady=(7, 0))
        if selected != self._selected_id:
            self._selection_generation += 1
            self._source_id = ""
        self._selected_id = selected
        self._render_detail()
        self._schedule_layout()

    def _select_case(self, _event=None):
        selected = next(iter(self.tree_cases.selection()), "")
        if selected != self._selected_id:
            self._selected_id, self._source_id = selected, ""
            self._selection_generation += 1
            self._feedback.configure(text="")
            self._render_detail()

    def _render_detail(self):
        item = self.selected_case()
        if item is None:
            self._detail_title.configure(text="Kennungsfall auswählen")
            self._badge.set_status("")
            self._detail_body.pack_forget()
            return
        self._detail_body.pack(fill="x", pady=(9, 0), before=self._feedback)
        self._detail_title.configure(text=item.assay_name)
        self._badge.set_status(item.status, kind="good" if item.completed else "warning")
        self._old_keys.configure(text=", ".join(row.assay_key for row in item.candidates))
        self._new_key.configure(text=item.assay_key)
        self.tree_sources.delete(*self.tree_sources.get_children())
        for source in item.sources:
            self.tree_sources.insert("", "end", iid=source.source_id, values=(source.file_name, source.status))
        self.tree_sources.configure(height=max(1, min(4, len(item.sources))))
        if self._source_id not in {source.source_id for source in item.sources}:
            self._selection_generation += 1
            self._source_id = next((source.source_id for source in item.sources if not source.done), item.sources[0].source_id if item.sources else "")
        if self._source_id:
            self.tree_sources.selection_set(self._source_id)
        choices = [f"{row.assay_name} · {row.assay_key}" for row in item.candidates]
        self.candidate_combo.configure(values=choices)
        selected = next((index for index, row in enumerate(item.candidates) if row.assay_key == item.source_assay_key), 0 if len(choices) == 1 else None)
        self._candidate_var.set(choices[selected] if selected is not None else "")
        for widget in (self._assignment, self.btn_open_draft, self.btn_retry):
            widget.pack_forget()
        if item.can_retry:
            self.btn_retry.pack(anchor="w", pady=(0, 8), before=self._workflow_hint)
        if item.draft_path:
            self.btn_open_draft.pack(anchor="w", pady=(0, 8), before=self._workflow_hint)
        elif not item.completed:
            self._assignment.pack(fill="x", before=self._workflow_hint)
        hint = "Alle betroffenen Importaufträge wurden erfolgreich verarbeitet." if item.completed else "Regel aktiv. Noch offene Berichte hier gezielt erneut verarbeiten." if item.can_retry else "Eigenes Regelwerk anlegen, mit einer Test-PDF prüfen und ausdrücklich aktivieren."
        self._workflow_hint.configure(text=hint)
        self._select_source()
        self._sync_actions()
        self._schedule_layout()

    def _select_source(self, _event=None):
        selected = next(iter(self.tree_sources.selection()), "")
        if selected != self._source_id:
            self._source_id = selected
            self._selection_generation += 1
        source = self.selected_source()
        self._source_context.configure(text=f"{source.file_name}\n{source.message or source.status}" if source else "")
        self._sync_actions()

    def selected_case(self):
        return self._by_id.get(self._selected_id)

    def selected_source(self):
        item = self.selected_case()
        return next((source for source in item.sources if source.source_id == self._source_id), None) if item else None

    def selected_candidate(self):
        item = self.selected_case()
        return next((row for row in item.candidates if f"{row.assay_name} · {row.assay_key}" == self._candidate_choice), None) if item else None

    def _candidate_changed(self, *_args):
        value = self._candidate_var.get()
        if value != self._candidate_choice:
            self._candidate_choice = value
            self._selection_generation += 1
        self._sync_actions()

    def selection_context(self):
        return self._selection_generation, self._selected_id, self._source_id, self._store_path, self._candidate_choice

    def set_busy(self, busy):
        self._busy = busy
        self._sync_actions()

    def set_feedback(self, text):
        self._feedback.configure(text=text)

    def _sync_actions(self):
        if not hasattr(self, "btn_retry"):
            return
        item, source, candidate = self.selected_case(), self.selected_source(), self.selected_candidate()
        self.btn_refresh.configure(state="disabled" if self._busy else "normal")
        self.candidate_combo.configure(state="disabled" if self._busy else "readonly")
        for button in (self.btn_confirm_copy, self.btn_confirm_blank):
            button.configure(state="normal" if item and candidate and not self._busy else "disabled")
        self.btn_open_draft.configure(state="normal" if item and item.draft_path and not self._busy else "disabled")
        self.btn_open_pdf.configure(state="normal" if source and source.available and not self._busy else "disabled")
        self.btn_find_pdf.configure(state="normal" if source and not self._busy else "disabled")
        self.btn_retry.configure(state="normal" if item and item.can_retry and not self._busy else "disabled")

    def invalidate_store_context(self):
        self._selection_generation += 1
        self._items, self._by_id, self._store_path = (), {}, ""
        self._selected_id, self._source_id = "", ""
        self._apply_filters()
        self._feedback.configure(text="Ergebnisspeicher gewechselt. Bitte neu laden.")

    def _schedule_layout(self, _event=None):
        if self._layout_id is None:
            self._layout_id = self.after_idle(self._layout)

    def _layout(self):
        self._layout_id = None
        width = self.winfo_width()
        if width < 20:
            return
        compact = width < 880
        if compact != self._compact:
            self._compact = compact
            self._left.grid_forget()
            self._right.grid_forget()
            self._page.body.columnconfigure(0, weight=1, uniform="" if compact else "changes_cards")
            self._page.body.columnconfigure(1, weight=0 if compact else 1, uniform="" if compact else "changes_cards")
            self._left.grid(row=0, column=0, sticky="new", padx=(12, 12 if compact else 7), pady=(0, 12))
            self._right.grid(row=1 if compact else 0, column=0 if compact else 1, sticky="new", padx=(12 if compact else 7, 12), pady=(0, 4))
            self._header.configure(padding=(12, 3 if compact else 10, 12, 8 if compact else 12))
            if compact:
                self._eyebrow.pack_forget()
            else:
                self._eyebrow.pack(anchor="w", before=self._title)
        self._subtitle.configure(wraplength=max(200, width - 30))
        detail_width = max(220, self._right.body.winfo_width() - 8)
        for label in (self._hint, self._source_context, self._workflow_hint, self._feedback, self._detail_title):
            label.configure(wraplength=detail_width)
        font = tkfont.nametofont("TkDefaultFont")
        for tree, columns, shares in ((self.tree_cases, ("assay", "key", "pdfs", "status"), (.50, .14, .10, .26)), (self.tree_sources, ("file", "status"), (.74, .26))):
            available = tree.winfo_width() - 4
            if available > 30:
                minima = [font.measure(str(tree.heading(column, "text"))) + 20 for column in columns]
                remainder = max(0, available - sum(minima))
                for column, minimum, share in zip(columns, minima, shares):
                    tree.column(column, width=int(minimum + remainder * share), minwidth=minimum, stretch=False)
        self._page._schedule_content_refresh()

    def _cancel_layout(self, event):
        if event.widget is self and self._layout_id is not None:
            self.after_cancel(self._layout_id)
            self._layout_id = None
