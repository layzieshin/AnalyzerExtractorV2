"""Globale Kopfzeile des Rule Editors. Kein src-Import."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from interfaces.tk.desktop_theme import COLOR_BG, COLOR_TEXT_MUTED
from interfaces.tk.widgets.common import StatusBadge


def _configure_button_styles(master) -> None:
    """RuleSuite-only button roles; leave the shared product theme untouched."""
    style = ttk.Style(master)
    for role, background, foreground, border in (
        ("Secondary", "#ffffff", "#21486f", "#c5d7eb"),
        ("Primary", "#175ba4", "#ffffff", "#175ba4"),
        ("Ghost", "#ffffff", "#365571", "#ffffff"),
        ("NavGhost", COLOR_BG, "#365571", COLOR_BG),
        ("Danger", "#ffffff", "#a93c42", "#e7bec2"),
        ("Selected", "#eaf3fd", "#175ba4", "#9bc1ed"),
    ):
        name = f"RuleSuite.{role}.TButton"
        style.configure(name, font=("Segoe UI", 9, "bold" if role == "Primary" else "normal"),
            padding=(9, 5), background=background, foreground=foreground, bordercolor=border,
            lightcolor=border, darkcolor=border, borderwidth=1, relief="solid",
            focuscolor="#ffffff" if role == "Primary" else "#175ba4", focusthickness=1)
        style.map(name, background=[("disabled", "#f3f6fa"), ("active", "#134a83" if role == "Primary" else "#eef5fd")],
            foreground=[("disabled", "#8b9bad"), ("!disabled", foreground)],
            bordercolor=[("disabled", "#e0e7ef"), ("focus", "#175ba4"), ("active", "#8bb2df")],
            lightcolor=[("focus", "#175ba4"), ("active", "#8bb2df")],
            darkcolor=[("focus", "#175ba4"), ("active", "#8bb2df")])
    for role in ("Secondary", "Danger"):
        style.configure(f"Field.RuleSuite.{role}.TButton", padding=(5, 3), font=("Segoe UI", 9))
    for role in ("Secondary", "Ghost"):
        style.configure(f"Filter.RuleSuite.{role}.TButton", padding=(8, 5),
            bordercolor="#d4e0ec" if role == "Secondary" else "#ffffff",
            lightcolor="#ffffff", darkcolor="#ffffff", borderwidth=1)
    style.configure("RuleSuite.Filter.TEntry", padding=(8, 6), fieldbackground="#ffffff",
        bordercolor="#d4e0ec", lightcolor="#ffffff", darkcolor="#ffffff", borderwidth=1)
    style.map("RuleSuite.Filter.TEntry", bordercolor=[("focus", "#8bb2df")])
    style.configure("RuleSuite.FilterCaption.TLabel", font=("Segoe UI", 9),
        background="#ffffff", foreground="#60758c")
    style.configure("RuleWorkplace.Title.TLabel", font=("Segoe UI", 16, "bold"), background=COLOR_BG, foreground="#16293c")
    style.configure("Doc.RuleSuite.Secondary.TButton", font=("Segoe UI", 9), padding=(5, 3))
    style.configure("Doc.RuleSuite.Selected.TButton", font=("Segoe UI", 9), padding=(5, 3))


class _ActionFlow(ttk.Frame):
    """Small, local native toolbar that wraps measured controls without clipping."""
    def __init__(self, parent, *, style="CardInner.TFrame"):
        super().__init__(parent, style=style)
        self._controls = []
        self._hidden_controls = set()
        self._layout_key = None
        self.bind("<Configure>", self._layout)

    def add(self, text, command, *, style="RuleSuite.Secondary.TButton", width=None):
        style = {"Toolbar.TButton": "RuleSuite.Secondary.TButton", "Compact.Primary.TButton": "RuleSuite.Primary.TButton"}.get(style, style)
        button = ttk.Button(self, text=text, command=command, style=style, **({"width": width} if width is not None else {}))
        self.add_widget(button)
        return button

    def add_widget(self, widget):
        self._controls.append(widget)
        widget.grid(row=0, column=len(self._controls) - 1, padx=(0, 6), pady=3, sticky="w")
        widget.bind("<Configure>", self._layout, add="+")

    def set_visible(self, widget, visible):
        if visible:
            self._hidden_controls.discard(widget)
        else:
            self._hidden_controls.add(widget)
            widget.place_forget()
            widget.grid_forget()
        self._layout_key = None
        self._layout()

    def _layout(self, _event=None):
        width = self.winfo_width()
        controls = [widget for widget in self._controls if widget not in self._hidden_controls]
        key = width, tuple((str(widget), widget.winfo_reqwidth(), widget.winfo_reqheight()) for widget in controls)
        if width < 10 or key == self._layout_key:
            return
        self._layout_key = key
        used = top = row_height = 0
        rows, row = [], []
        for widget, (_name, requested, height) in zip(controls, key[1]):
            needed = requested + 6
            if used and used + needed > width:
                rows.append((row, row_height))
                row = []
                used = row_height = 0
            row.append((widget, used, min(requested, width), height))
            used += needed
            row_height = max(row_height, height)
        if row:
            rows.append((row, row_height))
        for row, row_height in rows:
            for widget, left, requested, height in row:
                widget.place(x=left, y=top + (row_height - height) // 2, width=requested, height=height)
            top += row_height + 6
        self.configure(height=max(1, top - 6))


def build_toolbar(host: tk.Misc) -> None:
    _configure_button_styles(host)
    bar = ttk.Frame(host, style="Content.TFrame")
    host.rule_toolbar = bar
    bar.pack(fill="x", padx=12, pady=(12, 4))
    eyebrow = ttk.Label(bar, text="INTEGRIERTE RULESUITE", style="Eyebrow.TLabel")
    host.rule_toolbar_eyebrow = eyebrow
    eyebrow.pack(anchor="w")
    host.var_workspace_title = tk.StringVar(master=host, value="Regelwerke")
    host.var_workspace_subtitle = tk.StringVar(master=host, value="Regeln erstellen, prüfen und ausdrücklich aktivieren")
    title_row = ttk.Frame(bar, style="Content.TFrame")
    host.rule_title_row = title_row
    host.rule_breadcrumb = ttk.Label(bar, text="Analyzer  /  Regelwerke  /  Direkter Editor", style="PageSubtitle.TLabel")
    title_row.pack(fill="x", pady=(4, 0))
    title_row.columnconfigure(0, weight=1)
    host.lbl_loaded_assay_name = ttk.Label(title_row, textvariable=host.var_workspace_title, style="PageTitle.TLabel")
    host.lbl_loaded_assay_name.grid(row=0, column=0, sticky="w")
    host.lbl_status = StatusBadge(title_row, "Bereit", kind="success")
    host.lbl_status.grid(row=0, column=2, sticky="e", padx=(10, 0))
    host.btn_inventory_new = ttk.Button(title_row, text="Neue Regel aus PDF", style="RuleSuite.Primary.TButton", command=host.on_open_wizard)
    host.btn_inventory_new.grid(row=1, column=1, sticky="e", padx=(10, 0))
    host.lbl_status.configure(background=COLOR_BG)
    host.lbl_editor_subtitle = ttk.Label(title_row, textvariable=host.var_workspace_subtitle, style="PageSubtitle.TLabel")
    host.lbl_editor_subtitle.grid(row=1, column=0, sticky="w", pady=(2, 0))
    host.editor_navigation = _ActionFlow(title_row, style="Content.TFrame")
    host.btn_editor_back = host.editor_navigation.add("← Zur Übersicht", lambda: host._leave_editor_for_later(), style="RuleSuite.NavGhost.TButton")
    host.editor_navigation.add("Geführter Modus", host.open_step_by_step)
    if not getattr(host, "_embedded", False):
        controls = ttk.Frame(bar, style="Content.TFrame")
        host.rule_root_controls = controls
        controls.pack(fill="x", pady=(6, 0))
        controls.columnconfigure(1, weight=1)
        ttk.Label(controls, text="Arbeitsordner", style="PageSubtitle.TLabel").grid(row=0, column=0, sticky="w")
        tk.Entry(controls, textvariable=host.var_root, state="readonly", width=24).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(controls, text="Wählen …", command=host.on_pick_root, style="Toolbar.TButton").grid(row=0, column=2)
    host.editor_hint = ttk.Label(host, textvariable=host.var_hint, style="PageSubtitle.TLabel", width=1, wraplength=0)
    host.editor_hint.pack(fill="x", padx=12, pady=(0, 4))
    fit_state = {"compact": None}
    def fit(event):
        compact = event.width < 1000
        nav_width = sum(widget.winfo_reqwidth() + 6 for widget in host.editor_navigation._controls)
        host.editor_navigation.configure(width=nav_width)
        aside = nav_width if getattr(host, "_active_page", "inventory") == "workspace" else host.btn_inventory_new.winfo_reqwidth()
        host.lbl_loaded_assay_name.configure(style="RuleWorkplace.Title.TLabel" if getattr(host, "_active_page", "inventory") == "workspace" else "CompactPageTitle.TLabel" if compact else "PageTitle.TLabel",
            wraplength=max(180, event.width - aside - host.lbl_status.winfo_reqwidth() - 20))
        host.lbl_editor_subtitle.configure(wraplength=max(180, event.width - aside - 30))
        if compact != fit_state["compact"]:
            fit_state["compact"] = compact
            bar.pack_configure(pady=(5, 2) if compact else (12, 4))
            title_row.pack_configure(pady=(0, 0) if compact else (4, 0))
            if compact or getattr(host, "_active_page", "inventory") == "workspace":
                eyebrow.pack_forget()
            else:
                eyebrow.pack(anchor="w", before=title_row)
    bar.bind("<Configure>", fit, add="+")
