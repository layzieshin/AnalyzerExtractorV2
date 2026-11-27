"""The single field/marking grid; raw keys remain the selection identity."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, font
from interfaces.tk.scroll_helpers import create_scrollable_treeview
from .toolbar import _ActionFlow


def build_field_list_panel(host, parent):
    parent.rowconfigure(2, weight=1)
    parent.columnconfigure(0, weight=1)
    head = ttk.Frame(parent, style="CardInner.TFrame")
    head.grid(row=0, column=0, sticky="ew", pady=(0, 8))
    ttk.Label(head, text="REGELSTRUKTUR", style="Eyebrow.TLabel").pack(anchor="w")
    host.lbl_field_list_title = ttk.Label(head, text="Felder & Markierungen", style="ToolbarTitle.TLabel", wraplength=210)
    host.lbl_field_list_title.pack(anchor="w")
    ttk.Label(head, textvariable=host.var_field_count, style="Muted.TLabel").pack(anchor="w", pady=(3, 0))
    tools = ttk.Frame(parent, style="CardInner.TFrame")
    host.frame_marking_panel = tools
    tools.grid(row=1, column=0, sticky="ew", pady=(0, 6))
    tools.columnconfigure(0, weight=1)
    host.var_marking_mode = tk.StringVar(master=host, value="Alle markieren")
    host.cmb_marking_mode = ttk.Combobox(tools, textvariable=host.var_marking_mode, state="readonly", width=1,
        values=("Alle markieren", "Alle ausblenden", "Nur Treffer", "Nur aktives Feld"))
    host.cmb_marking_mode.grid(row=0, column=0, sticky="ew", padx=(0, 4))
    def visibility(_event=None):
        {"Alle markieren": lambda: host._set_all_markings_visible(True),
         "Alle ausblenden": lambda: host._set_all_markings_visible(False),
         "Nur Treffer": host._show_only_matched_markings,
         "Nur aktives Feld": host._show_only_active_marking}[host.var_marking_mode.get()]()
    host.cmb_marking_mode.bind("<<ComboboxSelected>>", visibility)
    host.btn_toggle_markings = ttk.Button(tools, text="↻", command=host._render_field_markings, style="Field.RuleSuite.Secondary.TButton", width=0)
    host.btn_toggle_markings.grid(row=0, column=1)
    style = ttk.Style(host)
    style.configure("RuleFields.Treeview", rowheight=font.Font(root=host, font=("Segoe UI", 9)).metrics("linespace") * 2 + 10, font=("Segoe UI", 9))
    host.tree_fields, frame = create_scrollable_treeview(parent, columns=("key", "regex", "search_from", "status"),
        displaycolumns=("status",), show="tree", height=5, horizontal=False, autohide=True, style="RuleFields.Treeview", selectmode="browse")
    tree = host.tree_fields
    for key, label in (("key", "Feldschlüssel"), ("regex", "Suchmuster (Regex)"), ("search_from", "Suchbereich"), ("status", "Status")):
        tree.heading(key, text=label, command="")
    tree.column("#0", width=155, minwidth=75, stretch=True)
    tree.column("status", width=48, minwidth=42, stretch=False, anchor="e")
    frame.grid(row=2, column=0, sticky="nsew")
    tree.bind("<<TreeviewSelect>>", host.on_field_selected)
    host._unified_field_grid = True
    host._marking_panel_visible = True
    host.tree_marking_legend = None
    def click(event):
        item = tree.identify_row(event.y)
        box = tree.bbox(item, "#0") if item else ()
        if box and tree.identify_column(event.x) == "#0" and event.x < box[0] + 23:
            host.toggle_field_marking(str(tree.item(item, "values")[0]))
            return "break"
    tree.bind("<Button-1>", click, add="+")
    tree.bind("<space>", lambda _event: host.toggle_field_marking(str(tree.item(tree.selection()[0], "values")[0])) or "break" if tree.selection() else "break")
    parent.bind("<Configure>", lambda event: host.lbl_field_list_title.configure(wraplength=max(110, event.width)), add="+")
    actions = _ActionFlow(parent)
    host.field_list_actions = actions
    actions.grid(row=3, column=0, sticky="ew", pady=(6, 0))
    for label, command in (("Neu", host.on_begin_new_field), ("Duplizieren", host.on_duplicate_field),
                           ("↑", lambda: host.on_move_field("up")), ("↓", lambda: host.on_move_field("down")),
                           ("Löschen", host.on_remove_field)):
        actions.add(label, command, style="Field.RuleSuite.Danger.TButton" if label == "Löschen" else "Field.RuleSuite.Secondary.TButton", width=0)
