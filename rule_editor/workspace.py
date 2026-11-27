"""One direct rule workplace: field grid, document, editing and existing actions."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from interfaces.tk.widgets.common import Card
from .advanced_view import build_advanced_view
from .field_list_panel import build_field_list_panel
from .field_settings_panel import build_field_settings_panel
from .report_panel import build_report_panel, build_authoring_result
from .toolbar import _ActionFlow


def build_workspace(host: tk.Misc, parent: tk.Widget) -> None:
    host.lbl_loaded_assay_key = host.lbl_editor_subtitle
    parent.rowconfigure(0, weight=1)
    parent.columnconfigure(0, weight=1)
    body = ttk.Frame(parent, style="Content.TFrame")
    body.grid(row=0, column=0, sticky="nsew", padx=8, pady=(0, 6))
    body.rowconfigure(0, weight=1)
    body.columnconfigure(0, weight=1)
    host.workspace_body = body
    host.workspace_scrollable = ttk.Frame(body, style="Content.TFrame")
    host.workspace_scrollable.grid(row=0, column=0, sticky="nsew")
    host.workspace_scrollable.rowconfigure(0, weight=1)
    host.workspace_scrollable.columnconfigure(0, weight=1)
    panes = ttk.Panedwindow(host.workspace_scrollable, orient=tk.HORIZONTAL)
    panes.grid(row=0, column=0, sticky="nsew")
    host.workspace_panes = panes
    left = Card(panes, padding=10, rounded=True)
    center = Card(panes, padding=0, rounded=True)
    right = ttk.Frame(panes, style="Content.TFrame")
    right.rowconfigure(1, weight=1)
    right.columnconfigure(0, weight=1)
    host._workspace_cards = left, center, right
    for card, weight in zip(host._workspace_cards, (20, 52, 28)):
        panes.add(card, weight=weight)
    build_field_list_panel(host, left.body)
    build_report_panel(host, center.body)
    test = Card(right, padding=10, rounded=True)
    test.grid(row=0, column=0, sticky="ew", pady=(0, 8))
    test_head = ttk.Frame(test.body, style="CardInner.TFrame")
    test_head.pack(fill="x")
    ttk.Button(test_head, text="Regelprüfung ▾", command=lambda: host._show_rule_results(toggle=True), style="RuleSuite.Ghost.TButton", width=0).pack(side="left")
    host.btn_rule_test = ttk.Button(test_head, text="Regel testen", command=host.on_preview, style="RuleSuite.Secondary.TButton", width=0)
    host.btn_rule_test.pack(side="right")
    build_authoring_result(host, test.body)
    host.authoring_values_frame.pack_forget()
    edit = Card(right, padding=10, rounded=True)
    edit.grid(row=1, column=0, sticky="nsew")
    build_field_settings_panel(host, edit.body)
    _build_functions(host, host.field_settings_scrollable.body)
    host._workspace_compact = False
    host._workspace_layout_key = None

    def layout(_event=None):
        width = panes.winfo_width()
        compact = width < 1100
        key = width, compact
        if width < 50 or key == host._workspace_layout_key:
            return
        host._workspace_layout_key = key
        host._workspace_compact = compact
        left_width = max(155, int(width * .20))
        right_width = max(260, int(width * (.32 if compact else .28)))
        panes.sashpos(0, left_width)
        panes.sashpos(1, max(left_width + 220, width - right_width))
    host._layout_editor_workspace = layout
    panes.bind("<Configure>", layout, add="+")
    host.frame_advanced = ttk.Frame(body, style="Content.TFrame")
    build_advanced_view(host, host.frame_advanced)
    host.frame_advanced.grid(row=0, column=0, sticky="nsew")
    host.frame_advanced.grid_remove()
    host._advanced_visible = False


def _build_functions(host, parent):
    functions = ttk.Frame(parent, style="CardInner.TFrame")
    functions.grid(row=13, column=0, sticky="ew", pady=(8, 0))
    host.editor_functions = functions
    flow = _ActionFlow(functions)
    host.editor_action_flow = flow
    flow.pack(fill="x")
    flow.add("Speichern", host.on_save_all)
    host.btn_rule_undo = flow.add("Rückgängig", host.on_undo)
    host.btn_rule_redo = flow.add("Wiederholen", host.on_redo)
    flow.add("Struktur prüfen", host.on_validate)
    flow.add("Änderungen vergleichen", host.on_show_diff)
    flow.add("Regeldetails", host._toggle_advanced)
    footer = _ActionFlow(functions)
    footer.pack(fill="x", pady=(6, 0))
    host.editor_footer_flow = footer
    host.btn_completion = footer.add("Abschluss prüfen", host._show_authoring_completion)
    footer.add("Später weiterbearbeiten", host._leave_editor_for_later)
    host.btn_draft_discard = footer.add("Entwurf verwerfen", host.on_discard_current_draft, style="RuleSuite.Danger.TButton")
    host.btn_activate = footer.add("Geprüfte Regel aktivieren", host.on_activate, style="RuleSuite.Primary.TButton")
    footer.set_visible(host.btn_activate, False)
    functions.grid_remove()
    def show_functions():
        if functions.winfo_manager():
            functions.grid_remove()
            disclosure.configure(text="▸ Funktionen")
        else:
            functions.grid()
            disclosure.configure(text="▾ Funktionen")
    host._toggle_editor_functions = show_functions
    disclosure = ttk.Button(parent, text="▸ Funktionen", command=show_functions, style="RuleSuite.Ghost.TButton")
    disclosure.grid(row=12, column=0, sticky="w", pady=(8, 0))
    host._bind_field_viewport(functions)
    host._bind_field_viewport(disclosure)
    ttk.Label(functions, textvariable=host.var_hint, style="Muted.TLabel", wraplength=260).pack(fill="x", pady=(6, 0))
