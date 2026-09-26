"""Linke Workspace-Spalte: Feldliste. Kein src-Import."""
from __future__ import annotations

import tkinter as tk

from interfaces.tk.scroll_helpers import create_scrollable_treeview
from interfaces.tk.widgets.common import SectionHeader


def build_field_list_panel(host: tk.Misc, parent: tk.Widget) -> None:
    parent.rowconfigure(1, weight=1)
    parent.columnconfigure(0, weight=1)
    SectionHeader(
        parent,
        "Extraktionsfelder",
        subtitle="Reihenfolge ist fest. Verschieben Sie Felder nur mit den Schaltflächen.",
    ).grid(row=0, column=0, sticky="ew", padx=2, pady=(0, 4))

    host.tree_fields, fields_frame = create_scrollable_treeview(
        parent,
        columns=("key", "regex", "search_from"),
        show="headings",
        height=12,
        horizontal=True,
    )
    field_headings = {
        "key": "Feldschlüssel",
        "regex": "Suchmuster (Regex)",
        "search_from": "Suchbereich",
    }
    host.tree_fields.column("key", width=140, anchor="w")
    host.tree_fields.column("regex", width=220, anchor="w")
    host.tree_fields.column("search_from", width=140, anchor="w")
    for column, title in field_headings.items():
        host.tree_fields.heading(column, text=title, command="")
    fields_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 4))
    host.tree_fields.bind("<<TreeviewSelect>>", host.on_field_selected)

    actions = tk.Frame(parent)
    actions.grid(row=2, column=0, sticky="ew", pady=(0, 2))
    for column in range(5):
        actions.columnconfigure(column, weight=1)
    buttons = (
        ("Neues Feld", host.on_begin_new_field),
        ("Duplizieren …", host.on_duplicate_field),
        ("Nach oben", lambda: host.on_move_field("up")),
        ("Nach unten", lambda: host.on_move_field("down")),
        ("Löschen …", host.on_remove_field),
    )
    for column, (label, command) in enumerate(buttons):
        tk.Button(actions, text=label, command=command).grid(row=0, column=column, sticky="ew", padx=1)
