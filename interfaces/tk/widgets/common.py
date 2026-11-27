from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Sequence
from tkinter import ttk

from interfaces.tk.desktop_theme import (
    COLOR_BG,
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
    def __init__(self, master: tk.Misc, *, padding: int = 12, rounded: bool = False,
                 background: str = COLOR_CARD) -> None:
        super().__init__(master, style="Content.TFrame" if rounded else "Card.TFrame")
        self._rounded = rounded
        if rounded:
            self._card_background = background
            self._decoration = tk.Canvas(self, background=COLOR_BG, highlightthickness=0, borderwidth=0, takefocus=False)
            self._decoration.place(x=0, y=0, relwidth=1, relheight=1)
            self._inner = ttk.Frame(self, style="CardInner.TFrame", padding=max(0, padding - 12))
            self._inner.pack(fill="both", expand=True, padx=12, pady=(12, 14))
            self._decoration.bind("<Configure>", self._draw_rounded_card)
            return
        wrapper = tk.Frame(self, background=COLOR_BORDER, padx=1, pady=1)
        wrapper.pack(fill="both", expand=True)
        self._inner = ttk.Frame(wrapper, style="CardInner.TFrame", padding=padding)
        self._inner.pack(fill="both", expand=True)

    def _draw_rounded_card(self, event: tk.Event) -> None:
        width, height = event.width, event.height
        if width < 4 or height < 6:
            return
        self._decoration.delete("all")

        def outline(x: int, y: int, right: int, bottom: int) -> tuple:
            radius = min(12, (right - x) // 2, (bottom - y) // 2)
            return (x + radius, y, right - radius, y, right, y, right, y + radius,
                    right, bottom - radius, right, bottom, right - radius, bottom,
                    x + radius, bottom, x, bottom, x, bottom - radius, x, y + radius, x, y)

        self._decoration.create_polygon(outline(1, 3, width - 1, height - 1), smooth=True,
                                        splinesteps=24, fill="#e8edf4", outline="")
        self._decoration.create_polygon(outline(1, 1, width - 1, height - 3), smooth=True,
                                        splinesteps=24, fill=self._card_background, outline=COLOR_BORDER, width=1)

    @property
    def body(self) -> ttk.Frame:
        return self._inner


class StatusBadge(ttk.Label):
    def __init__(self, master: tk.Misc, text: str = "", *, kind: str = "neutral") -> None:
        super().__init__(master, text=text, style="Muted.TLabel")
        self.set_status(text, kind=kind)

    def set_status(self, text: str, *, kind: str = "neutral") -> None:
        self.configure(text=text, foreground=status_color(kind))


class MultiSelectFilter(ttk.Menubutton):
    """A native check-menu; selections are OR-ed within one filter."""

    def __init__(self, master: tk.Misc, label: str, *, on_change: Callable[[], None]) -> None:
        super().__init__(master, text=f"{label}: Alle", direction="below")
        self._label = label
        self._on_change = on_change
        self._selected: frozenset[str] = frozenset()
        self._variables: dict[str, tk.BooleanVar] = {}
        self._menu = tk.Menu(self, tearoff=False)
        self.configure(menu=self._menu)

    @property
    def selected_values(self) -> frozenset[str]:
        return self._selected

    def set_options(self, values: Sequence[str]) -> None:
        self._menu.delete(0, "end")
        self._menu.add_command(label="Alle anzeigen", command=lambda: self.select_values(()))
        self._menu.add_separator()
        self._variables.clear()
        for value in sorted(set(values) | self._selected, key=str.casefold):
            variable = tk.BooleanVar(master=self, value=value in self._selected)
            self._variables[value] = variable
            self._menu.add_checkbutton(label=value, variable=variable, command=self._changed)

    def select_values(self, values: Sequence[str]) -> None:
        selected = frozenset(values)
        for value, variable in self._variables.items():
            variable.set(value in selected)
        self._selected = selected
        self._update_label()
        self._on_change()

    def _changed(self) -> None:
        self._selected = frozenset(value for value, variable in self._variables.items() if variable.get())
        self._update_label()
        self._on_change()

    def _update_label(self) -> None:
        self.configure(text=f"{self._label}: {len(self._selected)} gewählt" if self._selected else f"{self._label}: Alle")


class EmptyState(ttk.Frame):
    def __init__(self, master: tk.Misc, message: str, *, hint: str = "") -> None:
        super().__init__(master, style="CardInner.TFrame")
        ttk.Label(self, text=message, foreground=COLOR_TEXT).pack(anchor="w")
        if hint:
            ttk.Label(self, text=hint, style="Muted.TLabel").pack(anchor="w", pady=(4, 0))


class OverflowScrollbar(ttk.Scrollbar):
    """A native overflow-only overlay: showing it never resizes its viewport."""

    def __init__(self, master: tk.Misc, *, orient: str, command: Callable) -> None:
        super().__init__(master, orient=orient, command=command,
                         style="Slim.Vertical.TScrollbar" if orient == "vertical" else "Slim.Horizontal.TScrollbar")
        self._vertical = orient == "vertical"
        self._needed = False
        self._update_id: str | None = None
        self.bind("<Destroy>", self._cancel_update)

    def set(self, first: str, last: str) -> None:
        super().set(first, last)
        low, high = float(first), float(last)
        self._needed = low > 1e-7 or high < 1.0 - 1e-7
        if self._update_id is None:
            self._update_id = self.after_idle(self._apply_visibility)

    def _apply_visibility(self) -> None:
        self._update_id = None
        if self._needed:
            if self._vertical:
                self.place(relx=1, rely=0, relheight=1, width=8, anchor="ne")
            else:
                self.place(relx=0, rely=1, relwidth=1, height=8, anchor="sw")
            self.lift()
        else:
            self.place_forget()

    def _cancel_update(self, event: tk.Event) -> None:
        if event.widget is self and self._update_id is not None:
            self.after_cancel(self._update_id)
            self._update_id = None


class ScrollableFrame(ttk.Frame):
    def __init__(self, master: tk.Misc, *, autohide: bool = False) -> None:
        super().__init__(master, style="Content.TFrame")
        self._auto_layout = bool(autohide)
        self._canvas = tk.Canvas(self, highlightthickness=0, background=COLOR_CARD, borderwidth=0)
        scrollbar = OverflowScrollbar if autohide else ttk.Scrollbar
        self._scrollbar = scrollbar(self, orient="vertical", command=self._canvas.yview)
        self._inner = ttk.Frame(self._canvas, style="CardInner.TFrame")
        self._inner.bind("<Configure>", self._on_inner_configure)
        self._window_id = self._canvas.create_window((0, 0), window=self._inner, anchor="nw")
        self._canvas.configure(yscrollcommand=self._scrollbar.set)
        self._canvas.pack(side="left", fill="both", expand=True)
        if not autohide:
            self._scrollbar.pack(side="right", fill="y")
        self._canvas.bind("<Configure>", self._on_canvas_configure)
        self._canvas.bind("<Prior>", lambda _event: self._canvas.yview_scroll(-1, "pages"))
        self._canvas.bind("<Next>", lambda _event: self._canvas.yview_scroll(1, "pages"))
        self._canvas.bind("<Home>", lambda _event: self._canvas.yview_moveto(0))
        self._canvas.bind("<End>", lambda _event: self._canvas.yview_moveto(1))
        self._content_watchers: set[str] = set()
        self._content_refresh_id: str | None = None
        self.bind("<Destroy>", self._cancel_content_refresh)
        self._schedule_content_refresh()

    @property
    def body(self) -> ttk.Frame:
        return self._inner

    def _on_inner_configure(self, _event: object) -> None:
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))
        if self._auto_layout and self._inner.winfo_height() <= self._canvas.winfo_height():
            self._canvas.yview_moveto(0)
        self._schedule_content_refresh()

    def _on_canvas_configure(self, event: tk.Event) -> None:
        self._canvas.itemconfigure(self._window_id, width=event.width)
        if self._auto_layout and self._inner.winfo_height() <= event.height:
            self._canvas.yview_moveto(0)
        self._schedule_content_refresh()

    def _schedule_content_refresh(self, _event: object = None) -> None:
        if self._auto_layout and self._content_refresh_id is None:
            self._content_refresh_id = self.after_idle(self._refresh_content_layout)

    def _refresh_content_layout(self) -> None:
        self._content_refresh_id = None

        def watch(widget: tk.Misc) -> None:
            for child in widget.winfo_children():
                if str(child) not in self._content_watchers:
                    self._content_watchers.add(str(child))
                    child.bind("<Configure>", self._schedule_content_refresh, add="+")
                watch(child)

        watch(self._inner)
        # Canvas may not resize an off-screen embedded window after its content
        # shrinks. Synchronize its requested height without changing the viewport.
        height = self._inner.winfo_reqheight()
        self._canvas.itemconfigure(self._window_id, height=0)
        self._canvas.configure(scrollregion=(0, 0, self._canvas.winfo_width(), height))
        if height <= self._canvas.winfo_height():
            self._canvas.yview_moveto(0)

    def _cancel_content_refresh(self, event: tk.Event) -> None:
        if event.widget is self and self._content_refresh_id is not None:
            self.after_cancel(self._content_refresh_id)
            self._content_refresh_id = None


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
    autohide: bool = False,
) -> tuple[ttk.Frame, ttk.Treeview]:
    frame = ttk.Frame(master, style="CardInner.TFrame")
    tree = create_readonly_tree(
        frame,
        columns,
        headings,
        height=height,
        stretch_last=stretch_last,
    )
    scrollbar = OverflowScrollbar if autohide else ttk.Scrollbar
    y_scrollbar = scrollbar(frame, orient="vertical", command=tree.yview)
    x_scrollbar = scrollbar(frame, orient="horizontal", command=tree.xview)
    tree.configure(yscrollcommand=y_scrollbar.set, xscrollcommand=x_scrollbar.set)
    tree.grid(row=0, column=0, sticky="nsew")
    if not autohide:
        y_scrollbar.grid(row=0, column=1, sticky="ns")
        x_scrollbar.grid(row=1, column=0, sticky="ew")
    frame.rowconfigure(0, weight=1)
    frame.columnconfigure(0, weight=1)
    return frame, tree
