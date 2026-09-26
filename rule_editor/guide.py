"""GuideMixin: Bereichshilfe und Einstieg in den echten Step-by-Step-Editor."""
from __future__ import annotations

from tkinter import messagebox

from .constants import HELP_TEXTS


class GuideMixin:
    def _show_help(self, key: str) -> None:
        text = HELP_TEXTS.get(key, "Keine Hilfe verfuegbar.")
        messagebox.showinfo("Bereichshilfe", text)

    def open_step_by_step(self) -> None:
        self.on_open_wizard(intent="neutral")
