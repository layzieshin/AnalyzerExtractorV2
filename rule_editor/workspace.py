"""Arbeitsbereich: Kopfzeile und dreispaltiges Panedwindow. Kein src-Import."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from interfaces.tk.widgets.common import Card

from .advanced_view import build_advanced_view
from .field_list_panel import build_field_list_panel
from .field_settings_panel import build_field_settings_panel
from .report_panel import build_report_panel


def build_workspace(host: tk.Misc, parent: tk.Widget) -> None:
    parent.rowconfigure(1, weight=1)
    parent.columnconfigure(0, weight=1)

    header = ttk.Frame(parent, style="Header.TFrame")
    header.grid(row=0, column=0, sticky="ew", padx=8, pady=(4, 4))
    _build_header(host, header)

    body = ttk.Frame(parent, style="Content.TFrame")
    body.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
    body.rowconfigure(0, weight=1)
    body.columnconfigure(0, weight=1)
    host.workspace_body = body

    panes = ttk.Panedwindow(body, orient=tk.HORIZONTAL)
    host.workspace_panes = panes
    panes.grid(row=0, column=0, sticky="nsew")

    left = Card(panes, padding=6)
    middle = Card(panes, padding=6)
    right = Card(panes, padding=6)
    panes.add(left, weight=1)
    panes.add(middle, weight=3)
    panes.add(right, weight=2)

    build_field_list_panel(host, left.body)
    build_report_panel(host, middle.body)
    build_field_settings_panel(host, right.body)

    host.frame_advanced = ttk.Frame(body, style="Content.TFrame")
    build_advanced_view(host, host.frame_advanced)
    host.frame_advanced.grid(row=0, column=0, sticky="nsew")
    host.frame_advanced.grid_remove()
    host._advanced_visible = False
    _build_release_panel(host, parent)


def _action_group(parent: tk.Widget, title: str, buttons: tuple[tuple[str, object], ...]) -> None:
    box = ttk.Frame(parent, style="Header.TFrame")
    box.pack(side="left", padx=(0, 12))
    ttk.Label(box, text=title, style="AppSubtitle.TLabel").pack(side="left", padx=(0, 4))
    for text, command in buttons:
        ttk.Button(box, text=text, command=command).pack(side="left", padx=(2, 0))


def _build_header(host: tk.Misc, header: ttk.Frame) -> None:
    identity = ttk.Frame(header, style="Header.TFrame")
    identity.pack(fill="x")
    identity.columnconfigure(4, weight=1)
    ttk.Label(identity, text="Geladene Regel", style="AppSubtitle.TLabel").grid(row=0, column=0, sticky="w")
    ttk.Label(identity, text="Assay-Schlüssel", style="AppSubtitle.TLabel").grid(row=0, column=1, sticky="w", padx=(10, 0))
    host.lbl_loaded_assay_key = ttk.Label(identity, textvariable=host.var_new_assay_key, style="AppTitle.TLabel")
    host.lbl_loaded_assay_key.grid(row=0, column=2, sticky="w", padx=(4, 12))
    ttk.Label(identity, text="Assay-Name", style="AppSubtitle.TLabel").grid(row=0, column=3, sticky="w")
    host.lbl_loaded_assay_name = ttk.Label(identity, textvariable=host.var_new_assay_name, style="AppTitle.TLabel")
    host.lbl_loaded_assay_name.grid(row=0, column=4, sticky="ew", padx=(4, 0))

    editing = ttk.Frame(header, style="Header.TFrame")
    editing.pack(fill="x", pady=(6, 0))
    _action_group(editing, "Bearbeiten", (("Rückgängig", host.on_undo), ("Wiederholen", host.on_redo), ("Entwurf speichern", host.on_save_all)))
    ttk.Button(editing, text="Regeldetails", command=host._toggle_advanced).pack(side="right")
    ttk.Button(editing, text="Zur Übersicht", command=lambda: host._show_page("inventory")).pack(side="right", padx=(0, 6))
    technical = ttk.Frame(header, style="Header.TFrame")
    technical.pack(fill="x", pady=(4, 0))
    _action_group(technical, "Technische Hilfen", (("Entwurf strukturell prüfen", host.on_validate), ("Einzelne Extraktion testen", host.on_preview)))


def _build_release_panel(host, parent):
    frame = ttk.LabelFrame(parent, text="Freigabe des geladenen Entwurfs", padding=6)
    host.frame_release = frame
    frame.grid(row=2, column=0, sticky="ew", padx=8, pady=(0, 8))
    frame.columnconfigure(1, weight=1)
    ttk.Label(frame, textvariable=host.var_proof_status, wraplength=900).grid(row=0, column=0, columnspan=3, sticky="ew")
    for row, caption, variable, command in ((1, "Beispiel-/Problem-PDF", host.var_pdf, host.on_pick_pdf),
                                           (2, "Update-Referenz-PDF", host.var_reference_pdf, host.on_pick_reference_pdf)):
        ttk.Label(frame, text=caption).grid(row=row, column=0, sticky="w", pady=2)
        entry = ttk.Entry(frame, textvariable=variable, width=1)
        entry.grid(row=row, column=1, sticky="ew", padx=6)
        entry.bind("<FocusIn>", lambda _event: host._refresh_authoring_status())
        ttk.Button(frame, text="PDF auswählen …", command=command).grid(row=row, column=2, sticky="e")
    statuses = ttk.Frame(frame)
    statuses.grid(row=3, column=0, columnspan=3, sticky="ew", pady=3)
    for column, variable in enumerate((host.var_proof_structure, host.var_proof_example, host.var_proof_reference)):
        statuses.columnconfigure(column, weight=1, uniform="proof")
        ttk.Label(statuses, textvariable=variable, wraplength=290).grid(row=0, column=column, sticky="nw", padx=3)
    actions = ttk.Frame(frame)
    actions.grid(row=4, column=0, columnspan=3, sticky="ew", pady=3)
    host.btn_check_pdfs = ttk.Button(actions, text="Mit PDFs prüfen", style="Primary.TButton", command=host.on_check_pdfs)
    host.btn_check_pdfs.pack(side="left")
    ttk.Button(actions, text="Änderungen anzeigen", command=host.on_show_diff).pack(side="left", padx=6)
    ttk.Button(actions, text="Nachweis aktualisieren", command=host._refresh_authoring_status).pack(side="left")
    host.btn_activate = ttk.Button(actions, text="Aktivierung bestätigen", command=host.on_activate, state="disabled")
    host.btn_activate.pack(side="right")
    host.txt_proof_result = tk.Text(frame, height=3, wrap="word", state="disabled", font=("Segoe UI", 9))
    host.txt_proof_result.grid(row=5, column=0, columnspan=3, sticky="ew")
    host.txt_proof_result.bind("<FocusIn>", lambda _event: host._refresh_authoring_status())
