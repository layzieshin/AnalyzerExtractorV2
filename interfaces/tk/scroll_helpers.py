"""Shared scrollable Treeview/Listbox factories and Treeview column sorting."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable


def bind_mousewheel(widget: tk.Misc, scrollable: tk.Misc) -> None:
    """Scroll *scrollable* when the pointer is over *widget* (no global bind_all)."""

    def _on_mousewheel(event: tk.Event) -> None:
        if event.num == 4:
            scrollable.yview_scroll(-1, "units")
        elif event.num == 5:
            scrollable.yview_scroll(1, "units")
        else:
            delta = getattr(event, "delta", 0)
            if delta:
                scrollable.yview_scroll(int(-1 * (delta / 120)), "units")

    widget.bind("<MouseWheel>", _on_mousewheel)
    widget.bind("<Button-4>", _on_mousewheel)
    widget.bind("<Button-5>", _on_mousewheel)


def create_scrollable_treeview(
    parent: tk.Misc,
    *,
    horizontal: bool = False,
    mousewheel: bool = True,
    **treeview_kwargs: Any,
) -> tuple[ttk.Treeview, tk.Frame]:
    frame = tk.Frame(parent)
    frame.rowconfigure(0, weight=1)
    frame.columnconfigure(0, weight=1)

    tree = ttk.Treeview(frame, **treeview_kwargs)
    yscroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=yscroll.set)
    tree.grid(row=0, column=0, sticky="nsew")
    yscroll.grid(row=0, column=1, sticky="ns")

    if horizontal:
        xscroll = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
        tree.configure(xscrollcommand=xscroll.set)
        frame.rowconfigure(1, weight=0)
        frame.columnconfigure(0, weight=1)
        xscroll.grid(row=1, column=0, sticky="ew")

    if mousewheel:
        bind_mousewheel(tree, tree)

    return tree, frame


def create_scrollable_listbox(
    parent: tk.Misc,
    *,
    horizontal: bool = False,
    mousewheel: bool = True,
    **listbox_kwargs: Any,
) -> tuple[tk.Listbox, tk.Frame]:
    frame = tk.Frame(parent)
    frame.rowconfigure(0, weight=1)
    frame.columnconfigure(0, weight=1)

    listbox = tk.Listbox(frame, **listbox_kwargs)
    yscroll = ttk.Scrollbar(frame, orient="vertical", command=listbox.yview)
    listbox.configure(yscrollcommand=yscroll.set)
    listbox.grid(row=0, column=0, sticky="nsew")
    yscroll.grid(row=0, column=1, sticky="ns")

    if horizontal:
        xscroll = ttk.Scrollbar(frame, orient="horizontal", command=listbox.xview)
        listbox.configure(xscrollcommand=xscroll.set)
        frame.rowconfigure(1, weight=0)
        frame.columnconfigure(0, weight=1)
        xscroll.grid(row=1, column=0, sticky="ew")

    if mousewheel:
        bind_mousewheel(listbox, listbox)

    return listbox, frame


class TreeviewSorter:
    """Sort top-level Treeview rows via tree.move without delete/insert."""

    def __init__(
        self,
        tree: ttk.Treeview,
        *,
        numeric_columns: tuple[str, ...] = (),
        date_columns: tuple[str, ...] = (),
    ) -> None:
        self._tree = tree
        self._numeric = set(numeric_columns)
        self._date = set(date_columns)
        self._base_headings: dict[str, str] = {}
        self._sort_col: str | None = None
        self._reverse = False

    def attach(self, base_headings: dict[str, str]) -> None:
        self._base_headings = dict(base_headings)
        for col, title in base_headings.items():
            self._tree.heading(col, text=title, command=self._make_sort_command(col))

    def resort(self) -> None:
        if self._sort_col is not None:
            self._apply_sort()
            self._update_headings()

    def _make_sort_command(self, col: str) -> Callable[[], None]:
        def _command() -> None:
            self._sort_by(col)

        return _command

    def _sort_by(self, col: str) -> None:
        if self._sort_col == col:
            self._reverse = not self._reverse
        else:
            self._sort_col = col
            self._reverse = False
        self._apply_sort()
        self._update_headings()

    def _apply_sort(self) -> None:
        col = self._sort_col
        if col is None:
            return
        children = list(self._tree.get_children(""))
        if len(children) < 2:
            return
        ordered = sorted(children, key=lambda iid: self._sort_key(iid, col), reverse=self._reverse)
        for index, iid in enumerate(ordered):
            self._tree.move(iid, "", index)

    def _sort_key(self, iid: str, col: str) -> tuple[int, Any]:
        if col == "#0":
            value = self._tree.item(iid, "text")
        else:
            columns = tuple(self._tree["columns"])
            if col in columns:
                idx = columns.index(col)
                values = self._tree.item(iid, "values")
                value = values[idx] if idx < len(values) else ""
            else:
                value = self._tree.set(iid, col)
        return self._coerce(value, col)

    def _coerce(self, value: object, col: str) -> tuple[int, Any]:
        text = "" if value is None else str(value)
        if col in self._numeric:
            try:
                return (0, float(text.replace(",", ".")))
            except ValueError:
                return (1, text.lower())
        if col in self._date:
            return (0, text)
        return (0, text.lower())

    def _update_headings(self) -> None:
        arrow = " ↓" if self._reverse else " ↑"
        for col, title in self._base_headings.items():
            if col == self._sort_col:
                self._tree.heading(col, text=f"{title}{arrow}", command=self._make_sort_command(col))
            else:
                self._tree.heading(col, text=title, command=self._make_sort_command(col))
