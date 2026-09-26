"""Seltene Rule-Editor-Funktionen. Kein src-Import."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from interfaces.tk.scroll_helpers import bind_mousewheel, create_scrollable_listbox, create_scrollable_treeview
from interfaces.tk.widgets.common import Card, SectionHeader


def build_advanced_view(host: tk.Misc, parent: tk.Widget) -> None:
    parent.rowconfigure(1, weight=1)
    parent.columnconfigure(0, weight=1)

    bar = ttk.Frame(parent, style="Header.TFrame")
    bar.grid(row=0, column=0, columnspan=2, sticky="ew", padx=6, pady=(6, 4))
    ttk.Label(bar, text="Regeldetails", style="AppTitle.TLabel").pack(side="left")
    ttk.Label(
        bar,
        text="Feldprüfung, Exportdetails, Strukturprüfung und Protokoll",
        style="AppSubtitle.TLabel",
    ).pack(side="left", padx=(12, 0))
    ttk.Button(bar, text="Zurück zum Arbeitsbereich", command=host._hide_advanced).pack(side="right")

    canvas = tk.Canvas(parent, highlightthickness=0)
    host.advanced_canvas = canvas
    scroll = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=scroll.set)
    canvas.grid(row=1, column=0, sticky="nsew")
    scroll.grid(row=1, column=1, sticky="ns")
    inner = ttk.Frame(canvas, style="Content.TFrame")
    host.advanced_inner = inner
    window_id = canvas.create_window((0, 0), window=inner, anchor="nw")

    def _sync_scroll(_event: tk.Event | None = None) -> None:
        canvas.configure(scrollregion=canvas.bbox("all"))

    def _stretch(event: tk.Event) -> None:
        canvas.itemconfigure(window_id, width=event.width)

    inner.bind("<Configure>", _sync_scroll)
    canvas.bind("<Configure>", _stretch)

    host._advanced_sections = {}
    _build_field_extras(host, inner)
    _build_meta(host, inner)
    _build_validation(host, inner)
    _build_log(host, inner)

    def _bind_descendants(widget: tk.Widget) -> None:
        bind_mousewheel(widget, canvas)
        for child in widget.winfo_children():
            _bind_descendants(child)

    _bind_descendants(inner)
    bind_mousewheel(canvas, canvas)


def _section(host: tk.Misc, parent: tk.Widget, key: str, title: str, subtitle: str) -> ttk.Frame:
    card = Card(parent, padding=8)
    card.pack(fill="x", padx=6, pady=(0, 8))
    SectionHeader(card.body, title, subtitle=subtitle).pack(fill="x", pady=(0, 6))
    host._advanced_sections[key] = card
    return card.body


def _build_field_extras(host: tk.Misc, parent: tk.Widget) -> None:
    frame = _section(
        host,
        parent,
        "fields",
        "Erweiterte Feldprüfung",
        "Regex-Gruppe gilt nur für den Test. Alle Felder werden gegen den geladenen PDF-Text geprüft.",
    )
    row = tk.Frame(frame)
    row.pack(fill="x", pady=(0, 4))
    tk.Label(row, text="Regex-Gruppe (nur Test)").pack(side="left")
    ttk.Combobox(
        row,
        textvariable=host.var_regex_group,
        values=["0", "1", "2", "3"],
        width=4,
        state="readonly",
    ).pack(side="left", padx=(4, 8))
    row2 = tk.Frame(frame)
    row2.pack(fill="x", pady=(0, 6))
    tk.Button(row2, text="Alle Felder testen", command=host.on_batch_regex_check).pack(side="left")
    tk.Button(row2, text="Ergebnisliste leeren", command=host._clear_regex_results).pack(side="left", padx=(6, 0))

    result_frame = tk.LabelFrame(frame, text="Ergebnisliste")
    result_frame.pack(fill="x", pady=(0, 2))
    host.tree_regex_results, regex_results_frame = create_scrollable_treeview(
        result_frame,
        columns=("field_name", "status", "regex", "result", "context"),
        show="headings",
        height=5,
        horizontal=True,
    )
    host.tree_regex_results.heading("field_name", text="Feldschlüssel")
    host.tree_regex_results.heading("status", text="Status")
    host.tree_regex_results.heading("regex", text="Erkennungsregel (Regex)")
    host.tree_regex_results.heading("result", text="Ergebnis")
    host.tree_regex_results.heading("context", text="Kontext (Auszug)")
    host.tree_regex_results.column("field_name", width=140, anchor="w")
    host.tree_regex_results.column("status", width=80, anchor="center")
    host.tree_regex_results.column("regex", width=220, anchor="w")
    host.tree_regex_results.column("result", width=180, anchor="w")
    host.tree_regex_results.column("context", width=280, anchor="w")
    regex_results_frame.pack(fill="x", padx=6, pady=6)
    host.tree_regex_results.bind("<<TreeviewSelect>>", host.on_regex_result_selected)


def _build_meta(host: tk.Misc, parent: tk.Widget) -> None:
    frame = _section(
        host,
        parent,
        "meta",
        "Regel- und Exportdetails",
        "Assay-Name und Exportnamen. Die Excel-Spaltenzuordnung wird im Feldeditor gepflegt und hier nur angezeigt.",
    )
    form = tk.Frame(frame)
    form.pack(fill="x", pady=(0, 6))
    form.columnconfigure(1, weight=1)
    labels = (
        (0, "Assay-Name", host.var_new_assay_name),
        (1, "Los-/Chargenkennung (Regex)", host.var_lot_regex),
        (2, "Ergebnisdateiname", host.var_excel_filename),
        (3, "Tabellenblattname", host.var_sheet_template),
    )
    for row, label, variable in labels:
        tk.Label(form, text=label).grid(row=row, column=0, sticky="w", pady=2)
        tk.Entry(form, textvariable=variable).grid(row=row, column=1, sticky="we", padx=(4, 0), pady=2)

    tk.Label(frame, text="Excel-Spaltenzuordnung").pack(anchor="w", pady=(2, 0))
    host.tree_cols, cols_frame = create_scrollable_treeview(
        frame,
        columns=("key", "column"),
        show="headings",
        height=6,
        horizontal=True,
    )
    host.tree_cols.heading("key", text="Feldschlüssel")
    host.tree_cols.heading("column", text="Excel-Spalte")
    host.tree_cols.column("key", width=220, anchor="w")
    host.tree_cols.column("column", width=320, anchor="w")
    cols_frame.pack(fill="x", pady=(2, 2))
    host.tree_cols.configure(selectmode="none")


def _build_validation(host: tk.Misc, parent: tk.Widget) -> None:
    frame = _section(
        host,
        parent,
        "validate",
        "Strukturprüfung und Änderungsnachweis",
        "Automatisches Speichern und die letzte Strukturprüfung. Prüfen und Änderungen anzeigen stehen in der Kopfzeile.",
    )
    actions = tk.Frame(frame)
    actions.pack(fill="x", pady=(0, 6))
    tk.Checkbutton(actions, text="Automatisch speichern (alle 45 s)", variable=host.var_autosave).pack(side="left")
    tk.Label(actions, text="Zuletzt automatisch gespeichert").pack(side="left", padx=(12, 4))
    tk.Label(actions, textvariable=host.var_last_autosave).pack(side="left")

    val_frame = tk.LabelFrame(frame, text="Ergebnis der Strukturprüfung")
    val_frame.pack(fill="x", pady=(0, 2))
    host.list_validation, validation_frame = create_scrollable_listbox(val_frame, height=6)
    validation_frame.pack(fill="x", padx=6, pady=6)


def _build_log(host: tk.Misc, parent: tk.Widget) -> None:
    frame = _section(host, parent, "log", "Protokoll", "Meldungen zu Speichern, Strukturprüfung, Extraktionstest und Freigabe.")
    host.txt_log = tk.Text(frame, height=8, wrap="word")
    host.txt_log.pack(fill="x", pady=(0, 2))
