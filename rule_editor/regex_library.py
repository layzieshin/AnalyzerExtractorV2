"""Regex-Bibliothek: gaengige Bausteine mit Mini-Anleitung zum direkten Einfuegen."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from interfaces.tk.scroll_helpers import create_scrollable_treeview

REGEX_LIBRARY: list[dict[str, str]] = [
    {
        "name": "Zahl (ganz)",
        "pattern": r"(\d+)",
        "explain": (
            "Findet eine ganze Zahl, z.B. 42 oder 2024.\n\n"
            "Die runden Klammern sind die 'Fanggruppe': nur was darin steht, "
            "wird als Wert uebernommen."
        ),
    },
    {
        "name": "Zahl mit Komma oder Punkt",
        "pattern": r"(\d+(?:[\.,]\d+)?)",
        "explain": (
            "Findet Zahlen wie 12, 12,5 oder 12.5.\n\n"
            "Der Teil (?:[\\.,]\\d+)? bedeutet: optional darf ein Komma oder Punkt "
            "mit weiteren Ziffern folgen."
        ),
    },
    {
        "name": "Datum (TT.MM.JJJJ)",
        "pattern": r"(\d{2}\.\d{2}\.\d{4})",
        "explain": (
            "Findet ein Datum wie 24.12.2025.\n\n"
            "\\d{2} = genau zwei Ziffern, \\. = ein echter Punkt, "
            "\\d{4} = genau vier Ziffern."
        ),
    },
    {
        "name": "Uhrzeit (HH:MM:SS)",
        "pattern": r"(\d{2}:\d{2}:\d{2})",
        "explain": "Findet eine Uhrzeit wie 13:45:09. \\d{2} = genau zwei Ziffern.",
    },
    {
        "name": "Wort ohne Leerzeichen",
        "pattern": r"(\S+)",
        "explain": (
            "Findet ein zusammenhaengendes 'Wort' - alles bis zum naechsten "
            "Leerzeichen. Gut fuer Namen, Kennungen oder Codes."
        ),
    },
    {
        "name": "Rest der Zeile",
        "pattern": r"(.+)",
        "explain": (
            "Nimmt alles bis zum Zeilenende. Praktisch nach einem festen "
            "Begriff, z.B. Test:\\s*(.+) fuer alles hinter 'Test:'."
        ),
    },
    {
        "name": "Beschriftung: Wert",
        "pattern": r"Beschriftung:\s*(\S+)",
        "explain": (
            "Muster fuer Zeilen wie 'Anwender: Mustermann'.\n\n"
            "Ersetzen Sie 'Beschriftung' durch den echten Text vor dem Wert. "
            "\\s* erlaubt beliebig viele Leerzeichen dazwischen."
        ),
    },
    {
        "name": "Beliebige Zeichen dazwischen",
        "pattern": r".*?",
        "explain": (
            "Ueberbrueckt beliebigen Text zwischen zwei festen Teilen, "
            "z.B. S1\\b.*?(\\d+) - findet die erste Zahl irgendwo nach 'S1'.\n\n"
            "Kein eigener Wert: dieser Baustein hat keine Fanggruppe."
        ),
    },
    {
        "name": "Wortgrenze",
        "pattern": r"\b",
        "explain": (
            "Markiert eine Wortgrenze. \\bPCQ1\\b trifft 'PCQ1', aber nicht "
            "'PCQ10'. Verhindert versehentliche Teil-Treffer."
        ),
    },
    {
        "name": "Leerraum (ein oder mehr)",
        "pattern": r"\s+",
        "explain": "Steht fuer ein oder mehrere Leerzeichen/Tabs. Robust, wenn die Abstaende im PDF schwanken.",
    },
    {
        "name": "Analyzer Label + Wert",
        "pattern": r"Label:\s*(\S+)",
        "explain": (
            "Basis fuer Header-Zeilen wie 'Datum: 14.01.2026' oder 'Anwender: Fischer'. "
            "Ersetzen Sie 'Label' durch den echten Text vor dem Doppelpunkt."
        ),
    },
    {
        "name": "Analyzer Dezimalzahl",
        "pattern": r"(\d+(?:[\.,]\d+)?)",
        "explain": "Findet Werte wie 2,343, 17.3 oder 50 ohne eine Einheit festzulegen.",
    },
    {
        "name": "Analyzer Wert mit Einheit",
        "pattern": r"(\d+(?:[\.,]\d+)?\s*[A-Za-z/%]+(?:/[A-Za-z]+)?)",
        "explain": "Findet Werte wie 17,3 ng/ml oder 271 IU/ml. Einheit bleibt Teil des Treffers.",
    },
    {
        "name": "Analyzer Bereich",
        "pattern": r"(\d+(?:[\.,]\d+)?\s*-\s*\d+(?:[\.,]\d+)?)",
        "explain": "Findet Bereiche wie 8,7-26,0 oder 190-352.",
    },
    {
        "name": "Analyzer Dateiname .asy",
        "pattern": r"Test:.*[\\/]([^\\/]+\.asy)",
        "explain": "Findet in einer Test-Pfad-Zeile nur den Assay-Dateinamen, z.B. 25-OH Vitamin D.asy.",
    },
    {
        "name": "Analyzer Validation",
        "pattern": r"(Validationskriterien\s+(?:nicht\s+)?erfuellt)",
        "explain": "Findet den Validationsstatus. Bei Umlaut-Ausgabe ggf. erfuellt manuell anpassen.",
    },
    {
        "name": "Kit Charge",
        "pattern": r"Kit\s+([A-Za-z0-9]+)\s+\d{6}",
        "explain": "Findet die Kit-Charge in Zeilen wie 'Kit E251127AF 261126'.",
    },
    {
        "name": "Kit Haltbarkeit",
        "pattern": r"Kit\s+[A-Za-z0-9]+\s+(\d{6})",
        "explain": "Findet die sechsstellige Haltbarkeit hinter der Kit-Charge.",
    },
]


class RegexLibraryPopup(tk.Toplevel):
    """Kleines Nachschlagewerk; 'Einfuegen' setzt das Muster an die Cursorposition des Ziel-Entry."""

    def __init__(self, master: tk.Misc, target_entry: tk.Entry) -> None:
        super().__init__(master)
        self.title("Regex-Bibliothek")
        self.geometry("640x420")
        self.transient(master)
        self._target_entry = target_entry

        tk.Label(
            self,
            text=(
                "Baustein auswaehlen, Erklaerung lesen und mit 'Einfuegen' direkt "
                "in das Regex-Feld uebernehmen (an der Cursorposition)."
            ),
            anchor="w",
            justify="left",
            wraplength=600,
            fg="#444",
        ).pack(fill="x", padx=10, pady=(10, 6))

        body = tk.Frame(self)
        body.pack(fill="both", expand=True, padx=10, pady=(0, 6))

        self.tree, tree_frame = create_scrollable_treeview(
            body, columns=("pattern",), show="tree headings", height=10
        )
        self.tree.heading("#0", text="Baustein")
        self.tree.heading("pattern", text="Muster")
        self.tree.column("#0", width=210, anchor="w")
        self.tree.column("pattern", width=200, anchor="w")
        tree_frame.pack(side="left", fill="both", expand=True)
        for idx, row in enumerate(REGEX_LIBRARY):
            self.tree.insert("", tk.END, iid=str(idx), text=row["name"], values=(row["pattern"],))
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Double-1>", lambda _e: self._insert_selected())

        self.txt_explain = tk.Text(body, wrap="word", width=36, height=10)
        self.txt_explain.pack(side="right", fill="both", expand=True, padx=(8, 0))
        self.txt_explain.configure(state="disabled")

        nav = tk.Frame(self)
        nav.pack(fill="x", padx=10, pady=(0, 10))
        tk.Button(nav, text="Einfuegen", command=self._insert_selected).pack(side="left")
        tk.Button(nav, text="Schliessen", command=self.destroy).pack(side="right")

        self.tree.selection_set("0")
        self.tree.focus("0")

    def _selected_row(self) -> dict[str, str] | None:
        sel = self.tree.selection()
        if not sel:
            return None
        try:
            return REGEX_LIBRARY[int(sel[0])]
        except (ValueError, IndexError):
            return None

    def _on_select(self, _event: object = None) -> None:
        row = self._selected_row()
        if row is None:
            return
        self.txt_explain.configure(state="normal")
        self.txt_explain.delete("1.0", tk.END)
        self.txt_explain.insert(tk.END, f"{row['name']}\n\nMuster: {row['pattern']}\n\n{row['explain']}")
        self.txt_explain.configure(state="disabled")

    def _insert_selected(self) -> None:
        row = self._selected_row()
        if row is None:
            return
        try:
            pos = self._target_entry.index(tk.INSERT)
        except tk.TclError:
            pos = tk.END
        self._target_entry.insert(pos, row["pattern"])
        self._target_entry.focus_set()
