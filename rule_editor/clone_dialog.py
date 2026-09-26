"""Dialog: aktive Assay-Regel vollständig in einen neuen Entwurf duplizieren."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable

from interfaces.tk.desktop_theme import configure_desktop_theme


class CloneRulesetDialog(tk.Toplevel):
    def __init__(
        self,
        master: tk.Misc,
        *,
        rules: object,
        active_rows: list[dict[str, object]],
        initial_source_key: str = "",
        initial_target_key: str = "",
        initial_target_name: str = "",
        on_completed: Callable[[dict[str, object]], None],
    ) -> None:
        super().__init__(master)
        configure_desktop_theme(self)
        self.title("Als neue Regel duplizieren")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()

        self._rules = rules
        self._on_completed = on_completed
        self._active_rows = active_rows

        self.var_source = tk.StringVar(value="")
        self.var_target_key = tk.StringVar(value=initial_target_key)
        self.var_target_name = tk.StringVar(value=initial_target_name)

        body = tk.Frame(self, padx=12, pady=12)
        body.pack(fill="both", expand=True)

        tk.Label(body, text="Aktive Quelle").grid(row=0, column=0, sticky="w")
        source_values = [
            f"{row.get('assay_key', '')} | {row.get('assay_name', '') or row.get('assay_key', '')}"
            for row in active_rows
        ]
        self.cmb_source = ttk.Combobox(body, textvariable=self.var_source, values=source_values, width=56, state="readonly")
        self.cmb_source.grid(row=1, column=0, columnspan=2, sticky="we", pady=(4, 10))
        if initial_source_key:
            for display, row in zip(source_values, active_rows):
                if str(row.get("assay_key", "")).strip() == initial_source_key.strip():
                    self.var_source.set(display)
                    break
        elif source_values:
            self.var_source.set(source_values[0])

        tk.Label(body, text="Neuer Assay-Schlüssel").grid(row=2, column=0, sticky="w")
        tk.Entry(body, textvariable=self.var_target_key, width=24).grid(row=2, column=1, sticky="w", pady=(4, 6))
        tk.Label(body, text="Neuer Assay-Name").grid(row=3, column=0, sticky="w")
        tk.Entry(body, textvariable=self.var_target_name, width=42).grid(row=3, column=1, sticky="we", pady=(0, 10))

        buttons = tk.Frame(body)
        buttons.grid(row=4, column=0, columnspan=2, sticky="e")
        tk.Button(buttons, text="Abbrechen", command=self.destroy).pack(side="right")
        tk.Button(buttons, text="Duplizieren", command=self._on_submit).pack(side="right", padx=(0, 8))

        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _selected_source_key(self) -> str:
        display = self.var_source.get().strip()
        for row in self._active_rows:
            label = f"{row.get('assay_key', '')} | {row.get('assay_name', '') or row.get('assay_key', '')}"
            if label == display:
                return str(row.get("assay_key", "")).strip()
        return ""

    def _active_keys(self) -> set[str]:
        return {str(row.get("assay_key", "")).strip() for row in self._active_rows if str(row.get("assay_key", "")).strip()}

    def _on_submit(self) -> None:
        source_key = self._selected_source_key()
        target_key = self.var_target_key.get().strip()
        target_name = self.var_target_name.get().strip()
        if not source_key:
            messagebox.showinfo("Regel duplizieren", "Bitte eine aktive Quelle auswählen.", parent=self)
            return
        if not target_key or not target_name:
            messagebox.showinfo("Regel duplizieren", "Neuer Assay-Schlüssel und neuer Assay-Name sind erforderlich.", parent=self)
            return
        if target_key in self._active_keys():
            messagebox.showinfo(
                "Regel duplizieren",
                f"Der Ziel-Assay-Schlüssel {target_key} entspricht einer aktiven Regel. Es wurde nichts geändert.",
                parent=self,
            )
            return

        try:
            result = self._rules.clone_ruleset_to_draft(
                source_key,
                target_key,
                target_name,
                overwrite=False,
                include_fields=True,
            )
        except Exception as exc:
            messagebox.showerror("Regel duplizieren", str(exc), parent=self)
            return

        if result.get("status") == "exists":
            messagebox.showinfo(
                "Regel duplizieren",
                (
                    "Der Ziel-Entwurf existiert bereits und wurde nicht geändert:\n"
                    f"{result.get('draft_path')}"
                ),
                parent=self,
            )
            return

        self._on_completed(result)
        self.destroy()
