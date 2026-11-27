"""Inventar/Landing des Rule Editors. Kein src-Import."""
from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

from interfaces.tk.scroll_helpers import TreeviewSorter, create_scrollable_treeview
from interfaces.tk.widgets.common import Card, SectionHeader
from .toolbar import _ActionFlow

_FILTERS = (
    ("active", "Aktiv"),
    ("draft", "Entwürfe"),
    ("inactive", "Inaktiv"),
    ("history", "Historie"),
    ("trash", "Papierkorb"),
)


def build_inventory_view(host: tk.Misc, parent: tk.Widget) -> None:
    outer = ttk.Frame(parent, style="Content.TFrame")
    outer.pack(fill="both", expand=True, padx=8, pady=8)
    card = Card(outer, padding=16, rounded=True)
    card.pack(fill="both", expand=True)
    container = card.body

    filters = ttk.Frame(container, style="CardInner.TFrame")
    host._inventory_filterbar = filters
    filters.pack(fill="x", pady=(0, 12))
    filters.columnconfigure(2, weight=1)
    filter_group = ttk.Frame(filters, style="CardInner.TFrame")
    stock_group = ttk.Frame(filters, style="CardInner.TFrame")
    search = ttk.Frame(filters, style="CardInner.TFrame")
    host._inventory_filter_group, host._inventory_stock_group, host._inventory_search_group = filter_group, stock_group, search
    for group, title in ((filter_group, "Filter"), (stock_group, "Bestand"), (search, "Suche")):
        ttk.Label(group, text=title, style="RuleSuite.FilterCaption.TLabel").grid(row=0, column=0, sticky="nsw", padx=(0, 8))

    # Keep the normal Button API and the existing disclosure callback. A native
    # image remains visible when the cached count updates the button's text.
    host._inventory_dropdown_icon = tk.PhotoImage(master=host, width=14, height=8)
    for row, left, right in ((1, 4, 13), (2, 5, 12), (3, 6, 11), (4, 7, 10), (5, 8, 9)):
        host._inventory_dropdown_icon.put("#365571", to=(left, row, right, row + 1))
    host.btn_inventory_states = ttk.Button(filter_group, text="Zustände · 5", command=host._toggle_inventory_states,
        image=host._inventory_dropdown_icon, compound="right", style="Filter.RuleSuite.Secondary.TButton", width=0)
    host.btn_inventory_states.grid(row=0, column=1, sticky="nsew", padx=(0, 6))
    reset = ttk.Button(filter_group, text="Filter löschen", command=host._clear_inventory_filters, style="Filter.RuleSuite.Ghost.TButton", width=0)
    reset.grid(row=0, column=2, sticky="nsew")
    refresh = ttk.Button(stock_group, text="Aktualisieren", command=host._refresh_ruleset_overview, style="Filter.RuleSuite.Secondary.TButton", width=0)
    refresh.grid(row=0, column=1, sticky="nsew", padx=(0, 6))
    integrity = ttk.Button(stock_group, text="Integrität prüfen", command=host._request_inventory_integrity, style="Filter.RuleSuite.Secondary.TButton", width=0)
    integrity.grid(row=0, column=2, sticky="nsew")
    search.columnconfigure(1, weight=1)
    host._inventory_search_entry = ttk.Entry(search, textvariable=host.var_inventory_search, width=1,
        font=("Segoe UI", 9), style="RuleSuite.Filter.TEntry")
    host._inventory_search_entry.grid(row=0, column=1, sticky="nsew", padx=(0, 8))
    host._inventory_search_button = ttk.Button(search, text="Suchen", command=host._on_inventory_filter_changed,
        style="Filter.RuleSuite.Secondary.TButton", width=0)
    host._inventory_search_button.grid(row=0, column=2, sticky="nsew")
    control_widgets = (host.btn_inventory_states, reset, refresh, integrity, host._inventory_search_entry, host._inventory_search_button)
    layout_state = {"key": None}

    def fit_filters(event=None):
        width = filters.winfo_width()
        height = max(widget.winfo_reqheight() for widget in control_widgets)
        required = filter_group.winfo_reqwidth() + stock_group.winfo_reqwidth() + 320 + 32
        key = width, height, required
        if width < 20 or key == layout_state["key"]:
            return
        layout_state["key"] = key
        for group in (filter_group, stock_group, search):
            group.rowconfigure(0, minsize=height)
        filter_group.grid(row=0, column=0, sticky="nw", padx=(0, 16))
        stock_group.grid(row=0, column=1, sticky="nw", padx=(0, 16))
        if width >= required:
            search.grid(row=0, column=2, columnspan=1, sticky="nsew", pady=0)
        else:
            search.grid(row=1, column=0, columnspan=3, sticky="nsew", pady=(10, 0))
    filters.bind("<Configure>", fit_filters)

    host.inventory_state_options = _ActionFlow(container)
    host._inventory_states_open = False
    for kind, label in _FILTERS:
        checkbox = ttk.Checkbutton(
            host.inventory_state_options,
            text=label,
            variable=host.inventory_filter_vars[kind],
            command=host._on_inventory_filter_changed,
        )
        host.inventory_state_options.add_widget(checkbox)

    actions = _ActionFlow(container)
    host.inventory_selection_actions = actions
    host.btn_inventory_primary = actions.add("Regel auswählen", host.on_inventory_primary_action, style="RuleSuite.Primary.TButton")
    host.btn_inventory_more = actions.add("Weitere Aktionen", host.on_inventory_more_actions)
    host.btn_inventory_discard = actions.add("Entwurf verwerfen", host.on_discard_selected_draft, style="RuleSuite.Danger.TButton")
    actions.set_visible(host.btn_inventory_discard, False)

    host.tree_rulesets, host.inventory_tree_frame = create_scrollable_treeview(
        container,
        columns=("type", "key", "name", "fields", "modified", "status"),
        displaycolumns=("type", "name", "fields", "modified", "status"),
        show="headings",
        height=14,
        horizontal=True,
        autohide=True,
    )
    ruleset_headings = {
        "type": "Zustand",
        "key": "Assay-Schlüssel",
        "name": "Assay",
        "fields": "Feldzahl",
        "modified": "Änderungszeit",
        "status": "Prüfung",
    }
    host.tree_rulesets.column("type", width=110, anchor="w")
    host.tree_rulesets.column("key", width=140, anchor="w")
    host.tree_rulesets.column("name", width=220, anchor="w")
    host.tree_rulesets.column("fields", width=80, anchor="center")
    host.tree_rulesets.column("modified", width=170, anchor="w")
    host.tree_rulesets.column("status", width=220, anchor="w")
    host._tree_rulesets_sorter = TreeviewSorter(host.tree_rulesets, numeric_columns=("fields",))
    host._tree_rulesets_sorter.attach(ruleset_headings)
    host.inventory_tree_frame.pack(fill="both", expand=True, pady=(0, 4))
    actions.pack(fill="x", pady=(8, 0))
    actions.pack_forget()
    host.tree_rulesets.bind("<<TreeviewSelect>>", host._sync_inventory_primary_button)
    host.tree_rulesets.bind("<Button-3>", host._show_inventory_context_menu)
    heading_font = tkfont.Font(host, font=ttk.Style(host).lookup("Treeview.Heading", "font"))
    def fit(event):
        compact = event.width < 900
        fields_width = max(60, heading_font.measure("Feldzahl") + 24) if compact else 60
        host.tree_rulesets.configure(displaycolumns=("type", "name", "fields", "status") if compact else ("type", "name", "fields", "modified", "status"))
        for column, width in (("type", 85), ("fields", fields_width), ("modified", 155), ("status", 120)):
            host.tree_rulesets.column(column, width=width, minwidth=width, stretch=False)
        fixed_width = 215 + fields_width if compact else 430
        host.tree_rulesets.column("name", width=max(160, event.width - fixed_width), minwidth=120, stretch=True)
    host.tree_rulesets.bind("<Configure>", fit)
