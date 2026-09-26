from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Sequence
from tkinter import ttk

from interfaces.tk.view_models import format_assay_candidate_lines
from interfaces.tk.widgets.common import Card, EmptyState, SectionHeader, create_scrollable_tree
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
        self._build()

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        diag_card = Card(self)
        diag_card.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        dbody = diag_card.body
        SectionHeader(dbody, "Fehlgeschlagene Verarbeitungen", action_text="Aktualisieren", on_action=self._on_refresh).pack(
            fill="x", pady=(0, 8)
        )
        columns = ("file", "error", "message")
        diag_frame, self._diag_tree = create_scrollable_tree(
            dbody,
            columns,
            ("Datei", "Fehlerart", "Hinweis"),
            height=6,
        )
        diag_frame.pack(fill="both", expand=True, pady=(0, 8))
        self._diag_empty = EmptyState(dbody, "Keine fehlgeschlagenen Jobs.")
        diag_actions = ttk.Frame(dbody, style="CardInner.TFrame")
        diag_actions.pack(fill="x")
        ttk.Button(diag_actions, text="Details", command=self._on_show_diagnosis).pack(side="left")
        ttk.Button(diag_actions, text="Erneut versuchen", command=self._on_retry_job).pack(side="left", padx=(8, 0))
        ttk.Button(diag_actions, text="Draft aus Kandidat", command=self._on_create_draft).pack(side="left", padx=(8, 0))

        ttk.Label(dbody, text="Assay-Kandidaten", style="SectionTitle.TLabel").pack(anchor="w", pady=(8, 4))
        cand_columns = ("assay", "name", "status", "confidence")
        cand_frame, self._candidate_tree = create_scrollable_tree(
            dbody,
            cand_columns,
            ("Assay", "Name", "Status", "Konfidenz"),
            height=4,
        )
        cand_frame.pack(fill="both", expand=True, pady=(0, 8))
        self._lbl_context = ttk.Label(dbody, text="", style="Muted.TLabel", wraplength=700)
        self._lbl_context.pack(anchor="w")

        dup_card = Card(self)
        dup_card.grid(row=1, column=0, sticky="nsew")
        dup_body = dup_card.body
        SectionHeader(
            dup_body,
            "Klärfälle (Duplikate)",
            subtitle="Ausstehende Duplikat-Kandidaten zur manuellen Entscheidung.",
        ).pack(fill="x", pady=(0, 8))
        dup_columns = ("assay", "status", "detected")
        dup_frame, self._dup_tree = create_scrollable_tree(
            dup_body,
            dup_columns,
            ("Assay", "Status", "Erkannt"),
            height=5,
        )
        dup_frame.pack(fill="both", expand=True, pady=(0, 8))
        self._dup_empty = EmptyState(dup_body, "Keine ausstehenden Klärfälle.")
        dup_actions = ttk.Frame(dup_body, style="CardInner.TFrame")
        dup_actions.pack(fill="x")
        ttk.Button(dup_actions, text="Details", command=self._on_show_duplicate).pack(side="left")
        ttk.Button(dup_actions, text="Verwerfen", command=self._on_discard_duplicate).pack(side="left", padx=(8, 0))

    def selected_job_id(self) -> str:
        selection = self._diag_tree.selection()
        return str(selection[0]) if selection else ""

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
        for row in self._diag_tree.get_children():
            self._diag_tree.delete(row)
        if not items:
            self._diag_empty.pack(anchor="w", pady=(8, 0))
            return
        self._diag_empty.pack_forget()
        for item in items:
            self._diag_tree.insert(
                "",
                "end",
                iid=item.job_id,
                values=(item.file_name, item.error_label, item.friendly_message or item.technical_detail),
            )

    def render_candidates(self, candidates: Sequence[AssayCandidateItem]) -> None:
        for row in self._candidate_tree.get_children():
            self._candidate_tree.delete(row)
        self._candidates_by_id.clear()
        for index, candidate in enumerate(candidates):
            iid = candidate.candidate_id or f"{candidate.assay_key}::{index}"
            self._candidates_by_id[iid] = candidate
            self._candidate_tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    candidate.assay_key,
                    candidate.assay_name_hint,
                    candidate.known_status,
                    candidate.confidence,
                ),
            )
        self._lbl_context.configure(text="\n".join(format_assay_candidate_lines(candidates)))

    def render_duplicates(self, items: Sequence[DuplicateCandidateItem]) -> None:
        for row in self._dup_tree.get_children():
            self._dup_tree.delete(row)
        if not items:
            self._dup_empty.pack(anchor="w", pady=(8, 0))
            return
        self._dup_empty.pack_forget()
        for item in items:
            self._dup_tree.insert(
                "",
                "end",
                iid=str(item.candidate_id),
                values=(item.assay_key, item.status, item.detected_at),
            )
