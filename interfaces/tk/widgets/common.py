from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from interfaces.tk.desktop_theme import (
    COLOR_BORDER,
    COLOR_CARD,
    COLOR_TEXT,
    COLOR_TEXT_MUTED,
    status_color,
)


class SectionHeader(ttk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        title: str,
        *,
        subtitle: str = "",
        action_text: str = "",
        on_action: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(master, style="CardInner.TFrame")
        self.columnconfigure(0, weight=1)
        ttk.Label(self, text=title, style="SectionTitle.TLabel").grid(row=0, column=0, sticky="w")
        if subtitle:
            ttk.Label(self, text=subtitle, style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(2, 0))
        if action_text and on_action is not None:
            ttk.Button(self, text=action_text, command=on_action).grid(row=0, column=1, rowspan=2, sticky="e")


class Card(ttk.Frame):
    def __init__(self, master: tk.Misc, *, padding: int = 12) -> None:
        super().__init__(master, style="Card.TFrame")
        wrapper = tk.Frame(self, background=COLOR_BORDER, padx=1, pady=1)
        wrapper.pack(fill="both", expand=True)
        self._inner = ttk.Frame(wrapper, style="CardInner.TFrame", padding=padding)
        self._inner.pack(fill="both", expand=True)

    @property
    def body(self) -> ttk.Frame:
        return self._inner


class StatusBadge(ttk.Label):
    def __init__(self, master: tk.Misc, text: str = "", *, kind: str = "neutral") -> None:
        super().__init__(master, text=text, style="Muted.TLabel")
        self.set_status(text, kind=kind)

    def set_status(self, text: str, *, kind: str = "neutral") -> None:
        self.configure(text=text, foreground=status_color(kind))


class EmptyState(ttk.Frame):
    def __init__(self, master: tk.Misc, message: str, *, hint: str = "") -> None:
        super().__init__(master, style="CardInner.TFrame")
        ttk.Label(self, text=message, foreground=COLOR_TEXT).pack(anchor="w")
        if hint:
            ttk.Label(self, text=hint, style="Muted.TLabel").pack(anchor="w", pady=(4, 0))


class ScrollableFrame(ttk.Frame):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, style="Content.TFrame")
        self._canvas = tk.Canvas(self, highlightthickness=0, background=COLOR_CARD, borderwidth=0)
        self._scrollbar = ttk.Scrollbar(self, orient="vertical", command=self._canvas.yview)
        self._inner = ttk.Frame(self._canvas, style="CardInner.TFrame")
        self._inner.bind("<Configure>", self._on_inner_configure)
        self._window_id = self._canvas.create_window((0, 0), window=self._inner, anchor="nw")
        self._canvas.configure(yscrollcommand=self._scrollbar.set)
        self._canvas.pack(side="left", fill="both", expand=True)
        self._scrollbar.pack(side="right", fill="y")
        self._canvas.bind("<Configure>", self._on_canvas_configure)

    @property
    def body(self) -> ttk.Frame:
        return self._inner

    def _on_inner_configure(self, _event: object) -> None:
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, event: tk.Event) -> None:
        self._canvas.itemconfigure(self._window_id, width=event.width)


def create_readonly_tree(
    master: tk.Misc,
    columns: tuple[str, ...],
    headings: tuple[str, ...],
    *,
    height: int = 8,
    stretch_last: bool = True,
) -> ttk.Treeview:
    tree = ttk.Treeview(master, columns=columns, show="headings", height=height, selectmode="browse")
    for index, column in enumerate(columns):
        heading = headings[index] if index < len(headings) else column
        tree.heading(column, text=heading)
        tree.column(column, width=120, stretch=stretch_last and index == len(columns) - 1)
    return tree


def create_scrollable_tree(
    master: tk.Misc,
    columns: tuple[str, ...],
    headings: tuple[str, ...],
    *,
    height: int = 8,
    stretch_last: bool = True,
) -> tuple[ttk.Frame, ttk.Treeview]:
    frame = ttk.Frame(master, style="CardInner.TFrame")
    tree = create_readonly_tree(
        frame,
        columns,
        headings,
        height=height,
        stretch_last=stretch_last,
    )
    y_scrollbar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    x_scrollbar = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
    tree.configure(yscrollcommand=y_scrollbar.set, xscrollcommand=x_scrollbar.set)
    tree.grid(row=0, column=0, sticky="nsew")
    y_scrollbar.grid(row=0, column=1, sticky="ns")
    x_scrollbar.grid(row=1, column=0, sticky="ew")
    frame.rowconfigure(0, weight=1)
    frame.columnconfigure(0, weight=1)
    return frame, tree
