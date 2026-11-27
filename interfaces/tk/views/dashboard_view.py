from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from collections.abc import Callable, Sequence
from tkinter import ttk

from interfaces.tk.desktop_theme import COLOR_BG, COLOR_ERROR, COLOR_HERO, COLOR_PRIMARY, COLOR_SUCCESS, COLOR_WARNING
from interfaces.tk.view_models import (
    BatchFileStatus,
    DashboardRecentRow,
    DASHBOARD_RECENT_LIMIT,
    format_batch_status_message,
    format_watch_cycle_summary,
    status_badge_kind,
    watch_enabled_label,
)
from interfaces.tk.widgets.common import Card, EmptyState, ScrollableFrame, SectionHeader, StatusBadge, create_readonly_tree
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
        on_open_results: Callable[[], None],
        on_open_validation: Callable[[], None],
    ) -> None:
        super().__init__(master, style="Content.TFrame")
        self._on_pick_and_process_pdfs = on_pick_and_process_pdfs
        self._on_open_settings = on_open_settings
        self._on_refresh = on_refresh
        self._on_open_report = on_open_report
        self._on_open_selected_report = on_open_selected_report
        self._on_open_results = on_open_results
        self._on_open_validation = on_open_validation
        self._report_ids: dict[str, str] = {}
        self._recent_rows: dict[str, DashboardRecentRow] = {}
        self._recent_all_rows: tuple[DashboardRecentRow, ...] = ()
        self._recent_expanded = False
        self._selected_recent_id: str | None = None
        self._recent_limit = 5
        self._build()

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self._scrollable = ScrollableFrame(self, autohide=True)
        self._scrollable.grid(row=0, column=0, sticky="nsew")
        self._scrollable._canvas.configure(background=COLOR_BG)
        content = self._scrollable.body
        content.configure(style="Content.TFrame")
        content.columnconfigure(0, weight=1)

        heading = ttk.Frame(content, style="Content.TFrame")
        heading.grid(row=0, column=0, sticky="ew", pady=(0, 18))
        ttk.Label(heading, text="L A B O R A R B E I T S P L A T Z", style="Eyebrow.TLabel").pack(anchor="w")
        ttk.Label(heading, text="Arbeitsübersicht", style="PageTitle.TLabel").pack(anchor="w", pady=(6, 4))
        ttk.Label(
            heading, text="Berichte importieren und die nächsten offenen Aufgaben sehen.",
            style="PageSubtitle.TLabel",
        ).pack(anchor="w")

        start = ttk.Frame(content, style="Content.TFrame")
        start.grid(row=1, column=0, sticky="ew", pady=(0, 14))
        start.columnconfigure(0, weight=5, uniform="start")
        start.columnconfigure(1, weight=3, uniform="start")
        self._import_card = import_card = Card(start, padding=18, rounded=True, background=COLOR_HERO)
        import_card.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        body = import_card.body
        body.configure(style="Hero.TFrame")
        import_title = ttk.Frame(body, style="Hero.TFrame")
        import_title.pack(fill="x", pady=(0, 10))
        ttk.Label(import_title, text="↑", style="HeroIcon.TLabel", padding=(8, 1)).pack(side="left", padx=(0, 10))
        ttk.Label(import_title, text="PDF-Berichte auswerten", style="HeroTitle.TLabel").pack(side="left")
        self._lbl_import_context = ttk.Label(
            body, text="Dateien auswählen und mit dem aktuellen Importgerät verarbeiten.",
            style="HeroMuted.TLabel", wraplength=450,
        )
        self._lbl_import_context.pack(anchor="w", pady=(0, 12))
        import_actions = ttk.Frame(body, style="Hero.TFrame")
        import_actions.pack(fill="x")
        self._btn_pick = ttk.Button(
            import_actions,
            text="PDFs auswählen",
            style="Primary.TButton",
            command=self._on_pick_and_process_pdfs,
        )
        self._btn_pick.pack(side="left")
        ttk.Button(import_actions, text="Gerät wechseln", command=self._on_open_settings).pack(side="left", padx=(10, 0))
        self._lbl_activity = ttk.Label(body, text="Bereit.", style="HeroMuted.TLabel", wraplength=450)
        self._lbl_activity.pack(anchor="w", pady=(10, 0))
        body.bind("<Configure>", self._resize_import_text)

        context = ttk.Frame(start, style="Content.TFrame")
        context.grid(row=0, column=1, sticky="nsew")
        context.columnconfigure(0, weight=1)
        context.rowconfigure(0, weight=1)
        cases_card = Card(context, padding=16, rounded=True)
        cases_card.grid(row=0, column=0, sticky="nsew")
        metric = ttk.Frame(cases_card.body, style="CardInner.TFrame")
        metric.pack(fill="x")
        self._lbl_open_count = ttk.Label(metric, text="–", style="Metric.TLabel")
        self._lbl_open_count.pack(side="left", padx=(0, 8))
        ttk.Label(metric, text="im Prüfplatz", style="Muted.TLabel").pack(side="left", anchor="s", pady=(0, 4))
        ttk.Label(
            cases_card.body, text="Offene Fälle, Vergleiche und Nacharbeit", style="Muted.TLabel", wraplength=260,
        ).pack(anchor="w", pady=(0, 8))
        self._btn_open_validation = ttk.Button(
            cases_card.body, text="Prüfplatz öffnen  →", command=self._on_open_validation,
        )
        self._btn_open_validation.pack(anchor="w")
        device_line = ttk.Frame(cases_card.body, style="CardInner.TFrame")
        device_line.pack(fill="x", pady=(12, 0))
        ttk.Label(device_line, text="Importgerät", style="Muted.TLabel").pack(anchor="w")
        self._lbl_device = ttk.Label(device_line, text="Wird geladen …", style="Device.TLabel", wraplength=260)
        self._lbl_device.pack(anchor="w", pady=(2, 0))
        device_line.bind("<Configure>", lambda event: self._lbl_device.configure(wraplength=max(140, event.width)))

        self._lbl_batch = ttk.Label(content, text="", style="PageSubtitle.TLabel", wraplength=850)
        self._recent_card = recent_card = Card(content, padding=16, rounded=True)
        recent_card.grid(row=3, column=0, sticky="nsew", pady=(0, 14))
        rbody = recent_card.body
        SectionHeader(
            rbody,
            "Letzte Importe",
            subtitle="Zum passenden Bericht springen.",
            action_text="Alle Ergebnisse  →",
            on_action=self._on_open_results,
        ).pack(fill="x", pady=(0, 12))
        columns = ("file", "summary", "time", "status", "source", "details")
        self._tree = create_readonly_tree(
            rbody,
            columns,
            ("Bericht", "Assay / Gerät", "Eingang", "Status", "Herkunft", ""),
            height=1,
        )
        self._tree.configure(style="Recent.Treeview", show=("tree", "headings"), displaycolumns=("file", "summary", "status", "details"))
        self._tree.column("#0", width=22, minwidth=22, stretch=False)
        self._tree.heading("#0", text="")
        self._status_marks = {}
        for kind, color in (("neutral", COLOR_PRIMARY), ("success", COLOR_SUCCESS), ("warning", COLOR_WARNING), ("error", COLOR_ERROR)):
            mark = tk.PhotoImage(master=self, width=10, height=10)
            for y in range(10):
                for x in range(10):
                    if (x - 4.5) ** 2 + (y - 4.5) ** 2 <= 16:
                        mark.put(color, (x, y))
            self._status_marks[kind] = mark
        self._tree.pack(fill="x")
        self._tree.bind("<Configure>", self._resize_recent_columns)
        self._tree.bind("<<TreeviewSelect>>", lambda _e: self._update_open_result_button())
        self._tree.bind("<Double-1>", self._handle_open_report)
        self._tree.bind("<Return>", self._handle_open_report)
        self._tree.bind("<ButtonRelease-1>", self._open_recent_details)
        self._tree.bind("<MouseWheel>", self._scroll_dashboard)
        self._tree.bind("<Next>", lambda _event: self._scrollable._canvas.yview_scroll(1, "pages") or "break")
        self._tree.bind("<Prior>", lambda _event: self._scrollable._canvas.yview_scroll(-1, "pages") or "break")
        self._lbl_recent_meta = ttk.Label(rbody, text="", style="Muted.TLabel", wraplength=800)
        recent_actions = ttk.Frame(rbody, style="CardInner.TFrame")
        recent_actions.pack(fill="x", pady=(8, 0))
        self._btn_open_result = ttk.Button(
            recent_actions,
            text="Ergebnis öffnen",
            command=self._on_open_selected_report,
            state="disabled",
        )
        self._btn_open_result.pack(side="left")
        ttk.Button(recent_actions, text="Aktualisieren", command=self._on_refresh).pack(side="right")
        self._lbl_recent_count = ttk.Label(recent_actions, text="", style="Muted.TLabel")
        self._lbl_recent_count.pack(side="left", padx=(12, 0))
        self._btn_more_recent = ttk.Button(recent_actions, text="Weitere Importe", command=self._toggle_recent_rows)
        self._empty_recent = EmptyState(rbody, "Noch keine Importe vorhanden.", hint="Wählen Sie PDF-Berichte für die erste Auswertung aus.")

        self._watch_card = watch_card = Card(content, padding=14, rounded=True)
        watch_card.grid(row=4, column=0, sticky="ew")
        wbody = watch_card.body
        SectionHeader(
            wbody, "Ordnerimport", action_text="Konfigurieren", on_action=self._on_open_settings,
        ).pack(fill="x", pady=(0, 8))
        watch_line = ttk.Frame(wbody, style="CardInner.TFrame")
        watch_line.pack(fill="x")
        self._watch_status = StatusBadge(watch_line, "Inaktiv")
        self._watch_status.pack(side="left", anchor="n", padx=(0, 10))
        self._lbl_watch_input = ttk.Label(watch_line, text="Kein Eingabeordner konfiguriert.", style="Muted.TLabel", wraplength=650)
        self._lbl_watch_input.pack(side="left", fill="x", expand=True)
        watch_line.bind("<Configure>", lambda event: self._lbl_watch_input.configure(wraplength=max(200, event.width - 80)))
        self._lbl_watch_backup = ttk.Label(wbody, text="Kein Verschieben", style="Muted.TLabel", wraplength=800)
        self._lbl_watch_backup.pack(anchor="w", pady=(3, 0))
        self._lbl_watch_session = ttk.Label(wbody, text="", style="Muted.TLabel", wraplength=800)

        def bind_scroll(widget: tk.Misc) -> None:
            if widget is self._tree:
                return
            widget.bind("<MouseWheel>", self._scroll_dashboard, add="+")
            for child in widget.winfo_children():
                bind_scroll(child)

        bind_scroll(self._scrollable)

    def _scroll_dashboard(self, event: tk.Event) -> str:
        if self._scrollable._canvas.yview() != (0.0, 1.0):
            self._scrollable._canvas.yview_scroll(-int(event.delta / 120), "units")
        return "break"

    def _resize_recent_columns(self, event: tk.Event | None = None) -> None:
        width = event.width if event is not None else self._tree.winfo_width()
        if width <= 1:
            return
        available = max(1, width - 26)
        font = tkfont.Font(self, font=ttk.Style(self).lookup("Recent.Treeview", "font"))
        status_width = max(115, max((font.measure(self._tree.set(key, "status")) for key in self._tree.get_children()), default=0) + 24)
        details_width = font.measure("Details →") + 24
        file_min = font.measure("ANA_2026-11-26_0814.pdf") + 24
        summary_min = font.measure("Assay / Gerät") + 30
        time_width = max(font.measure(item.time_text) for item in self._recent_rows.values()) + 20 if self._recent_rows else font.measure("26.11.2026 08:14") + 20
        source_width = max((font.measure(item.source) for item in self._recent_rows.values()), default=font.measure("Herkunft")) + 20
        fixed_width = status_width + details_width
        if available >= max(840, file_min + fixed_width + summary_min):
            complete = available >= file_min + fixed_width + summary_min + time_width + source_width
            self._tree.configure(displaycolumns=("file", "summary", "time", "status", "source", "details") if complete else ("file", "summary", "status", "details"))
            if complete:
                fixed_width += time_width + source_width
                self._tree.column("time", width=time_width, minwidth=1, stretch=False)
                self._tree.column("source", width=source_width, minwidth=1, stretch=False)
            remaining = available - fixed_width
            file_width = max(file_min, round(remaining * 0.56))
            self._tree.column("summary", width=max(1, remaining - file_width), minwidth=1, stretch=False)
        else:
            self._tree.configure(displaycolumns=("file", "status", "details"))
            file_width = max(1, available - status_width - details_width)
        for column, column_width in (("file", file_width), ("status", status_width), ("details", details_width)):
            self._tree.column(column, width=column_width, minwidth=1, stretch=False)
        self._lbl_recent_meta.configure(wraplength=max(200, width - 8))

    def _open_recent_details(self, event: tk.Event) -> None:
        row_id = self._tree.identify_row(event.y)
        box = self._tree.bbox(row_id, "details") if row_id else ()
        if row_id in self._report_ids and box and box[0] <= event.x < box[0] + box[2]:
            self._tree.selection_set(row_id)
            self._tree.focus(row_id)
            self._update_open_result_button()
            self._on_open_report(self._report_ids[row_id])

    def _resize_import_text(self, event: tk.Event) -> None:
        width = max(200, event.width)
        self._lbl_import_context.configure(wraplength=width)
        self._lbl_activity.configure(wraplength=width)

    def render_import_device(self, label: str) -> None:
        self._lbl_device.configure(text=label)
        self._lbl_import_context.configure(text=f"Importgerät für die ausgewählten PDF-Berichte: {label}.")

    def render_open_case_count(self, count: int | None) -> None:
        self._lbl_open_count.configure(text="–" if count is None else str(max(0, int(count))))

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
        self._btn_open_validation.configure(state=state)
        if not enabled:
            self._btn_open_result.configure(state="disabled")

    def render_watch_settings(self, settings: DesktopSettings) -> None:
        enabled = bool(settings.watch_enabled)
        self._watch_status.set_status(watch_enabled_label(enabled), kind="success" if enabled else "neutral")
        self._lbl_watch_input.configure(text=settings.watch_input_path or "Kein Eingabeordner konfiguriert.")
        recursive = "Ja" if settings.watch_recursive else "Nein"
        archive = f"Archiv: {settings.watch_backup_path}" if settings.watch_backup_path else "Kein Verschieben"
        self._lbl_watch_backup.configure(text=f"{archive}  ·  Unterordner: {recursive}")

    def render_watch_session_summary(self, summary: WatchCycleSummary | None, *, error: str = "") -> None:
        text = format_watch_cycle_summary(summary, error=error)
        self._lbl_watch_session.configure(text=text)
        if text:
            self._lbl_watch_session.pack(anchor="w", pady=(4, 0))
        else:
            self._lbl_watch_session.pack_forget()

    def render_recent_rows(self, rows: Sequence[DashboardRecentRow]) -> None:
        selection = self._tree.selection()
        if selection:
            self._selected_recent_id = str(selection[0])
        for row in self._tree.get_children():
            self._tree.delete(row)
        self._recent_all_rows = tuple(rows[:DASHBOARD_RECENT_LIMIT])
        visible_rows = self._recent_all_rows if self._recent_expanded else self._recent_all_rows[:self._recent_limit]
        self._recent_rows = {item.row_id: item for item in self._recent_all_rows}
        self._report_ids = {item.row_id: item.report_id for item in self._recent_all_rows if item.report_id}
        if self._selected_recent_id not in self._recent_rows:
            self._selected_recent_id = None
        self._tree.configure(height=max(1, len(visible_rows)))
        self._lbl_recent_count.configure(text=f"{len(visible_rows)} von {len(self._recent_all_rows)} letzten Importen" if rows else "")
        if len(self._recent_all_rows) > self._recent_limit:
            self._btn_more_recent.configure(text="Weniger anzeigen" if self._recent_expanded else "Weitere Importe")
            self._btn_more_recent.pack(side="left", padx=(12, 0))
        else:
            self._btn_more_recent.pack_forget()
        self._update_open_result_button()
        if not rows:
            self._empty_recent.pack(anchor="w", pady=(8, 0))
            return
        self._empty_recent.pack_forget()
        for item in visible_rows:
            status = "Fehlgeschlagen" if "verarbeitung fehlgeschlagen" in item.status.casefold() else item.status
            if "wird archiviert" in status.casefold():
                status = "Archivierung"
            elif "teilweise validiert" in status.casefold():
                status = "Teilw. validiert"
            kind = status_badge_kind(item.status)
            if any(word in item.status.casefold() for word in ("vergleich", "nacharbeit")):
                kind = "warning"
            self._tree.insert(
                "",
                "end",
                iid=item.row_id,
                image=self._status_marks[kind],
                values=(item.file_name, item.summary, item.time_text, status, item.source, "Details →" if item.report_id else "–"),
            )
            if item.report_id:
                self._report_ids[item.row_id] = item.report_id
        if self._selected_recent_id is not None and self._tree.exists(self._selected_recent_id):
            self._tree.selection_set(self._selected_recent_id)
            self._tree.focus(self._selected_recent_id)
        self._update_open_result_button()
        self._resize_recent_columns()

    def _toggle_recent_rows(self) -> None:
        self._recent_expanded = not self._recent_expanded
        self.render_recent_rows(self._recent_all_rows)

    def selected_report_id(self) -> str | None:
        selection = self._tree.selection()
        selected_id = str(selection[0]) if selection else self._selected_recent_id
        return self._report_ids.get(selected_id) if selected_id is not None else None

    def _update_open_result_button(self) -> None:
        report_id = self.selected_report_id()
        state = "normal" if report_id else "disabled"
        self._btn_open_result.configure(state=state)
        selection = self._tree.selection()
        if selection:
            self._selected_recent_id = str(selection[0])
        item = self._recent_rows.get(self._selected_recent_id) if self._selected_recent_id else None
        if item is not None:
            prefix = "Auswahl unter Weitere Importe: " if not self._tree.exists(item.row_id) else ""
            self._lbl_recent_meta.configure(text=prefix + " · ".join(value for value in (item.file_name, item.source, item.time_text, item.status, item.summary, item.notice) if value))
            self._lbl_recent_meta.pack(fill="x", pady=(6, 0), before=self._btn_open_result.master)
        else:
            self._lbl_recent_meta.pack_forget()

    def render_batch_statuses(self, statuses: Sequence[BatchFileStatus]) -> None:
        text = format_batch_status_message(tuple(statuses))
        self._lbl_batch.configure(text=text)
        if text:
            self._lbl_batch.grid(row=2, column=0, sticky="ew", pady=(0, 14))
        else:
            self._lbl_batch.grid_remove()
