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

    actions = ttk.Frame(header, style="Header.TFrame")
    actions.pack(fill="x", pady=(6, 0))
    _action_group(
        actions,
        "Bearbeiten",
        (
            ("Rückgängig", host.on_undo),
            ("Wiederholen", host.on_redo),
            ("Entwurf speichern", host.on_save_all),
        ),
    )
    _action_group(
        actions,
        "Prüfen",
        (
            ("Entwurf strukturell prüfen", host.on_validate),
            ("Extraktion mit PDF testen", host.on_preview),
        ),
    )
    _action_group(
        actions,
        "Freigeben",
        (
            ("Änderungen anzeigen", host.on_show_diff),
            ("Entwurf aktivieren", host.on_activate),
        ),
    )
    ttk.Button(actions, text="Regeldetails", command=host._toggle_advanced).pack(side="right")
    ttk.Button(actions, text="Zur Übersicht", command=lambda: host._show_page("inventory")).pack(side="right", padx=(0, 6))
