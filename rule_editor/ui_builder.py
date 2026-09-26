"""UiBuilderMixin: Komposition von Inventar, Arbeitsbereich und Seitenwechsel."""
from __future__ import annotations

import tkinter as tk

from .inventory_view import build_inventory_view
from .toolbar import build_toolbar
from .workspace import build_workspace


class UiBuilderMixin:
    def _build_ui(self) -> None:
        self._step_nav_buttons: list[tuple[str, tk.Button]] = []
        self._guide_tab_order = ["draft", "pdf", "fields", "meta", "validate", "validate"]
        self._active_page = "inventory"
        self._advanced_visible = False

        build_toolbar(self)

        content = tk.Frame(self)
        content.pack(fill="both", expand=True)
        content.rowconfigure(0, weight=1)
        content.columnconfigure(0, weight=1)

        self.page_inventory = tk.Frame(content)
        self.page_workspace = tk.Frame(content)
        self.page_inventory.grid(row=0, column=0, sticky="nsew")
        build_inventory_view(self, self.page_inventory)
        build_workspace(self, self.page_workspace)
        self.page_workspace.grid(row=0, column=0, sticky="nsew")
        self.page_workspace.grid_remove()
        self.after_idle(self._place_workspace_sashes)

    def _show_page(self, page: str) -> None:
        if page == "workspace":
            self.page_inventory.grid_remove()
            self.page_workspace.grid()
            self._active_page = "workspace"
            return
        self.page_workspace.grid_remove()
        self.page_inventory.grid()
        self._active_page = "inventory"
        self._hide_advanced()

    def _show_advanced(self, section: str | None = None) -> None:
        self._show_page("workspace")
        self.workspace_panes.grid_remove()
        self.frame_advanced.grid()
        self._advanced_visible = True
        if section:
            self.after_idle(lambda: self._scroll_advanced_to(section))

    def _scroll_advanced_to(self, section: str) -> None:
        frame = getattr(self, "_advanced_sections", {}).get(section)
        canvas = getattr(self, "advanced_canvas", None)
        inner = getattr(self, "advanced_inner", None)
        if frame is None or canvas is None or inner is None:
            return
        inner.update_idletasks()
        height = max(1, inner.winfo_height())
        canvas.yview_moveto(max(0.0, min(1.0, frame.winfo_y() / height)))

    def _hide_advanced(self) -> None:
        frame = getattr(self, "frame_advanced", None)
        if frame is None:
            self._advanced_visible = False
            return
        frame.grid_remove()
        panes = getattr(self, "workspace_panes", None)
        if panes is not None:
            panes.grid()
        self._advanced_visible = False

    def _toggle_advanced(self) -> None:
        if self._advanced_visible:
            self._hide_advanced()
        else:
            self._show_advanced()

    def _place_workspace_sashes(self) -> None:
        panes = getattr(self, "workspace_panes", None)
        if panes is None or not panes.winfo_exists():
            return
        width = panes.winfo_width()
        if width < 900:
            return
        left = max(220, int(width * 0.22))
        middle_end = max(left + 360, int(width * 0.64))
        if middle_end > width - 270:
            middle_end = width - 270
        try:
            panes.sashpos(0, left)
            panes.sashpos(1, middle_end)
        except tk.TclError:
            return

    def _add_collapsible_help(self, parent: tk.Widget, key: str, short_text: str, wraplength: int) -> None:
        from .constants import HELP_TEXTS

        box = tk.Frame(parent, bd=1, relief=tk.GROOVE)
        box.pack(fill="x")
        head = tk.Frame(box)
        head.pack(fill="x", padx=6, pady=4)
        tk.Label(head, text=short_text, anchor="w", justify="left", wraplength=wraplength, fg="#444").pack(
            side="left", fill="x", expand=True
        )
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
