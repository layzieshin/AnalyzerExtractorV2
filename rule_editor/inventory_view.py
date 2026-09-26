"""Inventar/Landing des Rule Editors. Kein src-Import."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from interfaces.tk.scroll_helpers import TreeviewSorter, create_scrollable_treeview
from interfaces.tk.widgets.common import Card, SectionHeader

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
    card = Card(outer, padding=8)
    card.pack(fill="both", expand=True)
    container = card.body

    SectionHeader(
        container,
        "Assay-Regeln verwalten",
        subtitle="Regeln anlegen, öffnen und nach Zustand filtern. Mehrere Zustände können gleichzeitig sichtbar sein.",
    ).pack(fill="x", pady=(0, 6))

    filters = ttk.Frame(container, style="CardInner.TFrame")
    filters.pack(fill="x", pady=(0, 4))
    for kind, label in _FILTERS:
        tk.Checkbutton(
            filters,
            text=label,
            variable=host.inventory_filter_vars[kind],
            command=host._on_inventory_filter_changed,
        ).pack(side="left", padx=(0, 6))
    tk.Button(filters, text="Alle Zustände anzeigen", command=host._select_all_inventory_filters).pack(
        side="left", padx=(4, 8)
    )
    tk.Button(filters, text="Aktualisieren", command=host._refresh_ruleset_overview).pack(side="left")

    actions = ttk.Frame(container, style="CardInner.TFrame")
    actions.pack(fill="x", pady=(4, 6))
    ttk.Button(actions, text="Neue Regel aus PDF …", style="Primary.TButton", command=host.on_open_wizard).pack(
        side="left"
    )
    host.btn_inventory_primary = tk.Button(
        actions, text="Aktion für Auswahl", command=host.on_inventory_primary_action
    )
    host.btn_inventory_primary.pack(side="left", padx=(8, 0))
    host.btn_inventory_more = tk.Button(actions, text="Weitere Aktionen …", command=host.on_inventory_more_actions)
    host.btn_inventory_more.pack(side="left", padx=(8, 0))

    host.tree_rulesets, host.inventory_tree_frame = create_scrollable_treeview(
        container,
        columns=("type", "key", "name", "fields", "modified", "status"),
        show="headings",
        height=14,
        horizontal=True,
    )
    ruleset_headings = {
        "type": "Typ",
        "key": "Assay-Schlüssel",
        "name": "Assay-Name",
        "fields": "Feldzahl",
        "modified": "Änderungszeit",
        "status": "Status",
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
    host.tree_rulesets.bind("<<TreeviewSelect>>", host._sync_inventory_primary_button)
    host.tree_rulesets.bind("<Button-3>", host._show_inventory_context_menu)
