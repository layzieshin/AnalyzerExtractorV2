from __future__ import annotations

import rule_editor.meta_actions as meta_actions
from rule_editor.meta_actions import MetaMixin


class _MetaActions(MetaMixin):
    def __init__(self) -> None:
        self.current_draft_path = "I:/proj/rules/drafts/test.draft.json"
        self.column_mapping_data: dict[str, str] = {}
        self.hints: list[str] = []
        self.logs: list[str] = []
        self.dirty = False
        self.undo_pushed = False

    def _set_hint(self, text: str) -> None:
        self.hints.append(text)

    def _log(self, text: str) -> None:
        self.logs.append(text)

    def _push_undo_snapshot(self) -> None:
        self.undo_pushed = True

    def _reload_column_mapping_from_draft(self) -> None:
        self.column_mapping_data = {"alpha": "alpha", "beta": "beta"}
        self.cols_refreshed = True

    def _refresh_cols_tree(self) -> None:
        self.cols_refreshed = True


def test_on_sync_column_mapping_from_fields_calls_api_and_updates_ui(monkeypatch) -> None:
    editor = _MetaActions()
    calls: list[str] = []

    def _fake_sync(draft_path: str) -> str:
        calls.append(draft_path)
        return draft_path

    monkeypatch.setattr(meta_actions, "sync_column_mapping_from_fields", _fake_sync)

    editor.on_sync_column_mapping_from_fields()

    assert calls == [editor.current_draft_path]
    assert editor.undo_pushed is True
    assert editor.column_mapping_data == {"alpha": "alpha", "beta": "beta"}
    assert editor.hints[-1] == "Fehlende Spaltenzuordnungen aus Feldern ergänzt."
    assert editor.logs[-1] == "Fehlende Spaltenzuordnungen aus Feldern ergänzt."
    assert editor.dirty is False
