"""ManageMixin: Regelset-Verwaltungskachel (Liste, Bearbeiten, Loeschen, Wizard-Start)."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, simpledialog

from src.rulesuite.api import adopt_candidate_fields, create_draft, delete_ruleset, list_rulesets

from .wizard import NewRulesetWizard


class ManageMixin:
    def _refresh_ruleset_overview(self) -> None:
        if self.tree_rulesets is None:
            return
        for row in self.tree_rulesets.get_children():
            self.tree_rulesets.delete(row)
        try:
            rows = list_rulesets(self.var_root.get().strip())
        except Exception as e:
            self._set_hint(f"Regelset-Liste konnte nicht geladen werden: {e}")
            return
        for row in rows:
            if row.get("error"):
                status = f"FEHLER: {row['error']}"
            elif row.get("valid"):
                status = "OK"
            else:
                status = "UNGUELTIG"
            self.tree_rulesets.insert(
                "",
                tk.END,
                values=(
                    row.get("assay_key", ""),
                    row.get("assay_name", ""),
                    row.get("ruleset_file", ""),
                    row.get("field_count", 0),
                    status,
                ),
            )

    def _selected_ruleset_key(self) -> str | None:
        if self.tree_rulesets is None:
            return None
        sel = self.tree_rulesets.selection()
        if not sel:
            return None
        return str(self.tree_rulesets.item(sel[0], "values")[0]).strip()

    def _selected_ruleset_row(self) -> dict[str, object] | None:
        key = self._selected_ruleset_key()
        if not key:
            return None
        try:
            for row in list_rulesets(self.var_root.get().strip()):
                if str(row.get("assay_key", "")).strip() == key:
                    return row
        except Exception:
            return None
        return None

    def on_adopt_fields_from_ruleset(self) -> None:
        if not self.current_draft_path:
            self._set_hint("Bitte zuerst einen Draft laden.")
            return
        source_row = self._selected_ruleset_row()
        if source_row is None:
            self._set_hint("Bitte zuerst ein Quell-Regelwerk in der Verwaltungsliste auswaehlen.")
            return

        source_key = str(source_row.get("assay_key", "")).strip()
        source_name = str(source_row.get("assay_name", "")).strip() or source_key
        candidate_source = {"source_assay_key": source_key}
        try:
            result = adopt_candidate_fields(
                self.var_root.get().strip(),
                self.current_draft_path,
                candidate_source,
            )
        except Exception as exc:
            messagebox.showerror("Felder uebernehmen", str(exc))
            return

        self.on_load_draft_into_editor()
        summary = (
            f"Felder aus Regelwerk uebernommen.\n"
            f"Quelle: {source_key} / {source_name}\n"
            f"Ziel: {result.get('draft_path', self.current_draft_path)}\n"
            f"uebernommen: {len(result.get('adopted', []))}\n"
            f"uebersprungen (vorhanden): {len(result.get('skipped_existing', []))}\n"
            f"fehlend: {len(result.get('missing', []))}"
        )
        self._log(summary.replace("\n", " | "))
        self._set_hint(
            f"Felder uebernommen: {len(result.get('adopted', []))}; "
            f"uebersprungen: {len(result.get('skipped_existing', []))}."
        )
        messagebox.showinfo("Felder uebernehmen", summary)

    def on_open_wizard(self) -> None:
        NewRulesetWizard(
            self,
            project_root=self.var_root.get().strip(),
            assay_display_to_key=dict(self.assay_display_to_key),
            on_open_in_editor=self._wizard_open_draft,
            on_activate_requested=self._wizard_activate_draft,
        )

    def _wizard_open_draft(self, draft_path: str) -> None:
        self.var_draft_path.set(draft_path)
        self.on_load_draft_into_editor()
        self._refresh_ruleset_overview()
        self._set_hint("Wizard abgeschlossen - Draft im Editor geladen.")

    def _wizard_activate_draft(self, draft_path: str) -> None:
        self.var_draft_path.set(draft_path)
        self.on_load_draft_into_editor()
        self.on_activate()
        self._refresh_ruleset_overview()

    def on_manage_edit_selected(self) -> None:
        key = self._selected_ruleset_key()
        if not key:
            self._set_hint("Bitte zuerst ein Regelset in der Verwaltungsliste auswaehlen.")
            return
        try:
            path = create_draft(self.var_root.get().strip(), key)
        except Exception as e:
            messagebox.showerror("Fehler", str(e))
            return
        self.var_draft_path.set(path)
        self.on_load_draft_into_editor()
        self._set_hint(f"Regelset {key} als Draft geladen - Aenderungen wirken erst nach Aktivierung.")

    def on_manage_delete_selected(self) -> None:
        key = self._selected_ruleset_key()
        if not key:
            self._set_hint("Bitte zuerst ein Regelset in der Verwaltungsliste auswaehlen.")
            return

        if not messagebox.askyesno(
            "Regelset loeschen",
            (
                f"Regelset {key} wirklich loeschen?\n\n"
                "Der Eintrag wird aus index.json entfernt und die Datei in den "
                "Papierkorb (rules/trash/) verschoben."
            ),
        ):
            return
        typed = simpledialog.askstring(
            "Loeschen bestaetigen",
            f"Zur Bestaetigung den Assay-Key exakt eintippen:\n{key}",
            parent=self,
        )
        if typed is None:
            return
        if typed.strip() != key:
            self._set_hint("Loeschen abgebrochen: Eingabe stimmt nicht mit dem Assay-Key ueberein.")
            return

        try:
            result = delete_ruleset(self.var_root.get().strip(), key)
        except Exception as e:
            messagebox.showerror("Fehler", str(e))
            return
        trash = result.get("trash_path") or "(Datei war nicht vorhanden)"
        self._log(f"Regelset geloescht: {key} -> {trash}")
        self._set_hint(f"Regelset {key} geloescht (wiederherstellbar unter rules/trash/).")
        self._reload_assays()
        self._refresh_ruleset_overview()
