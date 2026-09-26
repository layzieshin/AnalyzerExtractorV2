from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Sequence
from tkinter import ttk

from interfaces.tk.view_models import format_timestamp
from interfaces.tk.widgets.common import Card, EmptyState, SectionHeader, create_scrollable_tree
from src.application.api import ValidationQueueItem


class ValidationView(ttk.Frame):
    """Primary work queue for human first validation of assay runs."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_refresh: Callable[[], None],
        on_save: Callable[[], None],
        on_open_pdf: Callable[[], None],
    ) -> None:
        super().__init__(master, style="Content.TFrame")
        self._on_refresh = on_refresh
        self._on_save = on_save
        self._on_open_pdf = on_open_pdf
        self._items: dict[str, ValidationQueueItem] = {}
        self._default_operator_initials = ""
        self._build()

    def _build(self) -> None:
        card = Card(self)
        card.pack(fill="both", expand=True)
        body = card.body
        SectionHeader(
            body,
            "Validierung",
            subtitle="Offene Assay-Messungen fachlich pruefen und mit Initialen freigeben.",
            action_text="Aktualisieren",
            on_action=self._on_refresh,
        ).pack(fill="x", pady=(0, 8))

        list_frame, self._tree = create_scrollable_tree(
            body,
            ("report", "assay", "lot", "device", "time", "status"),
            ("Bericht", "Assay", "Charge/Lot", "Geraet", "Zeit", "Status"),
            height=7,
        )
        list_frame.pack(fill="both", expand=True, pady=(0, 8))
        self._tree.bind("<<TreeviewSelect>>", self._on_select)
        self._empty = EmptyState(body, "Keine offenen Validierungen.")

        self._lbl_context = ttk.Label(body, text="Keine Messung ausgewaehlt.", style="Muted.TLabel", wraplength=760)
        self._lbl_context.pack(anchor="w", pady=(0, 6))
        fields_frame, self._fields = create_scrollable_tree(
            body,
            ("field", "value"),
            ("Feld", "Wert"),
            height=6,
        )
        fields_frame.pack(fill="both", expand=True, pady=(0, 8))

        form = ttk.Frame(body, style="CardInner.TFrame")
        form.pack(fill="x")
        ttk.Label(form, text="Initialen").grid(row=0, column=0, sticky="w")
        self._var_initials = tk.StringVar()
        ttk.Entry(form, textvariable=self._var_initials, width=16).grid(row=0, column=1, sticky="w", padx=(8, 16))
        ttk.Label(form, text="Kommentar (optional)").grid(row=0, column=2, sticky="w")
        self._var_comment = tk.StringVar()
        ttk.Entry(form, textvariable=self._var_comment).grid(row=0, column=3, sticky="ew", padx=(8, 0))
        form.columnconfigure(3, weight=1)
        actions = ttk.Frame(body, style="CardInner.TFrame")
        actions.pack(fill="x", pady=(8, 0))
        self._btn_save = ttk.Button(actions, text="Validierung speichern", style="Primary.TButton", command=self._on_save)
        self._btn_save.pack(side="left")
        self._btn_open_pdf = ttk.Button(actions, text="PDF oeffnen", command=self._on_open_pdf)
        self._btn_open_pdf.pack(side="left", padx=(8, 0))
        self._btn_save.configure(state="disabled")
        self._btn_open_pdf.configure(state="disabled")

    def set_default_operator_initials(self, initials: str) -> None:
        self._default_operator_initials = str(initials or "").strip()
        if not str(self._var_initials.get() or "").strip():
            self._var_initials.set(self._default_operator_initials)

    def selected_item(self) -> ValidationQueueItem | None:
        selection = self._tree.selection()
        return self._items.get(str(selection[0])) if selection else None

    def validation_initials(self) -> str:
        return self._var_initials.get()

    def validation_comment(self) -> str:
        return self._var_comment.get()

    def clear_comment(self) -> None:
        self._var_comment.set("")

    def render_cases(self, items: Sequence[ValidationQueueItem]) -> None:
        selected = self.selected_item()
        previous_run_id = selected.run_id if selected is not None else None
        for row in self._tree.get_children():
            self._tree.delete(row)
        self._items = {str(item.run_id): item for item in items}
        if not items:
            self._empty.pack(anchor="w", pady=(0, 8))
            self._render_item(None)
            return
        self._empty.pack_forget()
        for item in items:
            status = "Historie unklar" if item.validation_ambiguous else "Offen"
            self._tree.insert(
                "",
                "end",
                iid=str(item.run_id),
                values=(item.file_name or "-", item.assay_key or "-", item.lot_id or "-", item.device_id or "-", format_timestamp(item.created_at), status),
            )
        target = str(previous_run_id) if previous_run_id is not None and self._tree.exists(str(previous_run_id)) else str(items[0].run_id)
        self._tree.selection_set(target)
        self._tree.focus(target)
        self._render_item(self._items[target])

    def _on_select(self, _event: object) -> None:
        self._render_item(self.selected_item())

    def _render_item(self, item: ValidationQueueItem | None) -> None:
        for row in self._fields.get_children():
            self._fields.delete(row)
        if item is None:
            self._lbl_context.configure(text="Keine Messung ausgewaehlt.")
            self._btn_save.configure(state="disabled")
            self._btn_open_pdf.configure(state="disabled")
            return
        status = "Validierungshistorie ist nicht eindeutig; bitte in Ergebnisse klaeren." if item.validation_ambiguous else "Bereit zur Erstvalidierung."
        self._lbl_context.configure(
            text=(
                f"Bericht: {item.file_name or '-'} | Assay: {item.assay_key or '-'} | "
                f"Charge/Lot: {item.lot_id or '-'} | Geraet: {item.device_id or '-'} | {status}"
            )
        )
        for field in item.fields:
            self._fields.insert("", "end", values=(field.field_key, field.value if field.value != "" else "(leer)"))
        self._btn_save.configure(state="disabled" if item.validation_ambiguous else "normal")
        self._btn_open_pdf.configure(state="normal")
