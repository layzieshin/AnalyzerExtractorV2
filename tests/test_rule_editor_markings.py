from __future__ import annotations

from rule_editor.marking_actions import MarkingsMixin


class _Var:
    def __init__(self, value: str = "") -> None:
        self.value = value

    def get(self) -> str:
        return self.value

    def set(self, value: str) -> None:
        self.value = value


class _Text:
    def __init__(self) -> None:
        self.tags: dict[str, list[tuple[str, str]]] = {}
        self.seen: list[str] = []
        self.bound: set[str] = set()

    def tag_remove(self, tag: str, _start: str, _end: str) -> None:
        self.tags[tag] = []

    def tag_add(self, tag: str, start: str, end: str) -> None:
        self.tags.setdefault(tag, []).append((start, end))

    def tag_ranges(self, tag: str) -> tuple[str, ...]:
        ranges: list[str] = []
        for start, end in self.tags.get(tag, []):
            ranges.extend([start, end])
        return tuple(ranges)

    def tag_bind(self, tag: str, _event: str, _callback: object) -> None:
        self.bound.add(tag)

    def tag_unbind(self, tag: str, _event: str) -> None:
        self.bound.discard(tag)

    def see(self, index: str) -> None:
        self.seen.append(index)


class _Tree:
    def __init__(self) -> None:
        self.items: dict[str, dict[str, object]] = {}
        self._selection: tuple[str, ...] = ()
        self.focused: str | None = None
        self.seen: list[str] = []
        self._next = 0

    def insert(self, _parent: str, _where: str, *, text: str, values: tuple[str, str, str], tags: tuple[str, ...]) -> str:
        self._next += 1
        item = f"i{self._next}"
        self.items[item] = {"text": text, "values": values, "tags": tags}
        return item

    def get_children(self) -> list[str]:
        return list(self.items)

    def item(self, item: str, option: str | None = None, **kwargs: object) -> object:
        if "values" in kwargs:
            self.items[item]["values"] = kwargs["values"]
        if option is None:
            return self.items[item]
        return self.items[item][option]

    def selection(self) -> tuple[str, ...]:
        return self._selection

    def selection_set(self, item: str) -> None:
        self._selection = (item,)

    def focus(self, item: str) -> None:
        self.focused = item

    def see(self, item: str) -> None:
        self.seen.append(item)

    def tag_configure(self, _tag: str, **_kwargs: object) -> None:
        return None


class _DummyMarkings(MarkingsMixin):
    def __init__(self) -> None:
        self.txt_block = _Text()
        self.tree_marking_legend = _Tree()
        self.var_field_key = _Var("")
        self._field_marking_data = {
            "A": {"key": "A", "matched": True, "span": [2, 5], "value": "hit", "error": None},
            "B": {"key": "B", "matched": False, "span": None, "value": None, "error": None},
        }
        self._field_marking_tags = {"field::A", "field::B"}
        self._visible_marking_keys: set[str] = set()
        self._active_marking_key: str | None = None
        self.hints: list[str] = []
        self.tree_marking_legend.insert("", "end", text="A", values=("TREFFER", "AUS", "hit"), tags=())
        self.tree_marking_legend.insert("", "end", text="B", values=("KEIN TREFFER", "AUS", "-"), tags=())

    def _set_hint(self, text: str) -> None:
        self.hints.append(text)


def test_marking_visibility_shows_only_matched_fields() -> None:
    markings = _DummyMarkings()

    markings._set_all_markings_visible(True)

    assert markings._visible_marking_keys == {"A"}
    assert markings.txt_block.tags["field::A"] == [("1.0+2c", "1.0+5c")]
    assert markings.txt_block.tags["field::B"] == []
    values = [markings.tree_marking_legend.item(item, "values") for item in markings.tree_marking_legend.get_children()]
    assert values == [("TREFFER", "AN", "hit"), ("KEIN TREFFER", "AUS", "-")]


def test_marking_visibility_toggle_keeps_selection_context() -> None:
    markings = _DummyMarkings()
    first_item = markings.tree_marking_legend.get_children()[0]
    markings.tree_marking_legend.selection_set(first_item)
    markings._set_all_markings_visible(True)

    markings._toggle_selected_marking_visibility()

    assert markings._visible_marking_keys == set()
    assert markings.tree_marking_legend.selection() == (first_item,)
    values = markings.tree_marking_legend.item(first_item, "values")
    assert values == ("TREFFER", "AUS", "hit")


def test_hidden_active_marking_still_scrolls_with_emphasis() -> None:
    markings = _DummyMarkings()

    markings._emphasize_field_marking("A")

    assert markings._active_marking_key == "A"
    assert markings.txt_block.tags["field_emphasis"] == [("1.0+2c", "1.0+5c")]
    assert markings.txt_block.seen == ["1.0+2c"]
