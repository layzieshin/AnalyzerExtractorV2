from __future__ import annotations

from pathlib import Path

import rule_editor.draft_actions as draft_actions
from rule_editor.draft_actions import DraftMixin


class _Var:
    def __init__(self, value: str = "") -> None:
        self.value = value

    def get(self) -> str:
        return self.value

    def set(self, value: str) -> None:
        self.value = value


class _DraftActions(DraftMixin):
    def __init__(self) -> None:
        self.var_root = _Var("I:/proj")
        self.var_new_assay_key = _Var("(9000)")
        self.var_new_assay_name = _Var("Header Assay")
        self.var_draft_path = _Var("")
        self.logs: list[str] = []
        self.hints: list[str] = []
        self.loaded = False

    def _set_hint(self, text: str) -> None:
        self.hints.append(text)

    def _log(self, text: str) -> None:
        self.logs.append(text)

    def on_load_draft_into_editor(self) -> None:
        self.loaded = True


def test_on_create_blank_uses_template_header_contract(monkeypatch) -> None:
    draft = _DraftActions()
    calls: list[tuple[str, str, str]] = []

    def _fake_create_draft_from_template(project_root: str, assay_key: str, assay_name: str) -> str:
        calls.append((project_root, assay_key, assay_name))
        return str(Path(project_root) / "rules" / "drafts" / "(9000).draft.json")

    monkeypatch.setattr(draft_actions, "create_draft_from_template", _fake_create_draft_from_template)

    draft.on_create_blank()

    assert calls == [("I:/proj", "(9000)", "Header Assay")]
    assert draft.var_draft_path.get().endswith("(9000).draft.json")
    assert draft.loaded is True
    assert any("Header-Vertrag" in line for line in draft.logs)
    assert draft.hints[-1] == "Draft mit Header-Vertrag erstellt."
