"""WizardUiMixin: Widget-Aufbau der Wizard-Schritte (Logik liegt in wizard.py)."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from interfaces.tk.scroll_helpers import create_scrollable_listbox, create_scrollable_treeview

from .regex_library import RegexLibraryPopup

_REQUIRED_STATUS_LABELS = {
    "confirmed": "Treffer",
    "missing_regex": "Regex fehlt",
    "miss": "Kein Treffer",
    "error": "Fehler",
    "missing_field": "Feld fehlt",
}

_CANDIDATE_STATUS_LABELS = _REQUIRED_STATUS_LABELS

_STEPS = ["basis", "pdf", "confirm", "custom", "finish"]
_STEP_TITLES = {
    "basis": "Schritt 1 von 5: Grunddaten",
    "pdf": "Schritt 2 von 5: Beispiel-PDF laden",
    "confirm": "Schritt 3 von 5: Pflichtfelder bestaetigen",
    "custom": "Schritt 4 von 5: Kandidaten und eigene Felder (optional)",
    "finish": "Schritt 5 von 5: Abschluss",
}


class WizardUiMixin:
    def _build_ui(self) -> None:
        self.lbl_title = tk.Label(self, text="", font=("Segoe UI", 11, "bold"), anchor="w")
        self.lbl_title.pack(fill="x", padx=12, pady=(12, 2))
        tk.Label(self, textvariable=self.var_status, anchor="w", fg="#555", wraplength=1050).pack(
            fill="x", padx=12, pady=(0, 6)
        )

        self._cards = tk.Frame(self)
        self._cards.pack(fill="x", padx=12)
        self._card_frames: dict[str, tk.Frame] = {}
        for key in _STEPS:
            frame = tk.Frame(self._cards)
            frame.grid(row=0, column=0, sticky="nsew")
            self._card_frames[key] = frame
        self._cards.columnconfigure(0, weight=1)

        self._build_basis_card(self._card_frames["basis"])
        self._build_pdf_card(self._card_frames["pdf"])
        self._build_confirm_card(self._card_frames["confirm"])
        self._build_custom_card(self._card_frames["custom"])
        self._build_finish_card(self._card_frames["finish"])

        preview = tk.LabelFrame(self, text="Assay-Text (Treffer wird gelb markiert)")
        preview.pack(fill="both", expand=True, padx=12, pady=(8, 6))
        self.txt_preview = tk.Text(preview, wrap="word", height=12)
        self.txt_preview.pack(fill="both", expand=True, padx=6, pady=6)
        self.txt_preview.tag_config("hit", background="#f7d774")
        self.txt_preview.configure(state="disabled")

        nav = tk.Frame(self)
        nav.pack(fill="x", padx=12, pady=(0, 12))
        tk.Button(nav, text="Abbrechen", command=self._on_cancel).pack(side="left")
        self.btn_next = tk.Button(nav, text="Weiter", width=16, command=self._on_next)
        self.btn_next.pack(side="right")
        self.btn_back = tk.Button(nav, text="Zurueck", width=10, command=self._on_back)
        self.btn_back.pack(side="right", padx=(0, 8))

    def _build_basis_card(self, card: tk.Frame) -> None:
        form = tk.LabelFrame(card, text="Neues Regelset")
        form.pack(fill="x")
        tk.Label(form, text="Assay-Key (z.B. (1234))").grid(row=0, column=0, sticky="w", padx=(6, 0), pady=(8, 4))
        tk.Entry(form, textvariable=self.var_key, width=20).grid(row=0, column=1, sticky="w", padx=(4, 12), pady=(8, 4))
        tk.Label(form, text="Assay-Name").grid(row=0, column=2, sticky="w", pady=(8, 4))
        tk.Entry(form, textvariable=self.var_name, width=44).grid(row=0, column=3, sticky="we", padx=(4, 8), pady=(8, 4))
        form.columnconfigure(3, weight=1)

        tk.Radiobutton(
            form,
            text="Aehnlich wie Vorlage (Pflicht-Header aus Quell-Regelset; weitere Felder als Kandidaten)",
            variable=self.var_mode,
            value="similar",
        ).grid(row=1, column=0, columnspan=4, sticky="w", padx=6, pady=(8, 2))
        src_row = tk.Frame(form)
        src_row.grid(row=2, column=0, columnspan=4, sticky="w", padx=(28, 6))
        tk.Label(src_row, text="Vorlage:").pack(side="left")
        self.cmb_source = ttk.Combobox(
            src_row,
            textvariable=self.var_source,
            values=sorted(self._assay_display_to_key.keys()),
            width=52,
            state="readonly",
        )
        self.cmb_source.pack(side="left", padx=(6, 0))
        if self.cmb_source["values"]:
            self.var_source.set(self.cmb_source["values"][0])

        tk.Radiobutton(
            form,
            text="Von Grund auf neu (Pflicht-Header aus template.json; Zusatzfelder als Kandidaten)",
            variable=self.var_mode,
            value="blank",
        ).grid(row=3, column=0, columnspan=4, sticky="w", padx=6, pady=(6, 8))

    def _build_pdf_card(self, card: tk.Frame) -> None:
        form = tk.LabelFrame(card, text="Beispiel-PDF")
        form.pack(fill="x")
        tk.Label(
            form,
            text=(
                "Waehlen Sie eine PDF, die zu diesem Regelset passt. Der erkannte Text wird unten "
                "angezeigt und dient in den naechsten Schritten als Pruefgrundlage."
            ),
            anchor="w",
            justify="left",
            wraplength=1000,
            fg="#444",
        ).pack(fill="x", padx=6, pady=(8, 4))
        row = tk.Frame(form)
        row.pack(fill="x", padx=6, pady=(0, 8))
        tk.Entry(row, textvariable=self.var_pdf).pack(side="left", fill="x", expand=True)
        tk.Button(row, text="PDF...", command=self._on_pick_pdf).pack(side="left", padx=(6, 0))
        tk.Button(row, text="Text laden", command=self._on_load_text).pack(side="left", padx=(6, 0))

        req = tk.LabelFrame(card, text="Pflichtfelder (Focus Mode)")
        req.pack(fill="x", pady=(8, 0))
        tk.Label(
            req,
            text=(
                "Nach dem Laden sehen Sie den Status der acht Pflichtfelder. "
                "Im naechsten Schritt waehlen Sie ein Feld, pflegen den Regex manuell "
                "und pruefen den Treffer gegen den Beispieltext."
            ),
            anchor="w",
            justify="left",
            wraplength=1000,
            fg="#444",
        ).pack(fill="x", padx=6, pady=(8, 4))
        self.list_required, required_frame = create_scrollable_listbox(req, height=6, exportselection=False)
        required_frame.pack(fill="both", expand=True, padx=6, pady=(0, 8))
        self.list_required.bind("<<ListboxSelect>>", self._on_required_field_selected)

        cand = tk.LabelFrame(card, text="Kandidaten (Vorschau)")
        cand.pack(fill="x", pady=(8, 0))
        self.lbl_candidates_summary = tk.Label(cand, text="", anchor="w", fg="#444", wraplength=1000)
        self.lbl_candidates_summary.pack(fill="x", padx=6, pady=(8, 4))
        self.list_candidates_preview, candidates_preview_frame = create_scrollable_listbox(
            cand, height=4, exportselection=False
        )
        candidates_preview_frame.pack(fill="both", expand=True, padx=6, pady=(0, 8))

    def _build_confirm_card(self, card: tk.Frame) -> None:
        form = tk.LabelFrame(card, text="Pflichtfeld pruefen")
        form.pack(fill="x")
        head = tk.Frame(form)
        head.pack(fill="x", padx=6, pady=(8, 2))
        tk.Label(head, textvariable=self.var_progress, font=("Segoe UI", 10, "bold")).pack(side="left")
        tk.Label(head, textvariable=self.var_match, fg="#444").pack(side="right")

        grid = tk.Frame(form)
        grid.pack(fill="x", padx=6, pady=(2, 4))
        tk.Label(grid, text="Feldname").grid(row=0, column=0, sticky="w")
        tk.Entry(grid, textvariable=self.var_f_key, width=24, state="readonly").grid(row=0, column=1, sticky="w", padx=(4, 12))
        self.chk_required = tk.Checkbutton(grid, text="Pflichtfeld", variable=self.var_f_required)
        self.chk_required.grid(row=0, column=2, sticky="w")
        tk.Label(grid, text="Regex").grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.ent_confirm_regex = tk.Entry(grid, textvariable=self.var_f_regex, width=80)
        self.ent_confirm_regex.grid(row=1, column=1, columnspan=2, sticky="we", padx=(4, 0), pady=(4, 0))
        tk.Button(
            grid, text="Bib...", width=4, command=lambda: RegexLibraryPopup(self, self.ent_confirm_regex)
        ).grid(row=1, column=3, sticky="w", padx=(6, 0), pady=(4, 0))
        grid.columnconfigure(1, weight=1)
        self._build_search_from_row(grid, row=2)

        btns = tk.Frame(form)
        btns.pack(fill="x", padx=6, pady=(4, 8))
        tk.Button(btns, text="Pflichtfeld pruefen", command=self._on_confirm_required_field).pack(side="left")
        tk.Button(btns, text="Erneut testen", command=self._on_retest_field).pack(side="left", padx=(6, 0))
        self.btn_remove_field = tk.Button(btns, text="Feld entfernen", command=self._on_remove_field)
        self.btn_remove_field.pack(side="left", padx=(6, 0))
        sf_btns = tk.Frame(form)
        sf_btns.pack(fill="x", padx=6, pady=(0, 8))
        tk.Button(sf_btns, text="Suche ab Cursor-Zeile", command=self._on_use_cursor_line).pack(side="left")
        tk.Button(sf_btns, text="Suche ab vorheriger Zeile", command=self._on_use_previous_line).pack(side="left", padx=(6, 0))
        tk.Label(
            btns,
            text="'Passt - weiter' speichert das Feld und zeigt das naechste Pflichtfeld.",
            fg="#666",
        ).pack(side="right")

    def _build_custom_card(self, card: tk.Frame) -> None:
        cand = tk.LabelFrame(card, text="Kandidaten aus Vorlage")
        cand.pack(fill="x")
        tk.Label(
            cand,
            textvariable=self.var_candidates_summary,
            anchor="w",
            fg="#444",
            wraplength=1000,
        ).pack(fill="x", padx=6, pady=(8, 4))
        self.list_candidates, candidates_frame = create_scrollable_listbox(cand, height=5, exportselection=False)
        candidates_frame.pack(fill="both", expand=True, padx=6, pady=(0, 4))
        self.list_candidates.bind("<<ListboxSelect>>", self._on_candidate_selected)
        cand_btns = tk.Frame(cand)
        cand_btns.pack(fill="x", padx=6, pady=(0, 8))
        tk.Button(cand_btns, text="Kandidat testen", command=self._on_test_candidate).pack(side="left")
        tk.Button(cand_btns, text="Kandidat uebernehmen", command=self._on_adopt_candidate).pack(side="left", padx=(6, 0))
        tk.Button(cand_btns, text="Verwerfen", command=self._on_dismiss_candidate).pack(side="left", padx=(6, 0))

        form = tk.LabelFrame(card, text="Eigenes Feld anlegen (optional)")
        form.pack(fill="x", pady=(8, 0))
        head = tk.Frame(form)
        head.pack(fill="x", padx=6, pady=(8, 2))
        tk.Label(head, textvariable=self.var_custom_count, fg="#444").pack(side="left")
        tk.Label(head, textvariable=self.var_match, fg="#444").pack(side="right")

        grid = tk.Frame(form)
        grid.pack(fill="x", padx=6, pady=(2, 4))
        tk.Label(grid, text="Feldname").grid(row=0, column=0, sticky="w")
        tk.Entry(grid, textvariable=self.var_f_key, width=24).grid(row=0, column=1, sticky="w", padx=(4, 12))
        tk.Checkbutton(grid, text="Pflichtfeld", variable=self.var_f_required).grid(row=0, column=2, sticky="w")
        tk.Label(grid, text="Regex").grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.ent_custom_regex = tk.Entry(grid, textvariable=self.var_f_regex, width=80)
        self.ent_custom_regex.grid(row=1, column=1, columnspan=2, sticky="we", padx=(4, 0), pady=(4, 0))
        tk.Button(
            grid, text="Bib...", width=4, command=lambda: RegexLibraryPopup(self, self.ent_custom_regex)
        ).grid(row=1, column=3, sticky="w", padx=(6, 0), pady=(4, 0))
        grid.columnconfigure(1, weight=1)
        self._build_search_from_row(grid, row=2)

        btns = tk.Frame(form)
        btns.pack(fill="x", padx=6, pady=(4, 8))
        tk.Button(btns, text="Regex testen", command=self._on_test_custom).pack(side="left")
        tk.Button(btns, text="Feld uebernehmen", command=self._on_add_custom).pack(side="left", padx=(6, 0))
        tk.Label(
            btns,
            text="Felder nacheinander anlegen; mit 'Weiter' geht es zum Abschluss.",
            fg="#666",
        ).pack(side="right")

    def _build_search_from_row(self, grid: tk.Frame, row: int) -> None:
        sf = tk.Frame(grid)
        sf.grid(row=row, column=0, columnspan=4, sticky="w", pady=(4, 2))
        tk.Label(sf, text="Suche ab").pack(side="left")
        ttk.Combobox(
            sf,
            textvariable=self.var_f_mode,
            values=["none", "after", "line"],
            width=8,
            state="readonly",
        ).pack(side="left", padx=(4, 10))
        tk.Label(sf, text="after").pack(side="left")
        tk.Entry(sf, textvariable=self.var_f_after, width=28).pack(side="left", padx=(4, 10))
        tk.Label(sf, text="line").pack(side="left")
        tk.Entry(sf, textvariable=self.var_f_line, width=6).pack(side="left", padx=(4, 0))

    def _build_finish_card(self, card: tk.Frame) -> None:
        form = tk.LabelFrame(card, text="Zusammenfassung")
        form.pack(fill="x")
        self.list_summary, summary_frame = create_scrollable_listbox(form, height=7)
        summary_frame.pack(fill="both", expand=True, padx=6, pady=(8, 6))
        tk.Radiobutton(
            form,
            text="Draft im Editor oeffnen (empfohlen: dort weiter pruefen und kontrolliert aktivieren)",
            variable=self.var_finish_action,
            value="editor",
        ).pack(anchor="w", padx=6)
        tk.Radiobutton(
            form,
            text="Direkt aktivieren (nur wenn alle Pflichtfelder Treffer haben)",
            variable=self.var_finish_action,
            value="activate",
        ).pack(anchor="w", padx=6, pady=(0, 8))
        self.lbl_required_summary = tk.Label(form, text="", anchor="w", fg="#666", wraplength=1000)
        self.lbl_required_summary.pack(fill="x", padx=6, pady=(0, 8))
