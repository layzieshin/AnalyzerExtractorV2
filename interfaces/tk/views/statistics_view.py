from __future__ import annotations

import tkinter as tk
import math
from decimal import Decimal
from datetime import datetime, timedelta
from collections.abc import Callable, Sequence
from tkinter import ttk

from interfaces.tk.view_models import format_timestamp
from interfaces.tk.widgets.common import Card, SectionHeader, create_scrollable_tree
from src.application.api import QCAnalysisView, QCLotCase, QCLotDetail, QCReportVersion


class StatisticsView(ttk.Frame):
    """The single lot/QMMA/chart presentation, backed by ResultsController."""

    def __init__(self, master: tk.Misc, *, on_refresh: Callable[[], None],
                 on_qc_selected: Callable[[], None] | None = None,
                 on_configure_qc: Callable[[], None] | None = None,
                 on_reopen_qc: Callable[[], None] | None = None,
                 on_close_qc: Callable[[], None] | None = None,
                 on_qc_report_selected: Callable[[], None] | None = None,
                 on_export_qc: Callable[[], None] | None = None) -> None:
        super().__init__(master, style="Content.TFrame")
        self._on_open_qc = on_refresh
        self._on_qc_selected = on_qc_selected or (lambda: None)
        self._on_configure_qc = on_configure_qc or (lambda: None)
        self._on_reopen_qc = on_reopen_qc or (lambda: None)
        self._on_close_qc = on_close_qc or (lambda: None)
        self._on_qc_report_selected = on_qc_report_selected or (lambda: None)
        self._on_export_qc = on_export_qc or (lambda: None)
        self._qc_analysis: QCAnalysisView | None = None
        self._qc_model = None
        self._qc_version_ids = {}
        self._qc_control_ids = {}
        self._qc_chart_range = None
        self._qc_pan_start = None
        self._qc_chart_hits = {}
        self._qc_cases: dict[str, QCLotCase] = {}
        self._qc_detail: QCLotDetail | None = None
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self._build_qc_panel()

    def _build_qc_panel(self) -> None:
        self._qc_panel = ttk.Frame(self, style="Content.TFrame")
        self._qc_panel.grid(row=0, column=0, sticky="nsew")
        card = Card(self._qc_panel)
        card.pack(fill="both", expand=True)
        footer = ttk.Frame(card.body, style="CardInner.TFrame")
        footer.pack(side="bottom", fill="x", pady=(8, 0))
        scroll = ttk.Scrollbar(card.body, orient="vertical")
        scroll.pack(side="right", fill="y")
        outer = tk.Canvas(card.body, highlightthickness=0, yscrollcommand=scroll.set)
        outer.pack(fill="both", expand=True)
        scroll.configure(command=outer.yview)
        body = ttk.Frame(outer, style="CardInner.TFrame")
        window = outer.create_window((0, 0), window=body, anchor="nw")
        body.bind("<Configure>", lambda _event: outer.configure(scrollregion=outer.bbox("all")))
        outer.bind("<Configure>", lambda event: outer.itemconfigure(window, width=event.width))
        header = ttk.Frame(body, style="CardInner.TFrame")
        header.pack(fill="x", pady=(0, 8))
        ttk.Button(header, text="Neu laden", command=self._on_open_qc).pack(side="left", padx=8)
        ttk.Label(body, text="Chargen und Qualitätskontrolle", style="SectionTitle.TLabel").pack(anchor="w")
        frame, self._qc_tree = create_scrollable_tree(body, ("device", "assay", "lot", "state"),
            ("Gerät", "Assay", "Kit-Charge", "Stand"), height=3)
        frame.pack(fill="both", expand=True, pady=6)
        self._qc_tree.bind("<<TreeviewSelect>>", self._select_qc_case)
        self._qc_tree.column("assay", width=260, minwidth=200, stretch=True)
        profile_row = ttk.Frame(body, style="CardInner.TFrame")
        profile_row.pack(fill="x", pady=4)
        ttk.Label(profile_row, text="Prüfprofil").pack(side="left")
        self._qc_profile = tk.StringVar()
        self._qc_profile_combo = ttk.Combobox(profile_row, textvariable=self._qc_profile, state="readonly", width=45)
        self._qc_profile_combo.pack(side="left", padx=8)
        self._qc_profile_combo.bind("<<ComboboxSelected>>", lambda _event: self._on_qc_selected())
        ttk.Button(profile_row, text="Quellen anzeigen", command=self._on_qc_selected).pack(side="left")
        self._qc_summary = ttk.Label(body, text="Charge auswählen. Prüfprofile werden in den Einstellungen verwaltet.", wraplength=800)
        self._qc_summary.pack(anchor="w", pady=6)
        control_row = ttk.Frame(body, style="CardInner.TFrame")
        control_row.pack(fill="x", pady=4)
        ttk.Label(control_row, text="Kontrolle").pack(side="left")
        self._qc_control = tk.StringVar()
        self._qc_control_combo = ttk.Combobox(control_row, textvariable=self._qc_control, state="readonly", width=45)
        self._qc_control_combo.pack(side="left", padx=8)
        self._qc_control_combo.bind("<<ComboboxSelected>>", lambda _event: self._render_qc_control())
        ttk.Button(control_row, text="Diagramm zurücksetzen", command=self._reset_qc_chart).pack(side="left")
        self._qc_statistics = ttk.Label(body, text="", wraplength=700)
        self._qc_statistics.pack(anchor="w", pady=4)
        self._qc_canvas = tk.Canvas(body, height=230, background="white", highlightthickness=1, highlightbackground="#d8dde6")
        self._qc_canvas.pack(fill="x", pady=4)
        self._qc_canvas.bind("<Configure>", lambda _event: self._draw_qc_chart())
        self._qc_canvas.bind("<MouseWheel>", self._zoom_qc_chart)
        self._qc_canvas.bind("<ButtonPress-1>", self._begin_qc_pan)
        self._qc_canvas.bind("<B1-Motion>", self._pan_qc_chart)
        self._qc_canvas.bind("<Motion>", self._hover_qc_chart)
        self._qc_canvas.bind("<Leave>", lambda _event: self._qc_tooltip.place_forget())
        self._qc_tooltip = ttk.Label(self._qc_canvas, text="", padding=5, wraplength=270)
        self._qc_point_info = ttk.Label(body, text="Messpunkt anklicken; Mausrad zoomt, Ziehen verschiebt.", wraplength=700)
        self._qc_point_info.pack(anchor="w", pady=4)
        frame, self._qc_findings = create_scrollable_tree(body, ("rule", "status", "reason"), ("Regel", "Befund", "Verfügbarkeit / Grund"), height=3)
        frame.pack(fill="x", pady=4)
        ttk.Label(body, text="Quellen und Ausschlüsse", style="SectionTitle.TLabel").pack(anchor="w", pady=(8, 0))
        frame, self._qc_source_tree = create_scrollable_tree(body, ("date", "control", "actual", "target", "state"),
            ("Messdatum", "Kontrolle", "IST", "SOLL", "Eignung / Klärgrund"), height=3)
        frame.pack(fill="both", expand=True, pady=6)
        actions = ttk.Frame(footer, style="CardInner.TFrame")
        actions.pack(fill="x", pady=6)
        self._qc_configure = ttk.Button(actions, text="Charge einrichten / Referenzen", state="disabled", command=self._on_configure_qc)
        self._qc_configure.pack(side="left")
        self._qc_reopen = ttk.Button(actions, text="Charge wieder öffnen", state="disabled", command=self._on_reopen_qc)
        self._qc_reopen.pack(side="left", padx=8)
        self._qc_close = ttk.Button(actions, text="Mit PDF abschließen", state="disabled", command=self._on_close_qc)
        self._qc_close.pack(side="left")
        history_row = ttk.Frame(footer, style="CardInner.TFrame")
        history_row.pack(fill="x", pady=4)
        ttk.Label(history_row, text="Auswertung / Nachweis").pack(side="left")
        self._qc_version = tk.StringVar()
        self._qc_version_combo = ttk.Combobox(history_row, textvariable=self._qc_version, state="readonly", width=38)
        self._qc_version_combo.pack(side="left", padx=8)
        self._qc_version_combo.bind("<<ComboboxSelected>>", lambda _event: self._on_qc_report_selected())
        self._qc_export = ttk.Button(history_row, text="PDF speichern", state="disabled", command=self._on_export_qc)
        self._qc_export.pack(side="left")
        self._qc_include_explanations = tk.BooleanVar(value=False)
        ttk.Checkbutton(footer, text="Erläuterungen zur Diagrammauswertung mitdrucken", variable=self._qc_include_explanations).pack(anchor="w", pady=4)

    def render_qc_lots(self, cases: Sequence[QCLotCase]) -> None:
        self._qc_panel.grid(row=0, column=0, sticky="nsew")
        self._qc_cases = {case.lot_key: case for case in cases}
        self._qc_tree.delete(*self._qc_tree.get_children())
        for case in cases:
            state = {"open": "Offen", "closed": "Abgeschlossen", "unconfigured": "Noch nicht eingerichtet"}.get(case.state, case.state)
            self._qc_tree.insert("", "end", iid=case.lot_key, values=(case.device_name, case.assay_name or "Assayname fehlt", case.kit_lot, state))
        self._clear_qc_detail()
        self._qc_summary.configure(text="Charge auswählen. Prüfprofile werden in den Einstellungen verwaltet." if cases else "Noch keine extrahierten Kit-Chargen vorhanden.")

    def _clear_qc_detail(self) -> None:
        self._qc_detail = None
        self._qc_analysis = None
        self._qc_model = None
        self._qc_tooltip.place_forget()
        self._qc_canvas.delete("all")
        self._qc_statistics.configure(text="")
        self._qc_findings.delete(*self._qc_findings.get_children())
        self._qc_close.configure(state="disabled")
        self._qc_export.configure(state="disabled")
        self._qc_source_tree.delete(*self._qc_source_tree.get_children())
        self._qc_configure.configure(state="disabled")
        self._qc_reopen.configure(state="disabled")

    def _select_qc_case(self, _event) -> None:
        self._clear_qc_detail()
        case = self.selected_qc_case()
        options = case.profile_options if case else ()
        labels = [f"{name} · Fassung {identifier}" for identifier, name in options]
        self._qc_profile_combo.configure(values=labels)
        self._qc_profile_combo.configure(state="disabled" if case and case.state == "closed" else "readonly")
        self._qc_profile.set(next((label for label, option in zip(labels, options) if option[0] == case.profile_version_id), "") if case else "")
        if case and case.profile_version_id:
            self._on_qc_selected()
        else:
            self._qc_summary.configure(text="Bitte ein Prüfprofil wählen." if options else "Für dieses Gerät und diesen Assay zuerst ein Prüfprofil in den Einstellungen erfassen.")

    def selected_qc_case(self) -> QCLotCase | None:
        selected = self._qc_tree.selection()
        return self._qc_cases.get(selected[0]) if selected else None

    def selected_qc_profile_version(self) -> int:
        case = self.selected_qc_case()
        if case:
            for identifier, name in case.profile_options:
                if self._qc_profile.get() == f"{name} · Fassung {identifier}":
                    return identifier
        return 0

    def selected_qc_detail(self) -> QCLotDetail | None:
        return self._qc_detail

    def set_qc_loading(self) -> None:
        self._clear_qc_detail()
        self._qc_summary.configure(text="Lade vollständige Mess- und Validierungsnachweise …")

    def render_qc_detail(self, detail: QCLotDetail) -> None:
        self._qc_detail = detail
        manifest = detail.source_manifest
        self._render_qc_sources(manifest)
        message = f"Beginn: {manifest['start_date'] or 'nicht bestimmbar'} · {manifest['population_count']} gespeicherte Messungen · {manifest['included_count']} geeignete Kontrollwerte · {manifest['excluded_count']} ausgeschlossen."
        if detail.case.state == "closed":
            message += " Abgeschlossene Nachweise bleiben eingefroren; spätere Werte brauchen eine Wiederöffnung."
        elif not detail.sd_references:
            message += " Keine SD-Referenz: SD-Auswertung nicht verfügbar."
        self._qc_summary.configure(text=message)
        self._qc_configure.configure(state="normal" if detail.case.state != "closed" and manifest["included"] else "disabled")
        self._qc_reopen.configure(state="normal" if detail.case.state == "closed" and manifest["included"] else "disabled")

    def _render_qc_sources(self, manifest) -> None:
        self._qc_source_tree.delete(*self._qc_source_tree.get_children())
        labels = {"validation_missing": "Nicht validiert", "validation_ambiguous": "Validierung mehrdeutig",
            "validation_binding_mismatch": "Validierung gehört zu anderem Ergebnisstand", "result_choice_pending": "Ergebnisauswahl offen",
            "result_incomplete": "Ergebnis unvollständig", "result_unreadable": "Ergebnis unlesbar", "measurement_date_invalid": "Messdatum klären",
            "measurement_time_missing": "Extrahierte Messzeit fehlt", "measurement_time_invalid": "Messzeit passt nicht zum festgelegten Format",
            "device_incomplete_or_inactive": "Gerät unvollständig / inaktiv", "target_conflict": "Unterschiedliche Zielwerte: Profil klären",
            "unit_conflict": "Einheitenkonflikt: Profil klären", "unit_missing": "Einheit fehlt", "analytical_run_group_missing": "Analysenlauf fehlt"}
        for point in (*manifest["included"], *manifest["excluded"]):
            reasons = []
            for reason in point["reasons"]:
                reasons.append(labels.get(reason, f"{reason[:-8].upper()}-Wert klären" if reason.endswith("_invalid") else "Nachweis klären"))
            self._qc_source_tree.insert("", "end", values=(point["measured_at"] or "Unlesbar", point["control_name"],
                str(point["raw"].get("IST") or ""), str(point["raw"].get("SOLL") or ""), "; ".join(reasons) or "Eindeutig validiert"))

    def selected_qc_analysis(self) -> QCAnalysisView | None:
        return self._qc_analysis

    def selected_qc_report_version(self) -> int | None:
        return self._qc_version_ids.get(self._qc_version.get())

    def set_qc_analysis_loading(self) -> None:
        self._qc_analysis = None
        self._qc_close.configure(state="disabled")
        self._qc_export.configure(state="disabled")
        self._qc_statistics.configure(text="Lade geprüfte Auswertung …")

    def render_qc_analysis(self, analysis: QCAnalysisView, versions: Sequence[QCReportVersion]) -> None:
        self._qc_analysis = analysis
        self._qc_model = analysis.model
        self._qc_version_ids = {"Aktuelle Auswertung": None} if analysis.case.state != "closed" else {}
        for index, version in enumerate(versions, 1):
            self._qc_version_ids[f"Nachweis {index} · {format_timestamp(version.created_at_utc)}"] = version.version_id
        self._qc_version_combo.configure(values=tuple(self._qc_version_ids))
        self._qc_version.set(next((label for label, value in self._qc_version_ids.items() if value == analysis.evidence_lot_version_id), ""))
        self._qc_control_ids = {series["control_name"]: series["control_id"] for series in self._qc_model["computed_series"]}
        self._qc_control_combo.configure(values=tuple(self._qc_control_ids))
        if self._qc_control.get() not in self._qc_control_ids:
            self._qc_control.set(next(iter(self._qc_control_ids), ""))
        source = self._qc_model["source_manifest"]
        if analysis.evidence_lot_version_id is not None:
            self._render_qc_sources(source)
            self._qc_summary.configure(text=f"Gespeicherter Nachweis · Profilfassung {source['profile_version_id']} · {source['population_count']} eingefrorene Messungen. Heutige Quellen ändern diesen Nachweis nicht.")
        self._qc_close.configure(state="normal" if analysis.case.state == "open" and analysis.evidence_lot_version_id is None and source["included"] else "disabled")
        self._qc_export.configure(state="normal" if analysis.evidence_lot_version_id is not None else "disabled")
        self._render_qc_control()

    @staticmethod
    def _qc_reason(value: str) -> str:
        return {"sd_reference_missing": "Keine SD-Referenz", "history_insufficient": "Zu wenig Messhistorie",
            "sd_origin_unavailable": "Herkunft der SD nicht ausreichend belegt",
            "sd_unit_incompatible": "SD gehört zu einer anderen Einheit",
            "sd_parameter_incompatible": "SD gehört zu einer anderen Messwertdefinition",
            "measurement_order_ambiguous": "Messreihenfolge nicht belegt", "measurement_order_unavailable": "Messreihenfolge nicht belegt",
            "history_value_unavailable": "Nicht verwendbarer Wert unterbricht die Folge", "baseline_sd_zero": "Referenz-SD ist null",
            "baseline_insufficient": "Zu wenig eingefrorene Referenzwerte", "positive_target_required": "Positiver SOLL erforderlich",
            "classic_2sd_trigger_absent": "Aktuelles klassisches 2-SD-Prüfsignal fehlt", "eligible_values_missing": "Keine geeigneten Werte",
            "sd_or_group_incomplete": "SD oder Kontrollgruppe unvollständig", "within_run_controls_or_sd_unavailable": "Gemeinsamer Lauf oder SD nicht belegt",
            "target_or_unit_conflict": "Zielwerte oder Einheiten klären"}.get(value, "Nachweis klären" if value else "")

    def _qc_series(self):
        identifier = self._qc_control_ids.get(self._qc_control.get())
        return next((series for series in self._qc_model["computed_series"] if series["control_id"] == identifier), None) if self._qc_model else None

    def _render_qc_control(self) -> None:
        series = self._qc_series()
        if series is None:
            return
        qmma, sd = series["qmma"], series["sd"]
        actual = f"{Decimal(qmma['value']):.6g} {series['unit']}" if qmma["available"] else self._qc_reason(qmma["reason"])
        relative = f"{Decimal(qmma['relative_percent']):.6g} %" if qmma["relative_percent"] is not None else self._qc_reason(qmma["relative_reason"])
        sd_text = f"SD {Decimal(sd['sd']):.6g} · Referenzmitte {Decimal(sd['center']):.6g}" if sd["available"] else self._qc_reason(sd["reason"])
        self._qc_statistics.configure(text=f"QMMA: {actual} · relativ: {relative} · n = {qmma['n']}\n{sd_text}. Menschliche Validierung bleibt getrennt.")
        self._qc_chart_range = tuple(map(float, (*series["chart"]["x_range"], *series["chart"]["y_range"])))
        self._qc_findings.delete(*self._qc_findings.get_children())
        self._qc_point_info.configure(text="Keine geeigneten auswählbaren Messpunkte." if not series["chart"]["points"] else "Messpunkt anklicken; Mausrad zoomt, Ziehen verschiebt.")
        self._draw_qc_chart()
        if series["chart"]["points"]:
            self._show_qc_point(series["chart"]["points"][-1])

    def _reset_qc_chart(self) -> None:
        self._render_qc_control()

    def _draw_qc_chart(self) -> None:
        canvas = self._qc_canvas
        canvas.delete("all")
        self._qc_chart_hits = {}
        series = self._qc_series()
        if series is None or self._qc_chart_range is None:
            return
        left, top = 55, 15
        width, height = max(10, canvas.winfo_width() - 110), max(10, canvas.winfo_height() - 55)
        xlo, xhi, ylo, yhi = self._qc_chart_range
        if not (all(math.isfinite(value) for value in (xlo, xhi, ylo, yhi, xhi - xlo, yhi - ylo)) and xhi > xlo and yhi > ylo):
            canvas.create_text(80, 40, anchor="w", text="Diagrammskala nicht darstellbar; Kennzahlen bleiben lesbar.")
            return
        self._qc_plot_box = left, top, width, height
        def xy(x, y):
            return left + (float(x) - xlo) / (xhi - xlo) * width, top + height - (float(y) - ylo) / (yhi - ylo) * height
        def inside(point):
            return xlo <= float(point["x"]) <= xhi and ylo <= float(point["y"]) <= yhi
        canvas.create_rectangle(left, top, left + width, top + height, outline="#7c8794")
        chart = series["chart"]
        for band in chart["bands"]:
            y = xy(xlo, band["value"])[1]
            if top <= y <= top + height:
                canvas.create_line(left, y, left + width, y, fill="#aebbcf")
                canvas.create_text(left + width + 4, y, text=f"{band['sd_multiple']:+d} SD", anchor="w", font=("Segoe UI", 8))
        if chart["target"] is not None and ylo <= float(chart["target"]) <= yhi:
            y = xy(xlo, chart["target"])[1]
            canvas.create_line(left, y, left + width, y, fill="#287b51", width=2)
        points = {point["point_key"]: point for point in chart["points"]}
        for segment in chart["segments"]:
            selected = [points[key] for key in segment if key in points]
            for first, last in zip(selected, selected[1:]):
                if inside(first) and inside(last):
                    canvas.create_line(*xy(first["x"], first["y"]), *xy(last["x"], last["y"]), fill="#356ab4")
        for point in points.values():
            if not inside(point):
                continue
            x, y = xy(point["x"], point["y"])
            color = "#ba3030" if point["run_status"] == "reject" else ("#b87016" if point["run_status"] == "warning" else "#356ab4")
            marker = canvas.create_oval(x - 4, y - 4, x + 4, y + 4, fill=color, outline=color)
            self._qc_chart_hits[marker] = point
        canvas.create_text(left - 6, top, text=f"{yhi:.4g}", anchor="ne")
        canvas.create_text(left - 6, top + height, text=f"{ylo:.4g}", anchor="se")
        if points:
            for bound, x, anchor in ((xlo, left, "nw"), (xhi, left + width, "ne")):
                try:
                    ordinal = math.floor(bound)
                    measured = datetime.fromordinal(ordinal) + timedelta(seconds=round((bound - ordinal) * 86400))
                    label = format_timestamp(measured.isoformat())
                except (ValueError, OverflowError):
                    label = "Datum nicht darstellbar"
                canvas.create_text(x, top + height + 7, text=label, anchor=anchor, font=("Segoe UI", 8), tags=("qc-x-axis",))

    def _qc_hit(self, event):
        return next((self._qc_chart_hits[item] for item in reversed(self._qc_canvas.find_overlapping(event.x - 5, event.y - 5, event.x + 5, event.y + 5)) if item in self._qc_chart_hits), None)

    def _show_qc_point(self, point) -> None:
        shown_z = format(Decimal(point['z']), ".6g") if point['z'] is not None else "nicht verfügbar"
        self._qc_point_info.configure(text=f"Messung {point['run_id']} · {point['measured_at']} · IST {point['raw'].get('IST', '–')} / SOLL {point['raw'].get('SOLL', '–')} · z {shown_z} · Revision {point['revision_id']} · Validierung {point.get('validation_id')}" + (" · Messreihenfolge mehrdeutig" if point["order_ambiguous"] else ""))
        self._qc_findings.delete(*self._qc_findings.get_children())
        statuses = {"reject": "Ablehnungsbefund", "warning": "Warnung", "unavailable": "Nicht verfügbar", "pass": "Kein Befund", "disabled": "Nicht ausgewählt", "not_triggered": "Prüfsignal fehlt"}
        for finding in point["findings"]:
            self._qc_findings.insert("", "end", values=(finding["rule"], statuses[finding["status"]], self._qc_reason(finding["reason"])))

    def _hover_qc_chart(self, event) -> None:
        point = self._qc_hit(event)
        if point is None:
            self._qc_tooltip.place_forget()
            return
        shown_z = format(Decimal(point['z']), ".6g") if point['z'] is not None else "nicht verfügbar"
        self._qc_tooltip.configure(text=f"{point['measured_at']}\nIST {point['raw'].get('IST', '–')} · SOLL {point['raw'].get('SOLL', '–')}\nz {shown_z}")
        self._qc_tooltip.place(x=max(0, min(event.x + 10, self._qc_canvas.winfo_width() - 280)), y=max(0, min(event.y + 10, self._qc_canvas.winfo_height() - 65)))

    def _begin_qc_pan(self, event) -> None:
        point = self._qc_hit(event)
        if point is not None:
            self._show_qc_point(point)
        self._qc_pan_start = event.x, event.y, self._qc_chart_range

    def _pan_qc_chart(self, event) -> None:
        if self._qc_pan_start is None or self._qc_pan_start[2] is None:
            return
        x, y, (xlo, xhi, ylo, yhi) = self._qc_pan_start
        _left, _top, width, height = self._qc_plot_box
        dx, dy = (event.x - x) / width * (xhi - xlo), (event.y - y) / height * (yhi - ylo)
        self._qc_chart_range = xlo - dx, xhi - dx, ylo + dy, yhi + dy
        self._draw_qc_chart()

    def _zoom_qc_chart(self, event) -> None:
        if self._qc_chart_range is None:
            return
        xlo, xhi, ylo, yhi = self._qc_chart_range
        factor = 0.8 if event.delta > 0 else 1.25
        cx, cy = (xlo + xhi) / 2, (ylo + yhi) / 2
        self._qc_chart_range = cx - (cx - xlo) * factor, cx + (xhi - cx) * factor, cy - (cy - ylo) * factor, cy + (yhi - cy) * factor
        self._draw_qc_chart()

