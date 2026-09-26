from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Sequence
from tkinter import ttk

from interfaces.tk.view_models import integrity_summary, rules_inventory_item_id
from interfaces.tk.widgets.common import Card, EmptyState, SectionHeader, create_scrollable_tree
from src.application.api import RulesetInventoryItem


class RulesView(ttk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        *,
        on_open_rule_editor: Callable[[], None],
        on_refresh: Callable[[], None],
        on_validate: Callable[[], None],
    ) -> None:
        super().__init__(master, style="Content.TFrame")
        self._on_open_rule_editor = on_open_rule_editor
        self._on_refresh = on_refresh
        self._on_validate = on_validate
        self._build()

    def _build(self) -> None:
        card = Card(self)
        card.pack(fill="both", expand=True)
        body = card.body
        SectionHeader(
            body,
            "Regelwerke",
            subtitle="Inventar und Integritätsprüfung. Authoring erfolgt im Rule Editor.",
        ).pack(fill="x", pady=(0, 8))

        actions = ttk.Frame(body, style="CardInner.TFrame")
        actions.pack(fill="x", pady=(0, 8))
        ttk.Button(actions, text="Rule Editor öffnen", style="Primary.TButton", command=self._on_open_rule_editor).pack(
            side="left"
        )
        ttk.Button(actions, text="Aktualisieren", command=self._on_refresh).pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="Integrität prüfen", command=self._on_validate).pack(side="left", padx=(8, 0))

        self._lbl_integrity = ttk.Label(body, text="", style="Muted.TLabel")
        self._lbl_integrity.pack(anchor="w", pady=(0, 8))

        columns = ("assay", "type", "fields", "valid", "error")
        tree_frame, self._tree = create_scrollable_tree(
            body,
            columns,
            ("Assay", "Typ", "Felder", "Gültig", "Hinweis"),
            height=14,
        )
        tree_frame.pack(fill="both", expand=True)
        self._empty = EmptyState(body, "Kein Regelwerk-Inventar geladen.")

    def render_inventory(self, items: Sequence[RulesetInventoryItem]) -> None:
        for row in self._tree.get_children():
            self._tree.delete(row)
        if not items:
            self._empty.pack(anchor="w", pady=(8, 0))
            return
        self._empty.pack_forget()
        for index, item in enumerate(items):
            iid = rules_inventory_item_id(item, index)
            self._tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    item.assay_name or item.assay_key,
                    item.display_type,
                    str(item.field_count),
                    "Ja" if item.valid else "Nein",
                    item.error or "",
                ),
            )

    def render_integrity_report(self, report: dict[str, object]) -> None:
        total, failed = integrity_summary(report)
        if failed:
            self._lbl_integrity.configure(text=f"Integrität: {failed} von {total} Prüfungen fehlgeschlagen.")
        else:
            self._lbl_integrity.configure(text=f"Integrität: alle {total} Prüfungen bestanden.")
