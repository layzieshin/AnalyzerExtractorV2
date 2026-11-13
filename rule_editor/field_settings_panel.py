"""Rechte Workspace-Spalte: sichtbare Feldeinstellungen. Kein src-Import."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from interfaces.tk.desktop_theme import COLOR_TEXT_MUTED
from interfaces.tk.widgets.common import SectionHeader, ScrollableFrame

from rule_editor.field_actions import SEARCH_MODE_LABELS


def build_field_settings_panel(host: tk.Misc, parent: tk.Widget) -> None:
    parent.columnconfigure(0, weight=1)
    parent.rowconfigure(0, weight=1)
    scroll = ScrollableFrame(parent)
    scroll.grid(row=0, column=0, sticky="nsew")
    host.field_settings_scroll = scroll
    parent = scroll.body
    parent.columnconfigure(0, weight=1)
    parent.rowconfigure(8, weight=1)

    SectionHeader(
        parent,
        "Feld bearbeiten",
        subtitle="Anlegen oder Ersetzen speichert.",
    ).grid(row=0, column=0, sticky="ew", padx=2, pady=(0, 2))
    tk.Label(
        parent,
        textvariable=host.var_field_guidance,
        anchor="w",
        justify="left",
        wraplength=280,
        fg="#8a6d00",
    ).grid(row=1, column=0, sticky="ew", pady=(0, 4))

    form = tk.Frame(parent)
    form.grid(row=2, column=0, sticky="ew")
    form.columnconfigure(0, weight=1)
    tk.Label(form, text="Feldschlüssel").grid(row=0, column=0, sticky="w")
    tk.Entry(form, textvariable=host.var_field_key, name="field_key", width=1).grid(row=1, column=0, sticky="ew")
    tk.Label(form, text="Eindeutiger technischer Name", fg=COLOR_TEXT_MUTED).grid(row=2, column=0, sticky="w")
    tk.Label(form, text="Erkennungsregel (Regex)").grid(row=3, column=0, sticky="w", pady=(4, 0))
    host.ent_field_regex = tk.Entry(form, textvariable=host.var_field_regex, name="field_regex", width=1)
    host.ent_field_regex.grid(row=4, column=0, sticky="ew")
    host.ent_marking_regex = host.ent_field_regex
    tk.Button(form, text="Regex-Bibliothek …", command=lambda: host.on_open_regex_library(host.ent_field_regex)).grid(row=5, column=0, sticky="ew", pady=2)
    tk.Label(form, text="Excel-Ausgabespalte").grid(row=6, column=0, sticky="w", pady=(4, 0))
    tk.Entry(form, textvariable=host.var_field_excel_column, name="field_excel", width=1).grid(row=7, column=0, sticky="ew")
    tk.Checkbutton(form, text="In die Dublettenprüfung einbeziehen", variable=host.var_field_dedupe,
        wraplength=230, justify="left").grid(row=8, column=0, sticky="w", pady=4)

    tk.Label(
        parent,
        textvariable=host.var_marking_selection,
        anchor="w",
        justify="left",
        wraplength=280,
        fg="#333",
    ).grid(row=3, column=0, sticky="ew", pady=(6, 2))

    pattern_row = tk.Frame(parent)
    pattern_row.grid(row=4, column=0, sticky="ew")
    tk.Button(pattern_row, text="Muster aus Markierung", command=host.on_marking_regex_from_selection).pack(fill="x")
    tk.Button(pattern_row, text="Baustein …", command=host.on_open_regex_builder).pack(fill="x", pady=2)

    search = tk.Frame(parent)
    search.grid(row=5, column=0, sticky="ew", pady=(6, 0))
    search.columnconfigure(0, weight=1)
    tk.Label(search, text="Suchbereich").grid(row=0, column=0, sticky="w")
    host.cmb_search_mode = ttk.Combobox(
        search,
        textvariable=host.var_search_mode_label,
        values=list(SEARCH_MODE_LABELS.values()),
        width=1,
        state="readonly",
        name="field_search_mode",
    )
    host.cmb_search_mode.grid(row=1, column=0, sticky="ew")
    tk.Label(search, text="Textmarker").grid(row=2, column=0, sticky="w", pady=(4, 0))
    host.ent_search_after = tk.Entry(search, textvariable=host.var_search_after, name="field_search_after")
    host.ent_search_after.grid(row=3, column=0, sticky="ew")
    tk.Label(search, text="Zeilennummer").grid(row=4, column=0, sticky="w", pady=(4, 0))
    host.ent_search_line = tk.Entry(search, textvariable=host.var_search_line, width=8, name="field_search_line")
    host.ent_search_line.grid(row=5, column=0, sticky="w")

    search_actions = tk.Frame(parent)
    search_actions.grid(row=6, column=0, sticky="ew", pady=(6, 0))
    search_actions.columnconfigure(0, weight=1)
    tk.Button(search_actions, text="Ab markierter Zeile", command=host.on_marking_set_search_line).grid(
        row=0, column=0, sticky="ew", padx=(0, 2)
    )
    tk.Button(
        search_actions,
        text="Ab vorheriger Zeile",
        command=host.on_marking_set_search_after_prev_line,
    ).grid(row=1, column=0, sticky="ew", pady=2)
    tk.Button(
        search_actions,
        text="Ab markiertem Text",
        command=host.on_marking_set_search_after_selection,
    ).grid(row=2, column=0, sticky="ew", pady=2)

    actions = tk.Frame(parent)
    actions.grid(row=7, column=0, sticky="ew", pady=(8, 0))
    actions.columnconfigure(0, weight=1)
    host.btn_field_commit = tk.Button(
        actions,
        text="Markiertes Feld ersetzen",
        state=tk.DISABLED,
        command=host._commit_replace_field,
    )
    host.btn_field_commit.grid(row=0, column=0, sticky="ew", padx=2, pady=2)
    tk.Button(actions, text="Bearbeitung abbrechen", command=host.on_cancel_field_edit).grid(
        row=1, column=0, sticky="ew", padx=2, pady=2
    )
    tk.Button(actions, text="Regex testen", command=host.on_test_regex).grid(row=2, column=0, sticky="ew", padx=2, pady=2)
    tk.Button(actions, text="Im Bericht zeigen", command=host.on_goto_field_marking).grid(
        row=3, column=0, sticky="ew", padx=2, pady=2
    )

    preview = tk.LabelFrame(parent, text="Regex-Testtreffer")
    preview.grid(row=8, column=0, sticky="nsew", pady=(8, 4))
    preview.rowconfigure(0, weight=1)
    preview.columnconfigure(0, weight=1)
    host.txt_field_preview = tk.Text(preview, wrap="word", height=6)
    host.txt_field_preview.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
    host.txt_field_preview.tag_config("hit", background="#f7d774")
    host.txt_field_preview.configure(state="disabled")
    host.txt_marking_regex_preview = None
    host._sync_search_inputs()
