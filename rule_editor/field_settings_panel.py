"""Rechte Workspace-Spalte: sichtbare Feldeinstellungen. Kein src-Import."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from interfaces.tk.desktop_theme import COLOR_TEXT_MUTED
from interfaces.tk.widgets.common import SectionHeader

from rule_editor.field_actions import SEARCH_MODE_LABELS


def build_field_settings_panel(host: tk.Misc, parent: tk.Widget) -> None:
    parent.columnconfigure(0, weight=1)
    parent.rowconfigure(8, weight=1)

    SectionHeader(
        parent,
        "Feld bearbeiten",
        subtitle="Änderungen gelten erst nach Anlegen oder Ersetzen.",
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
    form.columnconfigure(1, weight=1)
    tk.Label(form, text="Feldschlüssel").grid(row=0, column=0, sticky="w")
    tk.Entry(form, textvariable=host.var_field_key, name="field_key").grid(row=0, column=1, sticky="we", padx=(4, 0))
    tk.Label(form, text="Eindeutiger technischer Name", fg=COLOR_TEXT_MUTED).grid(
        row=1, column=1, sticky="w", padx=(4, 0), pady=(0, 4)
    )
    tk.Label(form, text="Erkennungsregel (Regex)").grid(row=2, column=0, sticky="nw")
    host.ent_field_regex = tk.Entry(form, textvariable=host.var_field_regex, name="field_regex")
    host.ent_field_regex.grid(row=2, column=1, sticky="we", padx=(4, 0))
    host.ent_marking_regex = host.ent_field_regex
    tk.Button(
        form,
        text="Regex-Bibliothek …",
        command=lambda: host.on_open_regex_library(host.ent_field_regex),
    ).grid(row=2, column=2, sticky="w", padx=(4, 0))
    tk.Label(form, text="Excel-Ausgabespalte").grid(row=3, column=0, sticky="w", pady=(4, 0))
    tk.Entry(form, textvariable=host.var_field_excel_column, name="field_excel").grid(
        row=3, column=1, sticky="we", padx=(4, 0), pady=(4, 0)
    )
    tk.Checkbutton(
        form,
        text="In die Dublettenprüfung einbeziehen",
        variable=host.var_field_dedupe,
    ).grid(row=4, column=0, columnspan=3, sticky="w", pady=(4, 0))

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
    tk.Button(pattern_row, text="Muster aus Markierung", command=host.on_marking_regex_from_selection).pack(side="left")
    tk.Button(pattern_row, text="Baustein …", command=host.on_open_regex_builder).pack(side="left", padx=(6, 0))

    search = tk.Frame(parent)
    search.grid(row=5, column=0, sticky="ew", pady=(6, 0))
    search.columnconfigure(1, weight=1)
    tk.Label(search, text="Suchbereich").grid(row=0, column=0, sticky="w")
    host.cmb_search_mode = ttk.Combobox(
        search,
        textvariable=host.var_search_mode_label,
        values=list(SEARCH_MODE_LABELS.values()),
        width=22,
        state="readonly",
        name="field_search_mode",
    )
    host.cmb_search_mode.grid(row=0, column=1, sticky="w", padx=(4, 0))
    tk.Label(search, text="Textmarker").grid(row=1, column=0, sticky="w", pady=(4, 0))
    host.ent_search_after = tk.Entry(search, textvariable=host.var_search_after, name="field_search_after")
    host.ent_search_after.grid(row=1, column=1, sticky="we", padx=(4, 0), pady=(4, 0))
    tk.Label(search, text="Zeilennummer").grid(row=2, column=0, sticky="w", pady=(4, 0))
    host.ent_search_line = tk.Entry(search, textvariable=host.var_search_line, width=8, name="field_search_line")
    host.ent_search_line.grid(row=2, column=1, sticky="w", padx=(4, 0), pady=(4, 0))

    search_actions = tk.Frame(parent)
    search_actions.grid(row=6, column=0, sticky="ew", pady=(6, 0))
    search_actions.columnconfigure(0, weight=1)
    search_actions.columnconfigure(1, weight=1)
    tk.Button(search_actions, text="Ab markierter Zeile", command=host.on_marking_set_search_line).grid(
        row=0, column=0, sticky="ew", padx=(0, 2)
    )
    tk.Button(
        search_actions,
        text="Ab vorheriger Zeile",
        command=host.on_marking_set_search_after_prev_line,
    ).grid(row=0, column=1, sticky="ew", padx=(2, 0))
    tk.Button(
        search_actions,
        text="Ab markiertem Text",
        command=host.on_marking_set_search_after_selection,
    ).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 0))

    actions = tk.Frame(parent)
    actions.grid(row=7, column=0, sticky="ew", pady=(8, 0))
    actions.columnconfigure(0, weight=1)
    actions.columnconfigure(1, weight=1)
    host.btn_field_commit = tk.Button(
        actions,
        text="Markiertes Feld ersetzen",
        state=tk.DISABLED,
        command=host._commit_replace_field,
    )
    host.btn_field_commit.grid(row=0, column=0, sticky="ew", padx=2, pady=2)
    tk.Button(actions, text="Bearbeitung abbrechen", command=host.on_cancel_field_edit).grid(
        row=0, column=1, sticky="ew", padx=2, pady=2
    )
    tk.Button(actions, text="Regex testen", command=host.on_test_regex).grid(row=1, column=0, sticky="ew", padx=2, pady=2)
    tk.Button(actions, text="Im Bericht zeigen", command=host.on_goto_field_marking).grid(
        row=1, column=1, sticky="ew", padx=2, pady=2
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
