from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Sequence
from tkinter import ttk

from interfaces.tk.view_models import (
    BatchFileStatus,
    DashboardRecentRow,
    format_batch_status_message,
    format_watch_cycle_summary,
    watch_enabled_label,
)
from interfaces.tk.widgets.common import Card, EmptyState, SectionHeader, StatusBadge, create_scrollable_tree
from src.application.api import DesktopSettings, WatchCycleSummary


class DashboardView(ttk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        *,
        on_pick_and_process_pdfs: Callable[[], None],
        on_open_settings: Callable[[], None],
        on_refresh: Callable[[], None],
        on_open_report: Callable[[str], None],
        on_open_selected_report: Callable[[], None],
    ) -> None:
        super().__init__(master, style="Content.TFrame")
        self._on_pick_and_process_pdfs = on_pick_and_process_pdfs
        self._on_open_settings = on_open_settings
        self._on_refresh = on_refresh
        self._on_open_report = on_open_report
        self._on_open_selected_report = on_open_selected_report
        self._report_ids: dict[str, str] = {}
        self._build()

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)

        import_card = Card(self)
        import_card.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        body = import_card.body
        SectionHeader(
            body,
            "PDF-Berichte auswerten",
            subtitle="PDFs auswählen – die Verarbeitung startet automatisch.",
        ).pack(fill="x", pady=(0, 8))
        actions = ttk.Frame(body, style="CardInner.TFrame")
        actions.pack(fill="x", pady=(0, 8))
        self._btn_pick = ttk.Button(
            actions,
            text="PDFs auswählen",
            style="Primary.TButton",
            command=self._on_pick_and_process_pdfs,
        )
        self._btn_pick.pack(side="left")
        self._lbl_activity = ttk.Label(body, text="Bereit.", style="Muted.TLabel", wraplength=700)
        self._lbl_activity.pack(anchor="w", pady=(0, 4))
        self._lbl_batch = ttk.Label(body, text="", style="Muted.TLabel", wraplength=700)
        self._lbl_batch.pack(anchor="w")

        watch_card = Card(self)
        watch_card.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        wbody = watch_card.body
        header = SectionHeader(
            wbody,
            "Automatischer Import",
            subtitle="Watch-Ordner und Archiv werden in den Einstellungen konfiguriert.",
            action_text="Einstellungen",
            on_action=self._on_open_settings,
        )
        header.pack(fill="x", pady=(0, 8))
        self._watch_status = StatusBadge(wbody, "Inaktiv")
        self._watch_status.pack(anchor="w", pady=(0, 4))
        self._lbl_watch_input = ttk.Label(wbody, text="Eingabe: -", style="Muted.TLabel")
        self._lbl_watch_input.pack(anchor="w")
        self._lbl_watch_backup = ttk.Label(wbody, text="Archiv: -", style="Muted.TLabel")
        self._lbl_watch_backup.pack(anchor="w")
        self._lbl_watch_recursive = ttk.Label(wbody, text="Unterordner: Nein", style="Muted.TLabel")
        self._lbl_watch_recursive.pack(anchor="w", pady=(0, 4))
        self._lbl_watch_session = ttk.Label(wbody, text="", style="Muted.TLabel", wraplength=700)
        self._lbl_watch_session.pack(anchor="w", pady=(0, 4))
        ttk.Label(
            wbody,
            text="Bei aktivem Auto-Import werden neue PDFs im Hintergrund erkannt und verarbeitet.",
            style="Muted.TLabel",
            wraplength=700,
        ).pack(anchor="w")

        recent_card = Card(self)
        recent_card.grid(row=2, column=0, sticky="nsew")
        self.rowconfigure(2, weight=1)
        rbody = recent_card.body
        SectionHeader(
            rbody,
            "Letzte Verarbeitungen",
            action_text="Aktualisieren",
            on_action=self._on_refresh,
        ).pack(fill="x", pady=(0, 8))
        columns = ("status", "file", "summary", "time", "source")
        tree_frame, self._tree = create_scrollable_tree(
            rbody,
            columns,
            ("Status", "Datei", "Assays/Gerät", "Zeitpunkt", "Herkunft"),
            height=8,
        )
        tree_frame.pack(fill="both", expand=True)
        self._tree.bind("<<TreeviewSelect>>", lambda _e: self._update_open_result_button())
        self._tree.bind("<Double-1>", self._handle_open_report)
        recent_actions = ttk.Frame(rbody, style="CardInner.TFrame")
        recent_actions.pack(fill="x", pady=(8, 0))
        self._btn_open_result = ttk.Button(
            recent_actions,
            text="Ergebnis öffnen",
            command=self._on_open_selected_report,
            state="disabled",
        )
        self._btn_open_result.pack(side="left")
        self._empty_recent = EmptyState(rbody, "Noch keine Verarbeitungen vorhanden.")

    def _handle_open_report(self, _event: object) -> None:
        selection = self._tree.selection()
        if not selection:
            return
        report_id = self._report_ids.get(str(selection[0]))
        if report_id:
            self._on_open_report(report_id)

    def set_activity_message(self, message: str) -> None:
        self._lbl_activity.configure(text=message)

    def set_processing_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        self._btn_pick.configure(state=state)

    def set_actions_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        self._btn_pick.configure(state=state)
        if not enabled:
            self._btn_open_result.configure(state="disabled")

    def render_watch_settings(self, settings: DesktopSettings) -> None:
        enabled = bool(settings.watch_enabled)
        self._watch_status.set_status(watch_enabled_label(enabled), kind="success" if enabled else "neutral")
        self._lbl_watch_input.configure(text=f"Eingabe: {settings.watch_input_path or '-'}")
        self._lbl_watch_backup.configure(text=f"Archiv: {settings.watch_backup_path or '-'}")
        recursive = "Ja" if settings.watch_recursive else "Nein"
        self._lbl_watch_recursive.configure(text=f"Unterordner: {recursive}")

    def render_watch_session_summary(self, summary: WatchCycleSummary | None, *, error: str = "") -> None:
        self._lbl_watch_session.configure(text=format_watch_cycle_summary(summary, error=error))

    def render_recent_rows(self, rows: Sequence[DashboardRecentRow]) -> None:
        for row in self._tree.get_children():
            self._tree.delete(row)
        self._report_ids.clear()
        if not rows:
            self._empty_recent.pack(anchor="w", pady=(8, 0))
            return
        self._empty_recent.pack_forget()
        for item in rows:
            self._tree.insert(
                "",
                "end",
                iid=item.row_id,
                values=(item.status, item.file_name, item.summary, item.time_text, item.source),
            )
            if item.report_id:
                self._report_ids[item.row_id] = item.report_id
        self._update_open_result_button()

    def selected_report_id(self) -> str | None:
        selection = self._tree.selection()
        if not selection:
            return None
        return self._report_ids.get(str(selection[0]))

    def _update_open_result_button(self) -> None:
        report_id = self.selected_report_id()
        state = "normal" if report_id else "disabled"
        self._btn_open_result.configure(state=state)

    def render_batch_statuses(self, statuses: Sequence[BatchFileStatus]) -> None:
        self._lbl_batch.configure(text=format_batch_status_message(tuple(statuses)))
