"""Globale Kopfzeile des Rule Editors. Kein src-Import."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from interfaces.tk.desktop_theme import COLOR_TEXT_MUTED
from interfaces.tk.widgets.common import StatusBadge


def build_toolbar(host: tk.Misc) -> None:
    bar = ttk.Frame(host, style="Header.TFrame")
    bar.pack(fill="x", padx=10, pady=(8, 0))

    title_row = ttk.Frame(bar, style="Header.TFrame")
    title_row.pack(fill="x")
    ttk.Label(title_row, text="Regelverwaltung", style="AppTitle.TLabel").pack(side="left")
    ttk.Label(
        title_row,
        text="Assay-Regeln aus PDF erstellen, prüfen und freigeben",
        style="AppSubtitle.TLabel",
    ).pack(side="left", padx=(12, 0))

    controls = ttk.Frame(bar, style="Header.TFrame")
    controls.pack(fill="x", pady=(6, 0))
    ttk.Label(controls, text="Arbeitsordner", style="AppSubtitle.TLabel").pack(side="left")
    tk.Entry(controls, textvariable=host.var_root, width=62, state="readonly").pack(side="left", padx=(6, 6))
    ttk.Button(controls, text="Arbeitsordner wählen …", command=host.on_pick_root).pack(side="left")
    ttk.Button(
        controls,
        text="Regel aus PDF erstellen oder prüfen …",
        style="Primary.TButton",
        command=host.open_step_by_step,
    ).pack(side="left", padx=(10, 0))
    host.lbl_status = StatusBadge(controls, "Bereit", kind="success")
    host.lbl_status.pack(side="right")

    hint = tk.Label(host, textvariable=host.var_hint, anchor="w", fg=COLOR_TEXT_MUTED)
    hint.pack(fill="x", padx=10, pady=(4, 4))
