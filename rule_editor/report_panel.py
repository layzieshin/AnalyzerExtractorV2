"""Mittlere Workspace-Spalte: PDF-Testbericht und Markierungslegende. Kein src-Import."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from interfaces.tk.scroll_helpers import create_scrollable_treeview
from interfaces.tk.widgets.common import SectionHeader


def build_report_panel(host: tk.Misc, parent: tk.Widget) -> None:
    parent.rowconfigure(1, weight=1)
    parent.columnconfigure(0, weight=1)

    controls = tk.Frame(parent)
    controls.grid(row=0, column=0, sticky="ew", pady=(0, 4))
    controls.columnconfigure(1, weight=1)
    SectionHeader(
        controls,
        "PDF-Testbericht",
        subtitle="PDF laden, Text markieren und Treffer der Extraktionsfelder prüfen.",
    ).grid(row=0, column=0, columnspan=3, sticky="ew")
    tk.Label(controls, text="Test-PDF").grid(row=1, column=0, sticky="w", pady=(4, 0))
    tk.Entry(controls, textvariable=host.var_pdf).grid(row=1, column=1, sticky="ew", padx=(4, 6), pady=(4, 0))
    tk.Button(controls, text="PDF auswählen …", command=host.on_pick_pdf).grid(row=1, column=2, sticky="e", pady=(4, 0))
    tk.Button(controls, text="PDF-Text laden", command=host.on_load_text).grid(row=2, column=0, sticky="w", pady=(4, 0))
    host.btn_toggle_markings = tk.Button(
        controls,
        text="Markierungen ausblenden",
        command=host._toggle_marking_panel,
    )
    host.btn_toggle_markings.grid(row=2, column=1, columnspan=2, sticky="e", pady=(4, 0))

    text_wrap = tk.Frame(parent)
    text_wrap.grid(row=1, column=0, sticky="nsew", pady=(0, 4))
    text_wrap.rowconfigure(0, weight=1)
    text_wrap.columnconfigure(0, weight=1)
    host.txt_block = tk.Text(text_wrap, wrap="word")
    block_scroll = ttk.Scrollbar(text_wrap, orient="vertical", command=host.txt_block.yview)
    host.txt_block.configure(yscrollcommand=block_scroll.set)
    host.txt_block.grid(row=0, column=0, sticky="nsew")
    block_scroll.grid(row=0, column=1, sticky="ns")
    host.txt_block.tag_config("hit", background="#f7d774")
    host.txt_block.tag_config("field_emphasis", background="#ffd000")
    host.txt_block.bind("<<Selection>>", host._on_block_selection_changed)

    host.frame_marking_panel = tk.Frame(parent)
    host.frame_marking_panel.grid(row=2, column=0, sticky="ew", pady=(0, 2))
    host.frame_marking_panel.columnconfigure(0, weight=1)

    ttk.Label(host.frame_marking_panel, text="Markierungen", style="SectionTitle.TLabel").grid(
        row=0, column=0, sticky="w", pady=(0, 2)
    )
    marking_row = tk.Frame(host.frame_marking_panel)
    marking_row.grid(row=1, column=0, sticky="ew")
    for column in range(3):
        marking_row.columnconfigure(column, weight=1)
    marking_buttons = (
        ("Markierungen aktualisieren", host._render_field_markings),
        ("Alle Markierungen zeigen", lambda: host._set_all_markings_visible(True)),
        ("Alle Markierungen ausblenden", lambda: host._set_all_markings_visible(False)),
        ("Nur Treffer zeigen", host._show_only_matched_markings),
        ("Nur aktives Feld zeigen", host._show_only_active_marking),
        ("Sichtbarkeit umschalten", host._toggle_selected_marking_visibility),
    )
    for index, (label, command) in enumerate(marking_buttons):
        tk.Button(marking_row, text=label, command=command).grid(
            row=index // 3, column=index % 3, sticky="ew", padx=2, pady=2
        )

    tk.Label(
        host.frame_marking_panel,
        textvariable=host.var_marking_status,
        anchor="w",
        justify="left",
        wraplength=420,
        fg="#444",
    ).grid(row=2, column=0, sticky="ew", pady=(4, 2))

    legend_frame = tk.LabelFrame(host.frame_marking_panel, text="Extraktionsfelder und Treffer")
    legend_frame.grid(row=3, column=0, sticky="ew")
    host.tree_marking_legend, marking_legend_frame = create_scrollable_treeview(
        legend_frame,
        columns=("status", "visible", "value"),
        show="tree headings",
        height=5,
        horizontal=True,
    )
    host.tree_marking_legend.heading("#0", text="Feld")
    host.tree_marking_legend.heading("status", text="Status")
    host.tree_marking_legend.heading("visible", text="Sichtbar")
    host.tree_marking_legend.heading("value", text="Ergebnis")
    host.tree_marking_legend.column("#0", width=120, anchor="w")
    host.tree_marking_legend.column("status", width=90, anchor="center")
    host.tree_marking_legend.column("visible", width=70, anchor="center")
    host.tree_marking_legend.column("value", width=160, anchor="w")
    marking_legend_frame.pack(fill="x", padx=6, pady=6)
    host.tree_marking_legend.bind("<<TreeviewSelect>>", host.on_marking_legend_selected)
