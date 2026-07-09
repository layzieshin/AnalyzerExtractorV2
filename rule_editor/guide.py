"""GuideMixin: Step-by-Step-Guide und Hilfe-Popups."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

from .constants import HELP_TEXTS, STEP_BY_STEP_GUIDE


class GuideMixin:
    def _show_help(self, key: str) -> None:
        text = HELP_TEXTS.get(key, "Keine Hilfe verfuegbar.")
        messagebox.showinfo("Bereichshilfe", text)

    def open_step_by_step(self) -> None:
        if self._guide_window is not None and self._guide_window.winfo_exists():
            self._guide_window.deiconify()
            self._guide_window.lift()
            self._guide_window.focus_force()
            return

        self._guide_window = tk.Toplevel(self)
        self._guide_window.title("RuleSuite - Step by Step")
        self._guide_window.geometry("620x460")
        self._guide_window.protocol("WM_DELETE_WINDOW", self._close_step_by_step)

        self._guide_title_var = tk.StringVar(value="")
        tk.Label(
            self._guide_window,
            textvariable=self._guide_title_var,
            font=("Segoe UI", 11, "bold"),
            anchor="w",
            justify="left",
            wraplength=580,
        ).pack(fill="x", padx=12, pady=(12, 8))

        self._guide_text_widget = tk.Text(self._guide_window, wrap="word", height=16)
        self._guide_text_widget.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self._guide_text_widget.configure(state="disabled")

        nav = tk.Frame(self._guide_window)
        nav.pack(fill="x", padx=12, pady=(0, 12))
        tk.Button(nav, text="Zurueck", command=self._guide_prev).pack(side="left")
        tk.Button(nav, text="Weiter", command=self._guide_next).pack(side="left", padx=(8, 0))
        tk.Button(nav, text="Zum passenden Tab", command=self._guide_open_tab).pack(side="left", padx=(12, 0))
        tk.Button(nav, text="Schliessen", command=self._close_step_by_step).pack(side="right")

        self._guide_idx = 0
        self._render_guide_step()

    def _render_guide_step(self) -> None:
        if self._guide_title_var is None or self._guide_text_widget is None:
            return
        step = STEP_BY_STEP_GUIDE[self._guide_idx]
        self._guide_title_var.set(f"{step['title']}  ({self._guide_idx + 1}/{len(STEP_BY_STEP_GUIDE)})")
        self._guide_text_widget.configure(state="normal")
        self._guide_text_widget.delete("1.0", tk.END)
        self._guide_text_widget.insert(tk.END, step["text"])
        self._guide_text_widget.configure(state="disabled")

    def _guide_prev(self) -> None:
        if self._guide_idx > 0:
            self._guide_idx -= 1
            self._render_guide_step()

    def _guide_next(self) -> None:
        if self._guide_idx < len(STEP_BY_STEP_GUIDE) - 1:
            self._guide_idx += 1
            self._render_guide_step()

    def _guide_open_tab(self) -> None:
        if not self._guide_tab_order:
            return
        idx = min(self._guide_idx, len(self._guide_tab_order) - 1)
        self._select_tab(self._guide_tab_order[idx])

    def _close_step_by_step(self) -> None:
        if self._guide_window is not None and self._guide_window.winfo_exists():
            self._guide_window.destroy()
        self._guide_window = None
        self._guide_title_var = None
        self._guide_text_widget = None
