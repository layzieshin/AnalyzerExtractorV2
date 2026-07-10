"""UiBuilderMixin: reiner Widget-Aufbau (Tabs, Hilfeboxen, Schnellnavigation)."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .constants import HELP_TEXTS


class UiBuilderMixin:
    def _build_ui(self) -> None:
        top = tk.Frame(self)
        top.pack(fill="x", padx=10, pady=8)

        tk.Label(top, text="Projektordner").pack(side="left")
        tk.Entry(top, textvariable=self.var_root, width=70).pack(side="left", padx=(6, 6))
        tk.Button(top, text="Ordner...", command=self.on_pick_root).pack(side="left")
        tk.Button(top, text="Assays neu laden", command=self._reload_assays).pack(side="left", padx=(6, 0))
        tk.Button(top, text="Step by Step", command=self.open_step_by_step).pack(side="left", padx=(10, 0))

        self.lbl_status = tk.Label(top, text="Bereit")
        self.lbl_status.pack(side="right")

        hint = tk.Label(self, textvariable=self.var_hint, anchor="w", fg="#555")
        hint.pack(fill="x", padx=10, pady=(0, 4))
        self._step_tab_order = [
            ("draft", "1 Draft"),
            ("pdf", "2 PDF"),
            ("fields", "3 Felder"),
            ("meta", "4 Meta"),
            ("validate", "5 Pruefen"),
            ("log", "6 Log"),
        ]
        self._guide_tab_order = ["draft", "pdf", "fields", "meta", "validate", "validate"]
        self._step_nav_buttons: list[tuple[str, tk.Button]] = []
        self._tab_frames: dict[str, tk.Frame] = {}

        self._build_step_nav()

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        draft_tab = tk.Frame(self.notebook)
        self.notebook.add(draft_tab, text="Draft")
        self._tab_frames["draft"] = draft_tab
        self._build_draft_tab(draft_tab)

        pdf_tab = tk.Frame(self.notebook)
        self.notebook.add(pdf_tab, text="PDF / Assay-Text")
        self._tab_frames["pdf"] = pdf_tab
        self._build_pdf_tab(pdf_tab)

        fields_tab = tk.Frame(self.notebook)
        self.notebook.add(fields_tab, text="Felder")
        self._tab_frames["fields"] = fields_tab
        self._build_fields_tab(fields_tab)

        meta_tab = tk.Frame(self.notebook)
        self.notebook.add(meta_tab, text="Meta & Excel")
        self._tab_frames["meta"] = meta_tab
        self._build_meta_tab(meta_tab)

        validate_tab = tk.Frame(self.notebook)
        self.notebook.add(validate_tab, text="Validierung & Aktivierung")
        self._tab_frames["validate"] = validate_tab
        self._build_validate_tab(validate_tab)

        log_tab = tk.Frame(self.notebook)
        self.notebook.add(log_tab, text="Log")
        self._tab_frames["log"] = log_tab
        self._build_log_tab(log_tab)

        self._set_active_step_button("draft")

    def _build_step_nav(self) -> None:
        nav = tk.Frame(self)
        nav.pack(fill="x", padx=10, pady=(0, 8))
        tk.Label(nav, text="Schnellnavigation:").pack(side="left")
        for key, label in self._step_tab_order:
            btn = tk.Button(nav, text=label, command=lambda k=key: self._select_tab(k))
            btn.pack(side="left", padx=(6, 0))
            self._step_nav_buttons.append((key, btn))

    def _build_draft_tab(self, parent: tk.Frame) -> None:
        container = tk.Frame(parent)
        container.pack(fill="both", expand=True, padx=6, pady=6)
        self._add_collapsible_help(
            container,
            "draft_control",
            "Startpunkt: Bestehendes Regelset laden oder neues Regelset anlegen.",
            wraplength=1200,
        )

        control = tk.LabelFrame(container, text="Draft-Steuerung")
        control.pack(fill="x", pady=(8, 0))

        row1 = tk.Frame(control)
        row1.pack(fill="x", padx=6, pady=6)
        tk.Label(row1, text="Assay (aktiv)").pack(side="left")
        self.cmb_assay = ttk.Combobox(row1, textvariable=self.var_assay, width=52, state="readonly")
        self.cmb_assay.pack(side="left", padx=(4, 8))
        tk.Button(row1, text="Draft aus aktivem Assay", command=self.on_create_from_active).pack(side="left")
        tk.Button(row1, text="Draft laden...", command=self.on_pick_draft).pack(side="left", padx=(6, 0))

        row2 = tk.Frame(control)
        row2.pack(fill="x", padx=6, pady=(0, 6))
        tk.Label(row2, text="Neuer Assay-Key").pack(side="left")
        tk.Entry(row2, textvariable=self.var_new_assay_key, width=16).pack(side="left", padx=(4, 8))
        tk.Label(row2, text="Neuer Assay-Name").pack(side="left")
        tk.Entry(row2, textvariable=self.var_new_assay_name, width=42).pack(side="left", padx=(4, 8))
        tk.Button(row2, text="Neues leeres Draft", command=self.on_create_blank).pack(side="left")
        tk.Button(row2, text="Aus aktivem ableiten", command=self.on_derive).pack(side="left", padx=(6, 0))

        row3 = tk.Frame(control)
        row3.pack(fill="x", padx=6, pady=(0, 6))
        tk.Label(row3, text="Draft-Datei").pack(side="left")
        tk.Entry(row3, textvariable=self.var_draft_path).pack(side="left", fill="x", expand=True, padx=(4, 8))
        tk.Button(row3, text="Draft laden in Editor", command=self.on_load_draft_into_editor).pack(side="left")

        manage = tk.LabelFrame(container, text="Regelset-Verwaltung")
        manage.pack(fill="both", expand=True, pady=(10, 0))
        manage_btns = tk.Frame(manage)
        manage_btns.pack(fill="x", padx=6, pady=(6, 4))
        tk.Button(manage_btns, text="Neues Regelset (gefuehrt)...", command=self.on_open_wizard).pack(side="left")
        tk.Button(manage_btns, text="Ansehen/Bearbeiten", command=self.on_manage_edit_selected).pack(side="left", padx=(6, 0))
        tk.Button(manage_btns, text="Loeschen...", command=self.on_manage_delete_selected).pack(side="left", padx=(6, 0))
        tk.Button(manage_btns, text="Aktualisieren", command=self._refresh_ruleset_overview).pack(side="left", padx=(6, 0))

        self.tree_rulesets = ttk.Treeview(
            manage,
            columns=("key", "name", "file", "fields", "status"),
            show="headings",
            height=8,
        )
        self.tree_rulesets.heading("key", text="Assay-Key")
        self.tree_rulesets.heading("name", text="Name")
        self.tree_rulesets.heading("file", text="Datei")
        self.tree_rulesets.heading("fields", text="Felder")
        self.tree_rulesets.heading("status", text="Status")
        self.tree_rulesets.column("key", width=110, anchor="w")
        self.tree_rulesets.column("name", width=300, anchor="w")
        self.tree_rulesets.column("file", width=300, anchor="w")
        self.tree_rulesets.column("fields", width=70, anchor="center")
        self.tree_rulesets.column("status", width=160, anchor="w")
        self.tree_rulesets.pack(fill="both", expand=True, padx=6, pady=(0, 6))

    def _build_pdf_tab(self, parent: tk.Frame) -> None:
        container = tk.Frame(parent)
        container.pack(fill="both", expand=True, padx=6, pady=6)
        self._add_collapsible_help(
            container,
            "pdf_block",
            "Test-PDF laden und den relevanten Assay-Text fuer Regex-Tests anzeigen.",
            wraplength=1200,
        )

        row_text = tk.Frame(container)
        row_text.pack(fill="x", pady=(8, 6))
        tk.Label(row_text, text="Test-PDF").pack(side="left")
        tk.Entry(row_text, textvariable=self.var_pdf).pack(side="left", fill="x", expand=True, padx=(4, 8))
        tk.Button(row_text, text="PDF...", command=self.on_pick_pdf).pack(side="left")
        tk.Button(row_text, text="Text laden", command=self.on_load_text).pack(side="left", padx=(6, 0))
        self.btn_toggle_markings = tk.Button(
            row_text,
            text="Markierungs-Ansicht ausblenden",
            command=self._toggle_marking_panel,
        )
        self.btn_toggle_markings.pack(side="left", padx=(6, 0))

        split = tk.Frame(container)
        split.pack(fill="both", expand=True)

        text_frame = tk.Frame(split)
        text_frame.pack(side="left", fill="both", expand=True)

        self.txt_block = tk.Text(text_frame, wrap="word")
        self.txt_block.pack(fill="both", expand=True)
        self.txt_block.tag_config("hit", background="#f7d774")
        self.txt_block.tag_config("field_emphasis", background="#ffd000")
        self.txt_block.bind("<<Selection>>", self._on_block_selection_changed)

        self.frame_marking_panel = tk.Frame(split, width=430)
        self.frame_marking_panel.pack(side="right", fill="y", padx=(8, 0))
        self.frame_marking_panel.pack_propagate(False)

        marking_frame = tk.LabelFrame(self.frame_marking_panel, text="Markierungen")
        marking_frame.pack(fill="x", pady=(0, 6))
        marking_row_1 = tk.Frame(marking_frame)
        marking_row_1.pack(fill="x", padx=6, pady=(6, 3))
        tk.Button(marking_row_1, text="Aktualisieren", command=self._render_field_markings).pack(side="left")
        tk.Button(marking_row_1, text="Alle anzeigen", command=lambda: self._set_all_markings_visible(True)).pack(
            side="left", padx=(6, 0)
        )
        tk.Button(marking_row_1, text="Alle ausblenden", command=lambda: self._set_all_markings_visible(False)).pack(
            side="left", padx=(6, 0)
        )
        marking_row_2 = tk.Frame(marking_frame)
        marking_row_2.pack(fill="x", padx=6, pady=(0, 6))
        tk.Button(marking_row_2, text="Nur Treffer", command=self._show_only_matched_markings).pack(side="left")
        tk.Button(marking_row_2, text="Nur aktives Feld", command=self._show_only_active_marking).pack(
            side="left", padx=(6, 0)
        )
        tk.Button(marking_row_2, text="Feld AN/AUS", command=self._toggle_selected_marking_visibility).pack(
            side="left", padx=(6, 0)
        )
        tk.Label(
            marking_frame,
            textvariable=self.var_marking_status,
            anchor="w",
            justify="left",
            wraplength=400,
            fg="#444",
        ).pack(fill="x", padx=6, pady=(0, 6))

        selection_frame = tk.LabelFrame(self.frame_marking_panel, text="Textauswahl")
        selection_frame.pack(fill="x", pady=(0, 6))
        tk.Label(
            selection_frame,
            textvariable=self.var_marking_selection,
            anchor="w",
            justify="left",
            wraplength=350,
            fg="#333",
        ).pack(fill="x", padx=6, pady=(6, 4))
        sel_btn_row_1 = tk.Frame(selection_frame)
        sel_btn_row_1.pack(fill="x", padx=6, pady=(0, 3))
        tk.Button(sel_btn_row_1, text="Regex aus Auswahl", command=self.on_marking_regex_from_selection).pack(side="left")
        tk.Button(sel_btn_row_1, text="Suche ab: Zeile", command=self.on_marking_set_search_line).pack(
            side="left", padx=(6, 0)
        )
        sel_btn_row_2 = tk.Frame(selection_frame)
        sel_btn_row_2.pack(fill="x", padx=6, pady=(0, 6))
        tk.Button(
            sel_btn_row_2,
            text="Suche ab: Zeile davor",
            command=self.on_marking_set_search_after_prev_line,
        ).pack(side="left")

        legend_frame = tk.LabelFrame(self.frame_marking_panel, text="Felder und Treffer")
        legend_frame.pack(fill="both", expand=True, pady=(0, 6))
        self.tree_marking_legend = ttk.Treeview(
            legend_frame,
            columns=("status", "visible", "value"),
            show="tree headings",
            height=14,
        )
        self.tree_marking_legend.heading("#0", text="Feld")
        self.tree_marking_legend.heading("status", text="Status")
        self.tree_marking_legend.heading("visible", text="Sichtbar")
        self.tree_marking_legend.heading("value", text="Ergebnis")
        self.tree_marking_legend.column("#0", width=120, anchor="w")
        self.tree_marking_legend.column("status", width=82, anchor="center")
        self.tree_marking_legend.column("visible", width=58, anchor="center")
        self.tree_marking_legend.column("value", width=145, anchor="w")
        self.tree_marking_legend.pack(fill="both", expand=True, padx=6, pady=6)
        self.tree_marking_legend.bind("<<TreeviewSelect>>", self.on_marking_legend_selected)

        param_frame = tk.LabelFrame(self.frame_marking_panel, text="Feld bearbeiten")
        param_frame.pack(fill="x", pady=(0, 6))
        tk.Label(param_frame, text="Feldname").grid(row=0, column=0, sticky="w", padx=(6, 0), pady=(6, 4))
        tk.Entry(param_frame, textvariable=self.var_field_key, width=22).grid(row=0, column=1, sticky="we", padx=(4, 6), pady=(6, 4))
        tk.Checkbutton(param_frame, text="Pflichtfeld", variable=self.var_field_required).grid(
            row=0, column=2, sticky="w", pady=(6, 4)
        )
        tk.Label(param_frame, text="Regex").grid(row=1, column=0, sticky="nw", padx=(6, 0), pady=(0, 4))
        self.ent_marking_regex = tk.Entry(param_frame, textvariable=self.var_field_regex)
        self.ent_marking_regex.grid(row=1, column=1, sticky="we", padx=(4, 6), pady=(0, 4))
        tk.Button(
            param_frame,
            text="Bib...",
            width=4,
            command=lambda: self.on_open_regex_library(self.ent_marking_regex),
        ).grid(row=1, column=2, sticky="w", padx=(0, 6), pady=(0, 4))
        tk.Label(param_frame, text="Suche ab").grid(row=2, column=0, sticky="w", padx=(6, 0), pady=(0, 6))
        ttk.Combobox(
            param_frame,
            textvariable=self.var_search_mode,
            values=["none", "after", "line"],
            width=8,
            state="readonly",
        ).grid(row=2, column=1, sticky="w", padx=(4, 4), pady=(0, 6))
        sf_row = tk.Frame(param_frame)
        sf_row.grid(row=3, column=0, columnspan=3, sticky="we", padx=6, pady=(0, 6))
        tk.Label(sf_row, text="after").pack(side="left")
        tk.Entry(sf_row, textvariable=self.var_search_after, width=18).pack(side="left", padx=(4, 8))
        tk.Label(sf_row, text="line").pack(side="left")
        tk.Entry(sf_row, textvariable=self.var_search_line, width=6).pack(side="left", padx=(4, 0))
        param_frame.columnconfigure(1, weight=1)

        action_frame = tk.Frame(param_frame)
        action_frame.grid(row=4, column=0, columnspan=3, sticky="we", padx=6, pady=(0, 6))
        tk.Button(action_frame, text="Neues Feld anlegen", command=self.on_add_field).pack(side="left")
        tk.Button(action_frame, text="Feld übernehmen", command=self.on_apply_field).pack(side="left", padx=(6, 0))
        tk.Button(action_frame, text="Formular leeren", command=self._reset_field_form).pack(side="left", padx=(6, 0))

    def _build_fields_tab(self, parent: tk.Frame) -> None:
        container = tk.Frame(parent)
        container.pack(fill="both", expand=True, padx=6, pady=6)
        self._add_collapsible_help(
            container,
            "fields",
            "Hier definieren Sie, welche Werte aus der PDF gelesen werden sollen.",
            wraplength=1200,
        )

        self.tree_fields = ttk.Treeview(
            container,
            columns=("key", "regex", "required", "search_from"),
            show="headings",
            height=14,
        )
        self.tree_fields.heading("key", text="Feld")
        self.tree_fields.heading("regex", text="regex")
        self.tree_fields.heading("required", text="Pflicht")
        self.tree_fields.heading("search_from", text="search_from")
        self.tree_fields.column("key", width=160, anchor="w")
        self.tree_fields.column("regex", width=560, anchor="w")
        self.tree_fields.column("required", width=90, anchor="center")
        self.tree_fields.column("search_from", width=180, anchor="w")
        self.tree_fields.pack(fill="both", expand=True, pady=(8, 6))
        self.tree_fields.bind("<<TreeviewSelect>>", self.on_field_selected)

        edit = tk.LabelFrame(container, text="Feld-Editor")
        edit.pack(fill="x", pady=(0, 6))
        tk.Label(edit, text="Feldname").grid(row=0, column=0, sticky="w", padx=(6, 0), pady=(6, 4))
        tk.Entry(edit, textvariable=self.var_field_key, width=18).grid(row=0, column=1, sticky="w", padx=(4, 8), pady=(6, 4))
        tk.Label(edit, text="Regex").grid(row=0, column=2, sticky="w", pady=(6, 4))
        self.ent_field_regex = tk.Entry(edit, textvariable=self.var_field_regex, width=58)
        self.ent_field_regex.grid(row=0, column=3, sticky="we", padx=(4, 8), pady=(6, 4))
        tk.Checkbutton(edit, text="Pflichtfeld", variable=self.var_field_required).grid(row=0, column=4, sticky="w", pady=(6, 4))

        tk.Label(edit, text="Suche ab").grid(row=1, column=0, sticky="w", padx=(6, 0), pady=(0, 6))
        ttk.Combobox(
            edit,
            textvariable=self.var_search_mode,
            values=["none", "after", "line"],
            width=8,
            state="readonly",
        ).grid(row=1, column=1, sticky="w", padx=(4, 8), pady=(0, 6))
        tk.Entry(edit, textvariable=self.var_search_after, width=28).grid(row=1, column=2, sticky="w", padx=(0, 8), pady=(0, 6))
        tk.Entry(edit, textvariable=self.var_search_line, width=10).grid(row=1, column=3, sticky="w", pady=(0, 6))
        tk.Label(edit, text="Regex-Gruppe (nur Test)").grid(row=1, column=4, sticky="w", pady=(0, 6))
        ttk.Combobox(edit, textvariable=self.var_regex_group, values=["0", "1", "2", "3"], width=4, state="readonly").grid(
            row=1,
            column=5,
            sticky="w",
            padx=(4, 8),
            pady=(0, 6),
        )
        tk.Label(
            edit,
            textvariable=self.var_field_guidance,
            anchor="w",
            justify="left",
            wraplength=900,
            fg="#8a6d00",
        ).grid(row=2, column=0, columnspan=5, sticky="we", padx=(6, 8), pady=(0, 6))
        tk.Button(edit, text="Im PDF-Tab zeigen/hinterlegen", command=self.on_goto_field_marking).grid(
            row=2, column=5, sticky="e", padx=(0, 8), pady=(0, 6)
        )
        edit.columnconfigure(3, weight=1)

        row_btn_1 = tk.Frame(container)
        row_btn_1.pack(fill="x", pady=(0, 4))
        tk.Button(row_btn_1, text="Feld hinzufügen", command=self.on_add_field).pack(side="left")
        tk.Button(row_btn_1, text="Feld übernehmen", command=self.on_apply_field).pack(side="left", padx=(6, 0))
        tk.Button(row_btn_1, text="Feld duplizieren", command=self.on_duplicate_field).pack(side="left", padx=(6, 0))
        tk.Button(row_btn_1, text="Feld entfernen", command=self.on_remove_field).pack(side="left", padx=(6, 0))
        tk.Button(row_btn_1, text="Feld umbenennen", command=self.on_rename_field).pack(side="left", padx=(6, 0))
        tk.Button(row_btn_1, text="↑", width=3, command=lambda: self.on_move_field("up")).pack(side="left", padx=(6, 0))
        tk.Button(row_btn_1, text="↓", width=3, command=lambda: self.on_move_field("down")).pack(side="left", padx=(4, 0))

        row_btn_2 = tk.Frame(container)
        row_btn_2.pack(fill="x")
        tk.Button(row_btn_2, text="Regex testen", command=self.on_test_regex).pack(side="left")
        tk.Button(row_btn_2, text="Regex-Bibliothek...", command=self.on_open_regex_library).pack(side="left", padx=(6, 0))
        tk.Button(row_btn_2, text="Batch-Regex-Check", command=self.on_batch_regex_check).pack(side="left", padx=(6, 0))
        tk.Button(row_btn_2, text="i", width=2, command=lambda: self._show_help("batch_regex")).pack(side="left", padx=(4, 0))
        tk.Button(row_btn_2, text="Formular leeren", command=self._reset_field_form).pack(side="left", padx=(6, 0))
        tk.Button(row_btn_2, text="Ergebnisliste leeren", command=self._clear_regex_results).pack(side="left", padx=(6, 0))

        result_frame = tk.LabelFrame(container, text="Regex-Ergebnisse (pro Testlauf)")
        result_frame.pack(fill="both", expand=True, pady=(8, 6))
        self.tree_regex_results = ttk.Treeview(
            result_frame,
            columns=("field_name", "status", "regex", "result", "context"),
            show="headings",
            height=7,
        )
        self.tree_regex_results.heading("field_name", text="Feldname")
        self.tree_regex_results.heading("status", text="Status")
        self.tree_regex_results.heading("regex", text="Regex")
        self.tree_regex_results.heading("result", text="Ergebnis")
        self.tree_regex_results.heading("context", text="Kontext (Auszug)")
        self.tree_regex_results.column("field_name", width=150, anchor="w")
        self.tree_regex_results.column("status", width=80, anchor="center")
        self.tree_regex_results.column("regex", width=260, anchor="w")
        self.tree_regex_results.column("result", width=200, anchor="w")
        self.tree_regex_results.column("context", width=520, anchor="w")
        self.tree_regex_results.pack(fill="both", expand=True, padx=6, pady=6)
        self.tree_regex_results.bind("<<TreeviewSelect>>", self.on_regex_result_selected)

        preview_frame = tk.LabelFrame(container, text="Regex-Treffer (direkt im Felder-Tab)")
        preview_frame.pack(fill="both", expand=True, pady=(8, 0))
        tk.Label(
            preview_frame,
            text="Hier sehen Sie Kontext und Markierung fuer den zuletzt getesteten Regex.",
            anchor="w",
            justify="left",
            fg="#444",
        ).pack(fill="x", padx=6, pady=(6, 4))
        self.txt_field_preview = tk.Text(preview_frame, wrap="word", height=10)
        self.txt_field_preview.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        self.txt_field_preview.tag_config("hit", background="#f7d774")
        self.txt_field_preview.configure(state="disabled")

    def _build_meta_tab(self, parent: tk.Frame) -> None:
        container = tk.Frame(parent)
        container.pack(fill="both", expand=True, padx=6, pady=6)
        self._add_collapsible_help(
            container,
            "meta_actions",
            "Metadaten pflegen und Mapping fuer den Export konfigurieren.",
            wraplength=1200,
        )

        form = tk.LabelFrame(container, text="Metadaten")
        form.pack(fill="x", pady=(8, 6))
        tk.Label(form, text="Assay-Name").grid(row=0, column=0, sticky="w", padx=(6, 0), pady=(6, 4))
        tk.Entry(form, textvariable=self.var_new_assay_name).grid(row=0, column=1, sticky="we", padx=(4, 8), pady=(6, 4))
        tk.Label(form, text="Lot-Regel (Regex)").grid(row=1, column=0, sticky="w", padx=(6, 0), pady=(0, 4))
        tk.Entry(form, textvariable=self.var_lot_regex).grid(row=1, column=1, sticky="we", padx=(4, 8), pady=(0, 4))
        tk.Label(form, text="Dedupe-Felder (,) ").grid(row=2, column=0, sticky="w", padx=(6, 0), pady=(0, 4))
        tk.Entry(form, textvariable=self.var_dedupe_fields).grid(row=2, column=1, sticky="we", padx=(4, 8), pady=(0, 4))
        tk.Label(form, text="Excel-Dateiname (Template)").grid(row=3, column=0, sticky="w", padx=(6, 0), pady=(0, 4))
        tk.Entry(form, textvariable=self.var_excel_filename).grid(row=3, column=1, sticky="we", padx=(4, 8), pady=(0, 4))
        tk.Label(form, text="Sheetname (Template)").grid(row=4, column=0, sticky="w", padx=(6, 0), pady=(0, 6))
        tk.Entry(form, textvariable=self.var_sheet_template).grid(row=4, column=1, sticky="we", padx=(4, 8), pady=(0, 6))
        form.columnconfigure(1, weight=1)

        tk.Label(container, text="Spaltenzuordnung (column_mapping)").pack(anchor="w", padx=2)
        self.tree_cols = ttk.Treeview(container, columns=("key", "column"), show="headings", height=10)
        self.tree_cols.heading("key", text="Feldname")
        self.tree_cols.heading("column", text="Excel-Spalte")
        self.tree_cols.column("key", width=220, anchor="w")
        self.tree_cols.column("column", width=320, anchor="w")
        self.tree_cols.pack(fill="both", expand=True, pady=(2, 6))
        self.tree_cols.bind("<<TreeviewSelect>>", self.on_col_selected)

        col_edit = tk.Frame(container)
        col_edit.pack(fill="x")
        tk.Entry(col_edit, textvariable=self.var_col_key, width=24).pack(side="left")
        tk.Entry(col_edit, textvariable=self.var_col_name, width=34).pack(side="left", padx=(6, 6))
        tk.Button(col_edit, text="Uebernehmen", command=self.on_set_col).pack(side="left")
        tk.Button(col_edit, text="Entfernen", command=self.on_remove_col).pack(side="left", padx=(6, 0))

    def _build_validate_tab(self, parent: tk.Frame) -> None:
        container = tk.Frame(parent)
        container.pack(fill="both", expand=True, padx=6, pady=6)
        self._add_collapsible_help(
            container,
            "validation",
            "Hier speichern, pruefen und aktivieren Sie das Draft kontrolliert.",
            wraplength=1200,
        )

        actions_top = tk.Frame(container)
        actions_top.pack(fill="x", pady=(8, 4))
        tk.Button(actions_top, text="Undo", command=self.on_undo).pack(side="left")
        tk.Button(actions_top, text="Redo", command=self.on_redo).pack(side="left", padx=(6, 0))
        tk.Button(actions_top, text="i", width=2, command=lambda: self._show_help("undo_redo")).pack(side="left", padx=(4, 0))
        tk.Button(actions_top, text="Draft speichern", command=self.on_save_all).pack(side="left", padx=(10, 0))
        tk.Button(actions_top, text="Draft validieren", command=self.on_validate).pack(side="left", padx=(6, 0))

        actions_bottom = tk.Frame(container)
        actions_bottom.pack(fill="x", pady=(0, 6))
        tk.Button(actions_bottom, text="Preview (extract)", command=self.on_preview).pack(side="left")
        tk.Button(actions_bottom, text="i", width=2, command=lambda: self._show_help("preview")).pack(side="left", padx=(4, 0))
        tk.Button(actions_bottom, text="Diff anzeigen", command=self.on_show_diff).pack(side="left", padx=(6, 0))
        tk.Button(actions_bottom, text="i", width=2, command=lambda: self._show_help("diff")).pack(side="left", padx=(4, 0))
        tk.Button(actions_bottom, text="Aktivieren", command=self.on_activate).pack(side="left", padx=(6, 0))
        tk.Button(actions_bottom, text="i", width=2, command=lambda: self._show_help("activate")).pack(side="left", padx=(4, 0))

        autos = tk.Frame(container)
        autos.pack(fill="x", pady=(0, 6))
        tk.Checkbutton(autos, text="Auto-Save (45s)", variable=self.var_autosave).pack(side="left")
        tk.Button(autos, text="i", width=2, command=lambda: self._show_help("autosave")).pack(side="left", padx=(4, 0))
        tk.Label(autos, text="Last Auto-Save:").pack(side="left", padx=(12, 4))
        tk.Label(autos, textvariable=self.var_last_autosave).pack(side="left")

        val_frame = tk.LabelFrame(container, text="Validierung")
        val_frame.pack(fill="both", expand=True)
        self.list_validation = tk.Listbox(val_frame, height=12)
        self.list_validation.pack(fill="both", expand=True, padx=6, pady=6)

    def _build_log_tab(self, parent: tk.Frame) -> None:
        container = tk.Frame(parent)
        container.pack(fill="both", expand=True, padx=6, pady=6)
        self.txt_log = tk.Text(container, height=12, wrap="word")
        self.txt_log.pack(fill="both", expand=True)

    def _add_collapsible_help(self, parent: tk.Widget, key: str, short_text: str, wraplength: int) -> None:
        box = tk.Frame(parent, bd=1, relief=tk.GROOVE)
        box.pack(fill="x")
        head = tk.Frame(box)
        head.pack(fill="x", padx=6, pady=4)
        tk.Label(head, text=short_text, anchor="w", justify="left", wraplength=wraplength, fg="#444").pack(side="left", fill="x", expand=True)
        tk.Button(head, text="i", width=2, command=lambda: self._show_help(key)).pack(side="right")

        detail = tk.Label(
            box,
            text=HELP_TEXTS.get(key, "Keine Hilfe verfuegbar."),
            anchor="w",
            justify="left",
            wraplength=wraplength,
            fg="#333",
        )
        detail_open = {"value": False}

        def _toggle() -> None:
            detail_open["value"] = not detail_open["value"]
            if detail_open["value"]:
                detail.pack(fill="x", padx=6, pady=(0, 6))
                btn_toggle.config(text="Weniger")
            else:
                detail.pack_forget()
                btn_toggle.config(text="Mehr")

        btn_toggle = tk.Button(head, text="Mehr", command=_toggle)
        btn_toggle.pack(side="right", padx=(0, 4))
