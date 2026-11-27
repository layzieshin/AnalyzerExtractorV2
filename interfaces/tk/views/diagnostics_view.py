from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from collections.abc import Callable, Sequence
from tkinter import ttk

from interfaces.tk.view_models import format_assay_candidate_lines, format_timestamp
from interfaces.tk.scroll_helpers import bind_mousewheel
from interfaces.tk.widgets.common import Card, EmptyState, ScrollableFrame, create_scrollable_tree
from src.application.api import AssayCandidateItem, DuplicateCandidateItem, JobDiagnosisItem


class DiagnosticsView(ttk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        *,
        on_refresh: Callable[[], None],
        on_show_diagnosis: Callable[[], None],
        on_retry_job: Callable[[], None],
        on_create_draft: Callable[[], None],
        on_show_duplicate: Callable[[], None],
        on_discard_duplicate: Callable[[], None],
    ) -> None:
        super().__init__(master, style="Content.TFrame")
        self._on_refresh = on_refresh
        self._on_show_diagnosis = on_show_diagnosis
        self._on_retry_job = on_retry_job
        self._on_create_draft = on_create_draft
        self._on_show_duplicate = on_show_duplicate
        self._on_discard_duplicate = on_discard_duplicate
        self._candidates_by_id: dict[str, AssayCandidateItem] = {}
        self._diagnoses_by_job: dict[str, JobDiagnosisItem] = {}
        self._duplicates_by_id: dict[str, DuplicateCandidateItem] = {}
        self._candidate_job_id = ""
        self._diagnosis_selection_id = ""
        self._diagnosis_selection_generation = 0
        self._duplicate_store_path = ""
        self._duplicate_selection_id = None
        self._duplicate_selection_store = ""
        self._duplicate_selection_generation = 0
        self._layout_after_id = None
        self._compact = None
        self._configure_styles()
        self._build()

    def _configure_styles(self) -> None:
        style = ttk.Style(self)
        style.configure("Diagnostics.TButton", font=("Segoe UI", 9), padding=(8, 5), background="#ffffff",
            foreground="#21486f", bordercolor="#cbdbea", lightcolor="#ffffff", darkcolor="#ffffff", borderwidth=1, relief="solid")
        style.map("Diagnostics.TButton", background=[("active", "#eef5fd")], foreground=[("disabled", "#8b9bad")], bordercolor=[("focus", "#8bb2df")])
        style.configure("Diagnostics.Primary.TButton", font=("Segoe UI", 9, "bold"), padding=(10, 5))
        style.configure("Danger.Diagnostics.TButton", foreground="#a94444", bordercolor="#e5cbcb")
        style.map("Danger.Diagnostics.TButton", foreground=[("disabled", "#aab3be"), ("active", "#8c2929")], background=[("active", "#fff3f3")])
        style.configure("Diagnostics.Muted.TLabel", font=("Segoe UI", 9), background="#ffffff", foreground="#53677a")
        style.configure("Diagnostics.Title.TLabel", font=("Segoe UI", 12, "bold"), background="#ffffff", foreground="#16293c")
        style.configure("Diagnostics.Treeview", rowheight=38, font=("Segoe UI", 9), bordercolor="#dbe4ed")
        style.configure("Diagnostics.Treeview.Heading", font=("Segoe UI", 9, "bold"), padding=(8, 6), background="#f0f5fb")
        style.map("Diagnostics.Treeview", background=[("selected", "#eaf3fd")], foreground=[("selected", "#175ba4")])

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self._page_header = ttk.Frame(self, style="Content.TFrame", padding=(12, 12, 12, 10))
        self._page_header.grid(row=0, column=0, sticky="ew")
        self._eyebrow = ttk.Label(self._page_header, text="WEITERE", style="Eyebrow.TLabel")
        self._eyebrow.pack(anchor="w")
        self._page_title = ttk.Label(self._page_header, text="Diagnose", style="PageTitle.TLabel")
        self._page_title.pack(anchor="w", pady=(4, 2))
        self._page_subtitle = ttk.Label(self._page_header, text="Technische Fehler und Klärfälle zu doppelten Importen.", style="PageSubtitle.TLabel")
        self._page_subtitle.pack(anchor="w")
        self._page = ScrollableFrame(self, autohide=True)
        self._page.grid(row=1, column=0, sticky="nsew", pady=(0, 12))
        self._page.body.configure(style="Content.TFrame")
        self._page._canvas.configure(background="#f3f6fa", takefocus=True)
        self._diag_card = Card(self._page.body, padding=16, rounded=True)
        self._diag_card.pack(fill="x", padx=12, pady=(0, 12))
        self._build_diagnoses(self._diag_card.body)
        self._dup_card = Card(self._page.body, padding=16, rounded=True)
        self._dup_card.pack(fill="x", padx=12, pady=(0, 12))
        self._build_duplicates(self._dup_card.body)
        for tree in (self._diag_tree, self._candidate_tree, self._dup_tree):
            tree.configure(style="Diagnostics.Treeview")
            for column in tree.cget("columns"):
                tree.heading(column, anchor="w")
            tree.bind("<Configure>", self._schedule_layout)
        self._bind_page_scroll(self._page)
        self.bind("<Configure>", self._schedule_layout)
        self.bind("<Destroy>", self._cancel_layout)
        self._schedule_layout()

    def _build_diagnoses(self, dbody: ttk.Frame) -> None:
        heading = ttk.Frame(dbody, style="CardInner.TFrame")
        self._diag_heading = heading
        heading.pack(fill="x", pady=(0, 10))
        heading.columnconfigure(0, weight=1)
        self._diag_title = ttk.Label(heading, text="Fehlgeschlagene Verarbeitungen", style="Diagnostics.Title.TLabel")
        self._diag_title.grid(row=0, column=0, sticky="w")
        self._diag_count = ttk.Label(heading, text="Diagnose wird geladen …", style="Diagnostics.Muted.TLabel")
        self._diag_count.grid(row=1, column=0, sticky="w", pady=(3, 0))
        self._btn_refresh = ttk.Button(heading, text="Aktualisieren", command=self._on_refresh, style="Diagnostics.TButton")
        self._btn_refresh.grid(row=0, column=1, rowspan=2, sticky="ne", padx=(10, 0))
        self._diag_frame, self._diag_tree = create_scrollable_tree(dbody, ("file", "error", "message"), ("Datei", "Fehlerart", "Hinweis"), height=1, autohide=True)
        self._diag_empty = EmptyState(dbody, "Keine fehlgeschlagenen Jobs.")
        self._diag_context = ttk.Label(dbody, text="", style="Diagnostics.Muted.TLabel", wraplength=700)
        self._diag_actions = ttk.Frame(dbody, style="CardInner.TFrame")
        self._diag_actions.pack(fill="x")
        self._btn_details = ttk.Button(self._diag_actions, text="Details", command=self._on_show_diagnosis, style="Diagnostics.TButton", state="disabled")
        self._btn_details.pack(side="left")
        self._btn_retry = ttk.Button(self._diag_actions, text="Erneut versuchen", command=self._on_retry_job, state="disabled", style="Diagnostics.TButton")
        self._btn_retry.pack(side="left", padx=(8, 0))
        self._diag_tree.bind("<<TreeviewSelect>>", self._handle_job_selection)
        self._diag_tree.bind("<Double-1>", lambda _event: self._on_show_diagnosis() if self.selected_job_id() else None)
        self._candidate_panel = ttk.Frame(dbody, style="CardInner.TFrame")
        ttk.Label(self._candidate_panel, text="Assay-Kandidaten", style="Diagnostics.Title.TLabel").pack(anchor="w", pady=(12, 8))
        self._candidate_frame, self._candidate_tree = create_scrollable_tree(self._candidate_panel, ("assay", "name", "status", "confidence"),
            ("Assay", "Namenshinweis", "Status", "Konfidenz"), height=1, autohide=True)
        self._candidate_frame.pack(fill="x", pady=(0, 8))
        self._candidate_tree.bind("<<TreeviewSelect>>", lambda _event: self._btn_draft.configure(state="normal" if self.selected_candidate() else "disabled"))
        self._btn_draft = ttk.Button(self._candidate_panel, text="Entwurf aus Kandidat", command=self._on_create_draft, style="Diagnostics.TButton", state="disabled")
        self._btn_draft.pack(anchor="w", pady=(0, 8))
        self._lbl_context = ttk.Label(self._candidate_panel, text="", style="Diagnostics.Muted.TLabel", wraplength=700)
        self._lbl_context.pack(anchor="w")

    def _build_duplicates(self, dup_body: ttk.Frame) -> None:
        ttk.Label(dup_body, text="Duplikatvergleich", style="Diagnostics.Title.TLabel").pack(anchor="w")
        self._dup_hint = ttk.Label(dup_body, text="Ein doppelter Import wird mit der ausgewählten Ergebnisfassung verglichen.", style="Diagnostics.Muted.TLabel", wraplength=700)
        self._dup_hint.pack(anchor="w", pady=(4, 10))
        self._dup_frame, self._dup_tree = create_scrollable_tree(dup_body, ("assay", "status", "detected"), ("Assay", "Status", "Erkannt"), height=1, autohide=True)
        self._dup_tree.configure(displaycolumns=("assay", "detected", "status"))
        self._dup_empty = EmptyState(dup_body, "Keine ausstehenden Klärfälle.")
        self._dup_actions = ttk.Frame(dup_body, style="CardInner.TFrame")
        self._dup_actions.pack(fill="x")
        self._btn_compare = ttk.Button(self._dup_actions, text="Vergleichen", command=self._on_show_duplicate, style="Diagnostics.Primary.TButton", state="disabled")
        self._btn_compare.pack(side="left")
        self._btn_discard = ttk.Button(self._dup_actions, text="Verwerfen", command=self._on_discard_duplicate, style="Danger.Diagnostics.TButton", state="disabled")
        self._btn_discard.pack(side="left", padx=(8, 0))
        self._dup_tree.bind("<<TreeviewSelect>>", self._handle_duplicate_selection)
        self._dup_tree.bind("<Double-1>", lambda _event: self._on_show_duplicate() if self.selected_duplicate_id() is not None else None)

    def _bind_page_scroll(self, widget) -> None:
        if isinstance(widget, ttk.Treeview):
            return
        bind_mousewheel(widget, self._page._canvas)
        for child in widget.winfo_children():
            self._bind_page_scroll(child)

    def _schedule_layout(self, _event=None) -> None:
        if self._layout_after_id is None:
            self._layout_after_id = self.after_idle(self._layout_diagnostics)

    def _cancel_layout(self, event) -> None:
        if event.widget is self and self._layout_after_id is not None:
            self.after_cancel(self._layout_after_id)
            self._layout_after_id = None

    def _layout_diagnostics(self) -> None:
        self._layout_after_id = None
        width = self.winfo_width() - 56
        if width < 40:
            return
        compact = width < 900
        if compact != self._compact:
            self._page_header.configure(padding=(12, 4, 12, 6) if compact else (12, 12, 12, 10))
            self._page_title.configure(style="CompactPageTitle.TLabel" if compact else "PageTitle.TLabel")
            self._page_title.pack_configure(pady=(0, 2) if compact else (4, 2))
            if compact:
                self._eyebrow.pack_forget()
            else:
                self._eyebrow.pack(anchor="w", before=self._page_title)
            for card in (self._diag_card, self._dup_card):
                card.body.configure(padding=0 if compact else 4)
                card.pack_configure(pady=(0, (0 if card is self._dup_card else 8) if compact else 12))
            self._diag_heading.pack_configure(pady=(0, 6 if compact else 10))
            self._dup_hint.pack_configure(pady=(4, 6 if compact else 10))
            ttk.Style(self).configure("Diagnostics.Treeview", rowheight=32 if compact else 38)
            self._compact = compact
        for frame in (self._diag_frame, self._dup_frame):
            if frame.winfo_manager():
                frame.pack_configure(pady=(0, 6 if compact else 10))
        self._page_subtitle.configure(wraplength=width)
        self._diag_title.configure(wraplength=max(180, width - self._btn_refresh.winfo_reqwidth() - 16))
        for label in (self._diag_context, self._lbl_context, self._dup_hint):
            label.configure(wraplength=width)
        heading_font = tkfont.Font(self, font=ttk.Style(self).lookup("Diagnostics.Treeview.Heading", "font"))
        cell_font = tkfont.Font(self, font=ttk.Style(self).lookup("Diagnostics.Treeview", "font"))
        for tree, flexible in ((self._diag_tree, "message"), (self._candidate_tree, "assay"), (self._dup_tree, "assay")):
            if tree.winfo_width() < 10:
                continue
            columns = tuple(tree.cget("columns"))
            rows = [tree.item(row, "values") for row in tree.get_children()]
            minima = {column: heading_font.measure(tree.heading(column, "text")) + 24 for column in columns}
            desired = {column: max(minima[column], min(360 if column == flexible else 240,
                max((cell_font.measure(str(row[index])) + 24 for row in rows), default=0))) for index, column in enumerate(columns)}
            available = tree.winfo_width() - 4
            if sum(desired.values()) > available:
                desired[flexible] = max(minima[flexible], desired[flexible] - (sum(desired.values()) - available))
            extra = max(0, available - sum(desired.values()))
            for index, column in enumerate(columns):
                growth = extra // len(columns) + (extra % len(columns) if index == 0 else 0)
                desired[column] += growth
                tree.column(column, width=desired[column], minwidth=desired[column], stretch=column == flexible)

    def selected_job_id(self) -> str:
        selection = self._diag_tree.selection()
        return str(selection[0]) if selection else ""

    def _on_diagnosis_selected(self, _event: object = None) -> None:
        item = self._diagnoses_by_job.get(self.selected_job_id())
        retryable = item is not None and item.queue_status == "FAILED" and item.retry_kind == "full_processing"
        self._btn_retry.configure(state="normal" if retryable else "disabled")

    def _handle_job_selection(self, _event: object = None) -> None:
        selected = self.selected_job_id()
        if selected != self._diagnosis_selection_id:
            self._diagnosis_selection_id = selected
            self._diagnosis_selection_generation += 1
        self._on_diagnosis_selected()
        item = self._diagnoses_by_job.get(self.selected_job_id())
        self._btn_details.configure(state="normal" if item is not None else "disabled")
        if self._candidate_job_id != self.selected_job_id():
            self.render_candidates(())
        if item is not None:
            self._diag_context.configure(text=f"{item.file_name} · {item.error_label} · {self._diagnosis_hint(item)}")
            self._diag_context.pack(fill="x", pady=(0, 10), before=self._diag_actions)
        else:
            self._diag_context.pack_forget()
        self._schedule_layout()

    def _handle_duplicate_selection(self, _event: object = None) -> None:
        identifier = self.selected_duplicate_id()
        if (identifier, self._duplicate_store_path) != (self._duplicate_selection_id, self._duplicate_selection_store):
            self._duplicate_selection_id, self._duplicate_selection_store = identifier, self._duplicate_store_path
            self._duplicate_selection_generation += 1
        selected = self._dup_tree.selection()
        item = self._duplicates_by_id.get(str(selected[0])) if selected else None
        self._btn_compare.configure(state="normal" if item is not None and self._duplicate_store_path else "disabled")
        self._btn_discard.configure(state="normal" if item is not None and item.status == "pending" and self._duplicate_store_path else "disabled")

    def diagnosis_selection_context(self) -> tuple[str, int]:
        return self._diagnosis_selection_id, self._diagnosis_selection_generation

    def duplicate_selection_context(self) -> tuple[int | None, str, int]:
        return self._duplicate_selection_id, self._duplicate_selection_store, self._duplicate_selection_generation

    def selected_duplicate_descriptor(self) -> tuple[int, str, int] | None:
        candidate_id, store, generation = self.duplicate_selection_context()
        if candidate_id is None or not store or candidate_id != self.selected_duplicate_id():
            return None
        return candidate_id, store, generation

    def invalidate_store_context(self) -> None:
        self.render_duplicates((), store_path="")
        self.render_candidates(())

    @staticmethod
    def _diagnosis_hint(item: JobDiagnosisItem) -> str:
        message = item.friendly_message or item.technical_detail
        if message.strip().casefold() == item.error_label.strip().casefold():
            return f"Kontext: {item.context_label}" if item.context_label else "Details ansehen"
        return message

    def selected_candidate(self) -> AssayCandidateItem | None:
        selection = self._candidate_tree.selection()
        if not selection:
            return None
        return self._candidates_by_id.get(str(selection[0]))

    def selected_duplicate_id(self) -> int | None:
        selection = self._dup_tree.selection()
        if not selection:
            return None
        try:
            return int(str(selection[0]))
        except ValueError:
            return None

    def render_diagnoses(self, items: Sequence[JobDiagnosisItem]) -> None:
        previous = self.selected_job_id()
        self._diagnoses_by_job = {item.job_id: item for item in items}
        for row in self._diag_tree.get_children():
            self._diag_tree.delete(row)
        if not items:
            self._diag_frame.pack_forget()
            self._diag_empty.pack(anchor="w", pady=(0, 10), before=self._diag_actions)
            self._diag_count.configure(text="Keine technischen Fälle")
            self._handle_job_selection()
            return
        self._diag_empty.pack_forget()
        self._diag_frame.pack(fill="x", pady=(0, 10), before=self._diag_actions)
        self._diag_tree.configure(height=min(5, len(items)))
        self._diag_count.configure(text=f"{len(items)} {'technischer Eintrag' if len(items) == 1 else 'technische Einträge'}")
        for item in items:
            self._diag_tree.insert(
                "",
                "end",
                iid=item.job_id,
                values=(item.file_name, item.error_label, self._diagnosis_hint(item)),
            )
        if previous and self._diag_tree.exists(previous):
            self._diag_tree.selection_set(previous)
            self._diag_tree.focus(previous)
        self._handle_job_selection()

    def render_candidates(self, candidates: Sequence[AssayCandidateItem]) -> None:
        self._candidate_job_id = self.selected_job_id()
        for row in self._candidate_tree.get_children():
            self._candidate_tree.delete(row)
        self._candidates_by_id.clear()
        self._btn_draft.configure(state="disabled")
        if candidates:
            self._candidate_panel.pack(fill="x")
            self._candidate_tree.configure(height=min(4, len(candidates)))
        else:
            self._candidate_panel.pack_forget()
        for index, candidate in enumerate(candidates):
            iid = candidate.candidate_id or f"{candidate.assay_key}::{index}"
            self._candidates_by_id[iid] = candidate
            self._candidate_tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    candidate.assay_name or "Assayname fehlt",
                    candidate.assay_name_hint,
                    candidate.known_status,
                    candidate.confidence,
                ),
            )
        self._lbl_context.configure(text="\n".join(format_assay_candidate_lines(candidates)))
        self._schedule_layout()

    def render_duplicates(self, items: Sequence[DuplicateCandidateItem], *, store_path: str = "") -> None:
        previous = self.selected_duplicate_id() if store_path == self._duplicate_store_path else None
        self._duplicate_store_path = store_path
        self._duplicates_by_id = {str(item.candidate_id): item for item in items}
        for row in self._dup_tree.get_children():
            self._dup_tree.delete(row)
        if not items:
            self._dup_frame.pack_forget()
            self._dup_empty.pack(anchor="w", pady=(0, 10), before=self._dup_actions)
            self._handle_duplicate_selection()
            self._schedule_layout()
            return
        self._dup_empty.pack_forget()
        self._dup_frame.pack(fill="x", pady=(0, 10), before=self._dup_actions)
        self._dup_tree.configure(height=min(5, len(items)))
        for item in items:
            self._dup_tree.insert(
                "",
                "end",
                iid=str(item.candidate_id),
                values=(item.assay_name or "Assayname fehlt", {"pending": "Offen", "deleted": "Verworfen"}.get(item.status, item.status), format_timestamp(item.detected_at)),
            )
        if previous is not None and self._dup_tree.exists(str(previous)):
            self._dup_tree.selection_set(str(previous))
            self._dup_tree.focus(str(previous))
        self._handle_duplicate_selection()
        self._schedule_layout()
