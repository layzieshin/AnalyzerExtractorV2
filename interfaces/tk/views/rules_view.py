from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Sequence
from tkinter import ttk

from interfaces.tk.view_models import integrity_summary
from interfaces.tk.widgets.common import EmptyState
from rule_editor.editor_workspace import RuleEditorWorkspace
from src.application.api import RulesetInventoryItem


class RulesView(ttk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        *,
        on_open_rule_editor: Callable[[], None],
        on_refresh: Callable[[], None],
        on_validate: Callable[[], None],
        on_focus: Callable[[bool], None] | None = None,
        on_return_identity: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(master, style="Content.TFrame")
        self._on_open_rule_editor = on_open_rule_editor
        self._on_refresh = on_refresh
        self._on_validate = on_validate
        self._on_focus = on_focus
        self._on_return_identity = on_return_identity
        self._identity_context = None
        self._editor: RuleEditorWorkspace | None = None
        self._inventory_items = ()
        self._build()

    def _build(self) -> None:
        self._empty = EmptyState(self, "Regelwerke werden geladen …")
        self._empty.pack(anchor="w", padx=12, pady=12)
        self._identity_bar = ttk.Frame(self, style="Content.TFrame", padding=(8, 0, 8, 5))
        ttk.Button(self._identity_bar, text="‹ Zurück zu Änderungen", command=lambda: self._on_return_identity() if self._on_return_identity else None).pack(side="left")

    def bind_editor(self, rules: object, project_root) -> None:
        if self._editor is not None:
            if self._editor._rules is not rules:
                raise RuntimeError("Regelverwaltung ist bereits an einen anderen Controller gebunden.")
            return
        self._empty.pack_forget()
        self._editor = RuleEditorWorkspace(self, project_root, rules=rules, initial_inventory=self._inventory_items, embedded=True, on_focus=self._on_focus)
        self._editor.pack(fill="both", expand=True)
        self._tree = self._editor.tree_rulesets

    def render_inventory(self, items: Sequence[RulesetInventoryItem]) -> None:
        self._inventory_items = tuple(items)
        if self._editor is not None:
            self._editor.render_inventory(self._inventory_items)

    def prepare_leave(self, *, closing: bool = False) -> bool:
        return self._editor is None or self._editor.prepare_leave(closing=closing)

    def invalidate_context(self) -> None:
        self._identity_context = None
        self._identity_bar.pack_forget()
        if self._editor is not None:
            self._editor._identity_case_context = None
            self._editor._identity_activation_callback = None
        if self._on_focus:
            self._on_focus(False)
        if self._editor is not None:
            self._editor.invalidate_context()

    def open_identity_draft(self, payload, *, context, on_activated) -> bool:
        editor = self._editor
        if editor is None or not editor.prepare_leave():
            return False
        editor.invalidate_context()
        editor.current_draft_path = payload["draft_path"]
        editor.var_draft_path.set(payload["draft_path"])
        editor._apply_data_to_widgets(payload["draft_data"])
        editor.render_inventory(payload.get("inventory", ()))
        editor._show_page("workspace")
        editor.var_pdf.set(payload.get("test_pdf", ""))
        self._identity_context = context
        editor._identity_case_context = {**context, "draft_path": payload["draft_path"]}
        editor._identity_activation_callback = on_activated
        self._identity_bar.pack(fill="x", before=editor)
        if payload.get("test_pdf"):
            editor.on_load_text()
        if payload.get("message"):
            editor._set_hint(payload["message"])
        return True

    def render_integrity_report(self, report: dict[str, object]) -> None:
        total, failed = integrity_summary(report)
        text = f"Integrität: {failed} von {total} Prüfungen fehlgeschlagen." if failed else f"Integrität: alle {total} Prüfungen bestanden."
        if self._editor is not None:
            self._editor._set_hint(text)
