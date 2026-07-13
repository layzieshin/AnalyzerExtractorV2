"""ManageMixin: Inventar, Lifecycle und Regelset-Verwaltung (AP-16C/16D)."""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog

from src.rulesuite.api import (
    adopt_candidate_fields,
    clone_ruleset_to_draft,
    deactivate_ruleset,
    delete_inventory_item,
    draft_path_for_assay,
    list_rulesuite_inventory,
    open_inactive_as_draft,
)

from .clone_dialog import CloneRulesetDialog
from .wizard import NewRulesetWizard

_INVENTORY_FILTER_TO_KIND = {
    "Alle": "all",
    "Aktiv": "active",
    "Drafts": "draft",
    "Inaktiv": "inactive",
}


class ManageMixin:
    def _inventory_filter_kind(self) -> str:
        label = self.var_inventory_filter.get().strip()
        return _INVENTORY_FILTER_TO_KIND.get(label, "all")

    def _inventory_iid(self, row: dict[str, object]) -> str:
        return f"{row.get('kind', '')}|{row.get('path', '')}"

    def _refresh_ruleset_overview(self) -> None:
        if self.tree_rulesets is None:
            return
        for row_id in self.tree_rulesets.get_children():
            self.tree_rulesets.delete(row_id)
        self._inventory_by_iid = {}
        try:
            rows = list_rulesuite_inventory(self.var_root.get().strip(), kind=self._inventory_filter_kind())
        except Exception as exc:
            self._set_hint(f"Inventar konnte nicht geladen werden: {exc}")
            return
        for row in rows:
            if row.get("error"):
                status = f"FEHLER: {row['error']}"
            elif row.get("valid"):
                status = "OK"
            else:
                status = "UNGUELTIG"
            iid = self._inventory_iid(row)
            self._inventory_by_iid[iid] = dict(row)
            file_label = str(row.get("ruleset_file", "") or Path(str(row.get("path", ""))).name)
            self.tree_rulesets.insert(
                "",
                tk.END,
                iid=iid,
                values=(
                    row.get("display_type", ""),
                    row.get("assay_key", ""),
                    row.get("assay_name", ""),
                    file_label,
                    row.get("field_count", 0),
                    status,
                ),
            )

    def _selected_inventory_row(self) -> dict[str, object] | None:
        if self.tree_rulesets is None:
            return None
        selection = self.tree_rulesets.selection()
        if not selection:
            return None
        return self._inventory_by_iid.get(str(selection[0]))

    def _inventory_rows_by_kind(self, kind: str) -> list[dict[str, object]]:
        try:
            return list_rulesuite_inventory(self.var_root.get().strip(), kind=kind)
        except Exception:
            return []

    def _on_inventory_filter_changed(self, _event: object = None) -> None:
        self._refresh_ruleset_overview()

    def _inventory_select_row_at(self, event: object) -> str | None:
        if self.tree_rulesets is None:
            return None
        row_id = self.tree_rulesets.identify_row(event.y)  # type: ignore[attr-defined]
        if row_id:
            self.tree_rulesets.selection_set(row_id)
            self.tree_rulesets.focus(row_id)
        return row_id

    def _show_inventory_context_menu(self, event: object) -> None:
        row_id = self._inventory_select_row_at(event)
        if not row_id:
            return
        row = self._inventory_by_iid.get(str(row_id))
        if row is None:
            return
        menu = tk.Menu(self, tearoff=0)
        kind = row.get("kind")
        if kind == "active":
            menu.add_command(label="Inaktivieren...", command=self.on_manage_deactivate_selected)
            menu.add_command(label="Als Basis fuer Draft verwenden...", command=self.on_open_clone_ruleset_dialog)
        elif kind == "draft":
            menu.add_command(label="Draft oeffnen", command=self.on_manage_edit_selected)
            menu.add_command(label="Loeschen...", command=self.on_manage_delete_selected)
        elif kind == "inactive":
            menu.add_command(label="Als Draft oeffnen", command=self.on_manage_edit_selected)
            menu.add_command(label="Loeschen...", command=self.on_manage_delete_selected)
        try:
            menu.tk_popup(event.x_root, event.y_root)  # type: ignore[attr-defined]
        finally:
            menu.grab_release()

    def on_open_clone_ruleset_dialog(
        self,
        *,
        initial_source_key: str = "",
        initial_target_draft_path: str = "",
    ) -> None:
        project_root = self.var_root.get().strip()
        active_rows = self._inventory_rows_by_kind("active")
        draft_rows = self._inventory_rows_by_kind("draft")
        if not active_rows:
            self._set_hint("Kein aktives Regelwerk fuer Clone-Basis vorhanden.")
            return

        selected = self._selected_inventory_row()
        if not initial_source_key and selected and selected.get("kind") == "active":
            initial_source_key = str(selected.get("assay_key", ""))
        if not initial_target_draft_path and selected and selected.get("kind") == "draft":
            initial_target_draft_path = str(selected.get("path", ""))

        initial_target_key = self.var_new_assay_key.get().strip()
        initial_target_name = self.var_new_assay_name.get().strip()
        if initial_target_draft_path:
            for row in draft_rows:
                if str(row.get("path", "")).strip() == initial_target_draft_path.strip():
                    initial_target_key = str(row.get("assay_key", "")).strip()
                    initial_target_name = str(row.get("assay_name", "")).strip()
                    break

        CloneRulesetDialog(
            self,
            project_root=project_root,
            active_rows=active_rows,
            draft_rows=draft_rows,
            initial_source_key=initial_source_key,
            initial_target_key=initial_target_key,
            initial_target_name=initial_target_name,
            initial_target_draft_path=initial_target_draft_path,
            on_completed=self._on_clone_completed,
        )

    def _on_clone_completed(self, result: dict[str, object]) -> None:
        draft_path = str(result.get("draft_path", ""))
        status = str(result.get("status", ""))
        self.var_draft_path.set(draft_path)
        self.on_load_draft_into_editor()
        self._reload_assays()
        self._refresh_ruleset_overview()
        self._log(f"Draft geklont ({status}): {draft_path}")
        self._set_hint(f"Draft geklont ({status}).")

    def on_adopt_fields_from_ruleset(self) -> None:
        if not self.current_draft_path:
            self._set_hint("Bitte zuerst einen Draft laden.")
            return
        selected = self._selected_inventory_row()
        if selected is None or selected.get("kind") != "active":
            self._set_hint("Bitte zuerst ein aktives Regelwerk im Inventar auswaehlen.")
            return

        source_key = str(selected.get("assay_key", "")).strip()
        source_name = str(selected.get("assay_name", "")).strip() or source_key
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
        self._reload_assays()
        self._refresh_ruleset_overview()
        self._set_hint("Wizard abgeschlossen - Draft im Editor geladen.")

    def _wizard_activate_draft(self, draft_path: str) -> None:
        self.var_draft_path.set(draft_path)
        self.on_load_draft_into_editor()
        self.on_activate()
        self._reload_assays()
        self._refresh_ruleset_overview()

    def on_manage_edit_selected(self) -> None:
        row = self._selected_inventory_row()
        if row is None:
            self._set_hint("Bitte zuerst einen Inventar-Eintrag auswaehlen.")
            return

        kind = row.get("kind")
        if kind == "draft":
            self.var_draft_path.set(str(row.get("path", "")))
            self.on_load_draft_into_editor()
            self._set_hint("Draft geladen.")
            return

        if kind == "inactive":
            inactive_path = str(row.get("path", ""))
            try:
                result = open_inactive_as_draft(self.var_root.get().strip(), inactive_path)
            except Exception as exc:
                messagebox.showerror("Inaktiv oeffnen", str(exc))
                return
            draft_path = str(result.get("draft_path", ""))
            if result.get("status") == "exists":
                open_existing = messagebox.askyesno(
                    "Draft vorhanden",
                    (
                        f"Fuer dieses inaktive Regelwerk existiert bereits ein Draft:\n{draft_path}\n\n"
                        "Vorhandenen Draft oeffnen?\n"
                        "(Nein = Abbruch ohne Ueberschreiben)"
                    ),
                )
                if not open_existing:
                    self._set_hint("Abgebrochen: vorhandener Draft wurde nicht ueberschrieben.")
                    return
            self.var_draft_path.set(draft_path)
            self.on_load_draft_into_editor()
            self._log(
                f"Inaktiv als Draft geoeffnet ({result.get('status')}): {draft_path} "
                f"(Quelle: {inactive_path})"
            )
            self._set_hint("Inaktives Regelwerk als Draft geladen.")
            self._refresh_ruleset_overview()
            return

        project_root = self.var_root.get().strip()
        assay_key = str(row.get("assay_key", "")).strip()
        assay_name = str(row.get("assay_name", "")).strip() or assay_key
        target_draft = draft_path_for_assay(project_root, assay_key)
        if Path(target_draft).exists():
            open_existing = messagebox.askyesno(
                "Draft vorhanden",
                (
                    f"Fuer {assay_key} existiert bereits ein Draft:\n{target_draft}\n\n"
                    "Vorhandenen Draft oeffnen?\n"
                    "(Nein = Abbruch ohne Ueberschreiben)"
                ),
            )
            if not open_existing:
                self._set_hint("Abgebrochen: vorhandener Draft wurde nicht ueberschrieben.")
                return
            self.var_draft_path.set(target_draft)
            self.on_load_draft_into_editor()
            return

        try:
            result = clone_ruleset_to_draft(
                project_root,
                assay_key,
                assay_key,
                assay_name,
                overwrite=False,
                include_fields=True,
            )
        except Exception as exc:
            messagebox.showerror("Fehler", str(exc))
            return
        self.var_draft_path.set(str(result["draft_path"]))
        self.on_load_draft_into_editor()
        self._reload_assays()
        self._refresh_ruleset_overview()
        self._set_hint(f"Regelset {assay_key} als neuer Draft geladen.")

    def on_manage_deactivate_selected(self) -> None:
        row = self._selected_inventory_row()
        if row is None:
            self._set_hint("Bitte zuerst einen Inventar-Eintrag auswaehlen.")
            return
        if row.get("kind") != "active":
            self._set_hint("Inaktivieren ist nur fuer aktive Regelwerke verfuegbar.")
            return

        key = str(row.get("assay_key", "")).strip()
        if not messagebox.askyesno(
            "Regelwerk inaktivieren",
            (
                f"Regelwerk {key} wirklich inaktivieren?\n\n"
                "Der Eintrag wird aus der produktiven Erkennung entfernt (index.json). "
                "Die Datei bleibt unter rules/inactive/ erhalten."
            ),
        ):
            return
        typed = simpledialog.askstring(
            "Inaktivieren bestaetigen",
            f"Zur Bestaetigung den Assay-Key exakt eintippen:\n{key}",
            parent=self,
        )
        if typed is None:
            return
        if typed.strip() != key:
            self._set_hint("Inaktivieren abgebrochen: Eingabe stimmt nicht mit dem Assay-Key ueberein.")
            return

        try:
            result = deactivate_ruleset(self.var_root.get().strip(), key)
        except Exception as exc:
            messagebox.showerror("Inaktivieren", str(exc))
            return
        inactive = result.get("inactive_path") or "(Datei war nicht vorhanden)"
        self._log(f"Regelwerk inaktiviert: {key} -> {inactive}")
        self._set_hint(f"Regelwerk {key} inaktiviert (unter rules/inactive/).")
        self._reload_assays()
        self._refresh_ruleset_overview()

    def on_manage_delete_selected(self) -> None:
        row = self._selected_inventory_row()
        if row is None:
            self._set_hint("Bitte zuerst einen Inventar-Eintrag auswaehlen.")
            return

        kind = str(row.get("kind", ""))
        if kind == "active":
            self._set_hint("Aktive Regelwerke bitte zuerst inaktivieren.")
            messagebox.showinfo("Loeschen", "Aktive Regelwerke bitte zuerst inaktivieren.")
            return
        if kind not in ("draft", "inactive"):
            self._set_hint("Loeschen ist nur fuer Drafts und inaktive Regelwerke verfuegbar.")
            return

        path = str(row.get("path", ""))
        if kind == "draft":
            if not messagebox.askyesno("Draft loeschen", f"Draft wirklich nach rules/trash/ verschieben?\n\n{path}"):
                return
        else:
            label = str(row.get("assay_key", "")).strip() or Path(path).name
            if not messagebox.askyesno(
                "Inaktives Regelwerk loeschen",
                f"Inaktives Regelwerk wirklich nach rules/trash/ verschieben?\n\n{label}\n{path}",
            ):
                return

        try:
            result = delete_inventory_item(self.var_root.get().strip(), kind, path)
        except Exception as exc:
            messagebox.showerror("Loeschen", str(exc))
            return
        trash = result.get("trash_path") or "(unbekannt)"
        self._log(f"Inventar geloescht ({kind}): {path} -> {trash}")
        self._set_hint(f"Eintrag nach rules/trash/ verschoben: {trash}")
        self._refresh_ruleset_overview()
