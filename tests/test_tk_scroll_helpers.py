from __future__ import annotations

import tkinter as tk

import pytest

from interfaces.tk.scroll_helpers import (
    TreeviewSorter,
    create_scrollable_listbox,
    create_scrollable_treeview,
)


class _FakeTree:
    def __init__(self, columns: tuple[str, ...]) -> None:
        self._columns = columns
        self._items: dict[str, dict[str, object]] = {}
        self._order: list[str] = []
        self._headings: dict[str, dict[str, object]] = {}
        self._move_calls: list[tuple[str, str, int]] = []

    def __getitem__(self, key: str):
        if key == "columns":
            return self._columns
        raise KeyError(key)

    def get_children(self, parent: str) -> tuple[str, ...]:
        assert parent == ""
        return tuple(self._order)

    def item(self, iid: str, option: str | None = None, **kwargs):
        if option is None and not kwargs:
            return self._items[iid]
        if option == "text":
            return self._items[iid]["text"]
        if option == "values":
            return self._items[iid]["values"]
        raise NotImplementedError

    def set(self, iid: str, col: str, value: str | None = None) -> str:
        raise NotImplementedError

    def move(self, iid: str, parent: str, index: int) -> None:
        self._move_calls.append((iid, parent, index))
        self._order.remove(iid)
        self._order.insert(index, iid)

    def heading(self, col: str, **kwargs) -> None:
        entry = self._headings.setdefault(col, {})
        entry.update(kwargs)

    def add(self, iid: str, *, text: str = "", values: tuple[str, ...] = ()) -> None:
        self._items[iid] = {"text": text, "values": values}
        self._order.append(iid)


def test_create_scrollable_treeview_sets_yscrollcommand() -> None:
    try:
        root = tk.Tk()
        root.withdraw()
    except tk.TclError as exc:
        pytest.skip(f"Tk not available: {exc}")
    try:
        tree, frame = create_scrollable_treeview(root, columns=("a",), show="headings", height=4)
        assert tree.cget("yscrollcommand")
        assert isinstance(frame, tk.Frame)
    finally:
        root.destroy()


def test_create_scrollable_listbox_sets_yscrollcommand() -> None:
    try:
        root = tk.Tk()
        root.withdraw()
    except tk.TclError as exc:
        pytest.skip(f"Tk not available: {exc}")
    try:
        listbox, frame = create_scrollable_listbox(root, height=4)
        assert listbox.cget("yscrollcommand")
        assert isinstance(frame, tk.Frame)
    finally:
        root.destroy()


def test_treeview_sorter_sorts_strings_with_move() -> None:
    tree = _FakeTree(("name",))
    tree.add("b", values=("beta",))
    tree.add("a", values=("alpha",))
    tree.add("c", values=("charlie",))
    sorter = TreeviewSorter(tree)  # type: ignore[arg-type]
    sorter.attach({"name": "Name"})
    sorter._sort_by("name")
    assert tree._order == ["a", "b", "c"]
    assert len(tree._move_calls) >= 2
    sorter._sort_by("name")
    assert tree._order == ["c", "b", "a"]


def test_treeview_sorter_sorts_numeric_columns() -> None:
    tree = _FakeTree(("count",))
    tree.add("1", values=("10",))
    tree.add("2", values=("2",))
    tree.add("3", values=("100",))
    sorter = TreeviewSorter(tree, numeric_columns=("count",))  # type: ignore[arg-type]
    sorter.attach({"count": "Count"})
    sorter._sort_by("count")
    assert tree._order == ["2", "1", "3"]


def test_treeview_sorter_resort_preserves_active_column() -> None:
    tree = _FakeTree(("name",))
    tree.add("x", values=("z",))
    tree.add("y", values=("a",))
    sorter = TreeviewSorter(tree)  # type: ignore[arg-type]
    sorter.attach({"name": "Name"})
    sorter._sort_by("name")
    tree.add("z", values=("m",))
    sorter.resort()
    assert tree._order == ["y", "z", "x"]


def test_test_app_tree_files_has_scrollcommand(tmp_path) -> None:
    from interfaces.tk import test_app

    try:
        app = test_app.TestApp(project_root=tmp_path)
    except tk.TclError as exc:
        pytest.skip(f"Tk not available: {exc}")
    try:
        assert app.tree_files.cget("yscrollcommand")
    finally:
        app.destroy()


def test_rule_editor_tree_rulesets_has_scrollcommand(tmp_path, monkeypatch) -> None:
    from rule_editor_main import RuleEditorWindow

    monkeypatch.setenv("ARE_HOME", str(tmp_path))
    try:
        editor = RuleEditorWindow(project_root=tmp_path)
    except tk.TclError as exc:
        pytest.skip(f"Tk not available: {exc}")
    try:
        assert editor.tree_rulesets.cget("yscrollcommand")
    finally:
        editor.destroy()
