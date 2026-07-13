"""Dialog: aktives Regelwerk sicher in Ziel-Draft klonen (AP-16C)."""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Callable

from src.rulesuite.api import clone_ruleset_to_draft, draft_path_for_assay


class CloneRulesetDialog(tk.Toplevel):
    def __init__(
        self,
        master: tk.Misc,
        *,
        project_root: str,
        active_rows: list[dict[str, object]],
        draft_rows: list[dict[str, object]],
        initial_source_key: str = "",
        initial_target_key: str = "",
        initial_target_name: str = "",
        initial_target_draft_path: str = "",
        on_completed: Callable[[dict[str, object]], None],
    ) -> None:
        super().__init__(master)
        self.title("Regelwerk als Basis verwenden")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()

        self._project_root = project_root
        self._on_completed = on_completed
        self._active_rows = active_rows
        self._draft_rows = draft_rows

        self.var_source = tk.StringVar(value="")
        self.var_target_mode = tk.StringVar(value="new")
        self.var_target_draft = tk.StringVar(value="")
        self.var_target_key = tk.StringVar(value=initial_target_key)
        self.var_target_name = tk.StringVar(value=initial_target_name)
        self.var_include_fields = tk.BooleanVar(value=True)

        body = tk.Frame(self, padx=12, pady=12)
        body.pack(fill="both", expand=True)

        tk.Label(body, text="Basis-Regelwerk (aktiv)").grid(row=0, column=0, sticky="w")
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

        tk.Label(body, text="Ziel").grid(row=2, column=0, sticky="w")
        target_frame = tk.Frame(body)
        target_frame.grid(row=3, column=0, columnspan=2, sticky="we", pady=(4, 10))
        tk.Radiobutton(
            target_frame,
            text="Neuer Assay-Key/Name",
            variable=self.var_target_mode,
            value="new",
            command=self._sync_target_mode,
        ).pack(anchor="w")
        new_frame = tk.Frame(target_frame)
        new_frame.pack(fill="x", padx=16, pady=(2, 6))
        tk.Label(new_frame, text="Assay-Key").grid(row=0, column=0, sticky="w")
        tk.Entry(new_frame, textvariable=self.var_target_key, width=16).grid(row=0, column=1, sticky="w", padx=(6, 12))
        tk.Label(new_frame, text="Assay-Name").grid(row=0, column=2, sticky="w")
        tk.Entry(new_frame, textvariable=self.var_target_name, width=34).grid(row=0, column=3, sticky="w", padx=(6, 0))
        self._new_frame = new_frame

        tk.Radiobutton(
            target_frame,
            text="Bestehender Draft",
            variable=self.var_target_mode,
            value="existing",
            command=self._sync_target_mode,
        ).pack(anchor="w")
        draft_values = [
            f"{row.get('assay_key', '')} | {row.get('assay_name', '') or Path(str(row.get('path', ''))).name}"
            for row in draft_rows
        ]
        self.cmb_target_draft = ttk.Combobox(
            target_frame,
            textvariable=self.var_target_draft,
            values=draft_values,
            width=54,
            state="readonly",
        )
        self.cmb_target_draft.pack(anchor="w", padx=16, pady=(2, 0))
        if initial_target_draft_path:
            for display, row in zip(draft_values, draft_rows):
                if str(row.get("path", "")).strip() == initial_target_draft_path.strip():
                    self.var_target_draft.set(display)
                    self.var_target_mode.set("existing")
                    break

        tk.Checkbutton(
            body,
            text="Zusatzfelder/Format uebernehmen",
            variable=self.var_include_fields,
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(0, 10))

        buttons = tk.Frame(body)
        buttons.grid(row=5, column=0, columnspan=2, sticky="e")
        tk.Button(buttons, text="Abbrechen", command=self.destroy).pack(side="right")
        tk.Button(buttons, text="Erstellen", command=self._on_submit).pack(side="right", padx=(0, 8))

        self._sync_target_mode()
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _sync_target_mode(self) -> None:
        is_new = self.var_target_mode.get() == "new"
        state = tk.NORMAL if is_new else tk.DISABLED
        for child in self._new_frame.winfo_children():
            try:
                child.configure(state=state)
            except tk.TclError:
                pass
        self.cmb_target_draft.configure(state="readonly" if not is_new else "disabled")

    def _selected_source_key(self) -> str:
        display = self.var_source.get().strip()
        for row in self._active_rows:
            label = f"{row.get('assay_key', '')} | {row.get('assay_name', '') or row.get('assay_key', '')}"
            if label == display:
                return str(row.get("assay_key", "")).strip()
        return ""

    def _selected_target(self) -> tuple[str, str]:
        if self.var_target_mode.get() == "existing":
            display = self.var_target_draft.get().strip()
            for row in self._draft_rows:
                label = (
                    f"{row.get('assay_key', '')} | {row.get('assay_name', '') or Path(str(row.get('path', ''))).name}"
                )
                if label == display:
                    return str(row.get("assay_key", "")).strip(), str(row.get("assay_name", "")).strip()
            return "", ""
        return self.var_target_key.get().strip(), self.var_target_name.get().strip()

    def _on_submit(self) -> None:
        source_key = self._selected_source_key()
        target_key, target_name = self._selected_target()
        if not source_key:
            messagebox.showinfo("Regelwerk klonen", "Bitte ein Basis-Regelwerk auswaehlen.", parent=self)
            return
        if not target_key or not target_name:
            messagebox.showinfo("Regelwerk klonen", "Ziel-Assay-Key und -Name sind erforderlich.", parent=self)
            return

        target_path = draft_path_for_assay(self._project_root, target_key)
        overwrite = False
        if Path(target_path).exists():
            proceed = messagebox.askokcancel(
                "Draft existiert",
                (
                    f"Ziel-Draft existiert bereits:\n{target_path}\n\n"
                    "Mit 'OK' wird der vorhandene Draft ueberschrieben.\n"
                    "'Abbrechen' bricht ohne Aenderung ab."
                ),
                parent=self,
            )
            if not proceed:
                return
            overwrite = True

        try:
            result = clone_ruleset_to_draft(
                self._project_root,
                source_key,
                target_key,
                target_name,
                overwrite=overwrite,
                include_fields=self.var_include_fields.get(),
            )
        except Exception as exc:
            messagebox.showerror("Regelwerk klonen", str(exc), parent=self)
            return

        if result.get("status") == "exists":
            messagebox.showinfo(
                "Regelwerk klonen",
                f"Ziel-Draft existiert bereits und wurde nicht geaendert:\n{result.get('draft_path')}",
                parent=self,
            )
            return

        self._on_completed(result)
        self.destroy()
