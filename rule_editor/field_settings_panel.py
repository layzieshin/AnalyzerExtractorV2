"""Right-hand field form; the document remains the full-height center pane."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from interfaces.tk.desktop_theme import COLOR_CARD, COLOR_TEXT_MUTED
from interfaces.tk.widgets.common import OverflowScrollbar, ScrollableFrame
from .field_actions import SEARCH_MODE_LABELS
from .toolbar import _ActionFlow


def build_field_settings_panel(host, parent):
    viewport = ScrollableFrame(parent, autohide=True)
    host.field_settings_scrollable = viewport
    viewport.pack(fill="both", expand=True)
    viewport._canvas.configure(background=COLOR_CARD)
    body = viewport.body
    body.columnconfigure(0, weight=1)
    ttk.Label(body, text="AUSGEWÄHLTES FELD", style="Eyebrow.TLabel").grid(row=0, column=0, sticky="w")
    ttk.Label(body, text="Feld bearbeiten", style="SectionTitle.TLabel").grid(row=1, column=0, sticky="w", pady=(2, 7))
    form = ttk.Frame(body, style="CardInner.TFrame")
    form.grid(row=2, column=0, sticky="ew")
    form.columnconfigure(0, weight=1)
    ttk.Label(form, text="Feldschlüssel").grid(row=0, column=0, sticky="w", pady=(0, 3))
    ttk.Entry(form, textvariable=host.var_field_key, name="field_key").grid(row=1, column=0, sticky="ew")
    ttk.Label(form, text="Erkennungsregel (Regex)").grid(row=2, column=0, sticky="w", pady=(8, 3))
    host.ent_field_regex = tk.Entry(form, textvariable=host.var_field_regex, name="field_regex", font=("Consolas", 10), relief="solid", borderwidth=1)
    host.ent_field_regex.grid(row=3, column=0, sticky="ew", ipady=10)
    host.ent_marking_regex = host.ent_field_regex
    host.btn_regex_builder = ttk.Button(body, text="Regex-Baukasten öffnen ↗", command=host.on_open_regex_builder, style="RuleSuite.Primary.TButton", width=0)
    host.btn_regex_builder.grid(row=3, column=0, sticky="ew", pady=(7, 0))
    actions = _ActionFlow(body)
    actions.grid(row=4, column=0, sticky="ew", pady=(4, 0))
    actions.add("Bibliothek", lambda: host.on_open_regex_library(host.ent_field_regex), width=0)
    actions.add("Muster aus Markierung", host.on_marking_regex_from_selection, width=0)
    test = _ActionFlow(body)
    test.grid(row=5, column=0, sticky="ew", pady=(4, 0))
    test.add("Regex testen", host.on_test_regex, width=0)
    test.add("Im Bericht zeigen", host.on_goto_field_marking, width=0)
    preview = ttk.Frame(body, style="CardInner.TFrame")
    preview.grid(row=10, column=0, sticky="ew", pady=(5, 0))
    preview.rowconfigure(0, weight=1)
    preview.columnconfigure(0, weight=1)
    host.txt_field_preview = tk.Text(preview, wrap="word", height=2, width=20, background=COLOR_CARD, relief="flat", font=("Consolas", 9))
    host.txt_field_preview.grid(row=0, column=0, sticky="nsew")
    scroll = OverflowScrollbar(preview, orient="vertical", command=host.txt_field_preview.yview)
    host.txt_field_preview.configure(yscrollcommand=scroll.set, state="disabled")
    host.txt_field_preview.tag_config("hit", background="#cdece0")
    host.txt_marking_regex_preview = None
    preview.grid_remove()
    summary = ttk.Frame(body, style="CardInner.TFrame")
    summary.grid(row=6, column=0, sticky="ew", pady=(4, 0))
    summary.columnconfigure(0, weight=1)
    host.var_regex_short = tk.StringVar(master=host, value="Noch nicht getestet")
    host.lbl_regex_short = ttk.Label(summary, textvariable=host.var_regex_short, foreground="#126854", wraplength=230)
    host.lbl_regex_short.grid(row=0, column=0, sticky="w")
    def details():
        preview.grid_remove() if preview.winfo_manager() else preview.grid()
    ttk.Button(summary, text="Details", command=details, style="RuleSuite.Ghost.TButton", width=0).grid(row=0, column=1, sticky="e")
    options = ttk.Frame(body, style="CardInner.TFrame")
    options.grid(row=8, column=0, sticky="ew")
    options.columnconfigure(1, weight=1)
    def toggle():
        visible = bool(options.winfo_manager())
        options.grid_remove() if visible else options.grid()
        disclosure.configure(text=("▸" if visible else "▾") + " Suchbereich und weitere Feldoptionen")
    disclosure = ttk.Button(body, text="▸ Suchbereich und weitere Feldoptionen", command=toggle, style="RuleSuite.Ghost.TButton", width=0)
    disclosure.grid(row=7, column=0, sticky="ew", pady=(6, 0))
    _build_options(host, options)
    options.grid_remove()
    commit = _ActionFlow(body)
    commit.grid(row=9, column=0, sticky="ew", pady=(6, 0))
    host.btn_field_commit = commit.add("Änderung anwenden", host.on_apply_field, style="RuleSuite.Primary.TButton", width=0)
    host.btn_field_replace = commit.add("Markiertes Feld ersetzen", host._commit_replace_field, width=0)
    commit.add("Abbrechen", host.on_cancel_field_edit, style="RuleSuite.Ghost.TButton", width=0)
    host.btn_field_commit.configure(state="disabled")
    host.btn_field_replace.configure(state="disabled")
    host._sync_search_inputs()
    def wheel(event):
        viewport._canvas.yview_scroll(-int(getattr(event, "delta", 0) / 120), "units")
        return "break"
    def reveal(event):
        if event.widget != event.widget.focus_get():
            return
        canvas = viewport._canvas
        relative = event.widget.winfo_rooty() - canvas.winfo_rooty()
        if relative >= -1 and relative + event.widget.winfo_height() <= canvas.winfo_height() + 1:
            return
        top = canvas.canvasy(0)
        y = event.widget.winfo_rooty() - canvas.winfo_rooty() + top
        end = y + event.widget.winfo_height()
        total = max(1, body.winfo_height())
        if y < top:
            canvas.yview_moveto(max(0, y / total))
        elif end > top + canvas.winfo_height():
            canvas.yview_moveto(max(0, (end - canvas.winfo_height()) / total))
    def bind(widget):
        widget.bind("<MouseWheel>", wheel)
        widget.bind("<FocusIn>", reveal, add="+")
        for child in widget.winfo_children():
            bind(child)
    bind(viewport)
    host._bind_field_viewport = bind


def _build_options(host, options):
    ttk.Label(options, text="Suchbereich").grid(row=0, column=0, sticky="w", pady=3)
    host.cmb_search_mode = ttk.Combobox(options, textvariable=host.var_search_mode_label, values=list(SEARCH_MODE_LABELS.values()), state="readonly", width=10, name="field_search_mode")
    host.cmb_search_mode.grid(row=0, column=1, sticky="ew", padx=(6, 0))
    ttk.Label(options, text="Textmarker").grid(row=1, column=0, sticky="w", pady=3)
    host.ent_search_after = ttk.Entry(options, textvariable=host.var_search_after, name="field_search_after")
    host.ent_search_after.grid(row=1, column=1, sticky="ew", padx=(6, 0))
    ttk.Label(options, text="Zeilennummer").grid(row=2, column=0, sticky="w", pady=3)
    host.ent_search_line = ttk.Entry(options, textvariable=host.var_search_line, name="field_search_line", width=8)
    host.ent_search_line.grid(row=2, column=1, sticky="w", padx=(6, 0))
    ttk.Label(options, text="Excel-Spalte").grid(row=3, column=0, sticky="w", pady=3)
    ttk.Entry(options, textvariable=host.var_field_excel_column, name="field_excel", width=10).grid(row=3, column=1, sticky="ew", padx=(6, 0))
    ttk.Checkbutton(options, text="In Dublettenprüfung einbeziehen", variable=host.var_field_dedupe).grid(row=4, column=0, columnspan=2, sticky="w")
    helpers = _ActionFlow(options)
    helpers.grid(row=5, column=0, columnspan=2, sticky="ew", pady=4)
    helpers.add("Ab markierter Zeile", host.on_marking_set_search_line, width=0)
    helpers.add("Ab vorheriger Zeile", host.on_marking_set_search_after_prev_line, width=0)
    helpers.add("Ab markiertem Text", host.on_marking_set_search_after_selection, width=0)
    for index, variable in enumerate((host.var_field_guidance, host.var_marking_selection), 6):
        ttk.Label(options, textvariable=variable, foreground=COLOR_TEXT_MUTED, wraplength=260).grid(row=index, column=0, columnspan=2, sticky="ew")
