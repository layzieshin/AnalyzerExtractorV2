"""Thin standalone host; the product shell embeds the same RuleEditorWorkspace."""
from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path

from interfaces.tk.desktop_theme import configure_desktop_theme
from rule_editor.editor_workspace import RuleEditorWorkspace
from src.application.api import RuleSuiteController
from src.runtime.api import resolve_app_root


class RuleEditorWindow(tk.Tk):
    def __init__(self, project_root: str | Path | None = None) -> None:
        super().__init__()
        self.title("Analyzer Result Extractor – Regelverwaltung")
        self.minsize(1024, 768)
        self.geometry("1440x900")
        self._maximize_on_windows()
        configure_desktop_theme(self)
        root = Path(project_root).resolve() if project_root is not None else resolve_app_root(Path(__file__))
        self.workspace = RuleEditorWorkspace(self, root, rules=RuleSuiteController(root),
            controller_factory=RuleSuiteController, on_close=self.destroy)
        self.workspace.pack(fill="both", expand=True)
        self.protocol("WM_DELETE_WINDOW", self.workspace._on_editor_close)

    def __getattr__(self, name):
        # Compatibility reads delegate to the single Frame owner.
        workspace = self.__dict__.get("workspace")
        if workspace is not None and hasattr(workspace, name):
            return getattr(workspace, name)
        return super().__getattr__(name)

    def _maximize_on_windows(self) -> None:
        if sys.platform == "win32":
            try:
                self.state("zoomed")
            except tk.TclError:
                self.geometry("1440x900")

    def destroy(self) -> None:
        workspace = self.__dict__.get("workspace")
        if workspace is not None:
            workspace.destroy()
        super().destroy()


if __name__ == "__main__":
    RuleEditorWindow().mainloop()
