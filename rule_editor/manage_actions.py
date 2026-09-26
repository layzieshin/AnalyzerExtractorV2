"""ManageMixin: Inventar, Lifecycle und Regelset-Verwaltung (AP-16C/16D)."""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog

from .clone_dialog import CloneRulesetDialog
from .wizard import NewRulesetWizard

_INVENTORY_KINDS = ("active", "draft", "inactive", "history", "trash")


def _inventory_row(item: object) -> dict[str, object]:
    return {
        "kind": str(getattr(item, "kind", "") or ""),
        "display_type": str(getattr(item, "display_type", "") or ""),
        "assay_key": str(getattr(item, "assay_key", "") or ""),
        "assay_name": str(getattr(item, "assay_name", "") or ""),
        "path": str(getattr(item, "path", "") or ""),
        "ruleset_file": str(getattr(item, "ruleset_file", "") or ""),
        "field_count": int(getattr(item, "field_count", 0) or 0),
        "valid": bool(getattr(item, "valid", False)),
        "error": getattr(item, "error", None),
        "modified_at": str(getattr(item, "modified_at", "") or ""),
        "sha256": str(getattr(item, "sha256", "") or ""),
        "read_only": bool(getattr(item, "read_only", False)),
    }


class ManageMixin:
    def _selected_inventory_kinds(self) -> set[str]:
        selected: set[str] = set()
        variables = getattr(self, "inventory_filter_vars", {})
        for kind in _INVENTORY_KINDS:
            variable = variables.get(kind)
            if variable is not None and bool(variable.get()):
                selected.add(kind)
        return selected

    def _select_all_inventory_filters(self) -> None:
        variables = getattr(self, "inventory_filter_vars", {})
        for kind in _INVENTORY_KINDS:
            variable = variables.get(kind)
            if variable is not None:
                variable.set(True)
        self._refresh_ruleset_overview()

    def _inventory_iid(self, row: dict[str, object]) -> str:
        return f"{row.get('kind', '')}|{row.get('path', '')}"

    def _refresh_ruleset_overview(self) -> None:
        if self.tree_rulesets is None:
            return
        for row_id in self.tree_rulesets.get_children():
            self.tree_rulesets.delete(row_id)
        self._inventory_by_iid = {}
        try:
            rows = [_inventory_row(item) for item in self._rules.list_inventory(kind="all")]
        except Exception as exc:
            self._set_hint(f"Inventar konnte nicht geladen werden: {exc}")
            return
        selected_kinds = self._selected_inventory_kinds()
        for row in rows:
            if row.get("kind") not in selected_kinds:
                continue
            if row.get("read_only") and row.get("error"):
                status = f"NUR LESEN · FEHLER: {row['error']}"
            elif row.get("read_only") and row.get("valid"):
                status = "NUR LESEN"
            elif row.get("read_only"):
                status = "NUR LESEN · UNGUELTIG"
            elif row.get("error"):
                status = f"FEHLER: {row['error']}"
            elif row.get("valid"):
                status = "OK"
            else:
                status = "UNGUELTIG"
            iid = self._inventory_iid(row)
            self._inventory_by_iid[iid] = dict(row)
            self.tree_rulesets.insert(
                "",
                tk.END,
                iid=iid,
                values=(
                    row.get("display_type", ""),
                    row.get("assay_key", ""),
                    row.get("assay_name", ""),
                    row.get("field_count", 0),
                    row.get("modified_at", ""),
                    status,
                ),
            )
        self._tree_rulesets_sorter.resort()
        self._sync_inventory_primary_button()

    def _selected_inventory_row(self) -> dict[str, object] | None:
        if self.tree_rulesets is None:
            return None
        selection = self.tree_rulesets.selection()
        if not selection:
            return None
        return self._inventory_by_iid.get(str(selection[0]))

    def _inventory_rows_by_kind(self, kind: str) -> list[dict[str, object]]:
        try:
            return [_inventory_row(item) for item in self._rules.list_inventory(kind=kind)]
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

    def _inventory_context_actions(self, row: dict[str, object]) -> list[tuple[str, object]]:
        kind = row.get("kind")
        if kind == "active":
            return [
                ("Als Entwurf bearbeiten", self.on_manage_edit_selected),
                ("Regel deaktivieren …", self.on_manage_deactivate_selected),
                ("Als neue Regel duplizieren …", self.on_open_clone_ruleset_dialog),
                ("Details anzeigen", self.on_show_inventory_details),
            ]
        if kind == "draft":
            return [
                ("Entwurf weiterbearbeiten", self.on_manage_edit_selected),
                ("Entwurf in Papierkorb verschieben …", self.on_manage_delete_selected),
                ("Endgültig löschen (nur nie aktiviert) …", self.on_delete_never_active_selected),
                ("Details anzeigen", self.on_show_inventory_details),
            ]
        if kind == "inactive":
            return [
                ("Als Entwurf wiederherstellen …", self.on_manage_edit_selected),
                ("In Papierkorb verschieben …", self.on_manage_delete_selected),
                ("Details anzeigen", self.on_show_inventory_details),
            ]
        if kind == "history":
            return [
                ("Als Entwurf wiederherstellen …", self.on_manage_edit_selected),
                ("Details anzeigen", self.on_show_inventory_details),
            ]
        if kind == "trash":
            return [("Details anzeigen", self.on_show_inventory_details)]
        return [("Details anzeigen", self.on_show_inventory_details)]

    def _populate_inventory_menu(self, menu: tk.Menu, row: dict[str, object]) -> None:
        for label, command in self._inventory_context_actions(row):
            menu.add_command(label=label, command=command)

    def _sync_inventory_primary_button(self, _event: object = None) -> None:
        button = getattr(self, "btn_inventory_primary", None)
        if button is None:
            return
        row = self._selected_inventory_row()
        if not row:
            button.configure(text="Aktion für Auswahl")
            return
        actions = self._inventory_context_actions(row)
        button.configure(text=str(actions[0][0]) if actions else "Details anzeigen")

    def on_inventory_primary_action(self) -> None:
        row = self._selected_inventory_row()
        if row is None:
            self._set_hint("Bitte zuerst einen Inventar-Eintrag auswählen.")
            return
        actions = self._inventory_context_actions(row)
        if not actions:
            return
        actions[0][1]()

    def on_inventory_more_actions(self) -> None:
        row = self._selected_inventory_row()
        if row is None:
            self._set_hint("Bitte zuerst einen Inventar-Eintrag auswählen.")
            return
        menu = tk.Menu(self, tearoff=0)
        self._populate_inventory_menu(menu, row)
        button = getattr(self, "btn_inventory_more", None)
        if button is not None:
            x = button.winfo_rootx()
            y = button.winfo_rooty() + button.winfo_height()
        else:
            x, y = 0, 0
        try:
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def _show_inventory_context_menu(self, event: object) -> None:
        row_id = self._inventory_select_row_at(event)
        if not row_id:
            return
        row = self._inventory_by_iid.get(str(row_id))
        if row is None:
            return
        menu = tk.Menu(self, tearoff=0)
        self._populate_inventory_menu(menu, row)
        try:
            menu.tk_popup(event.x_root, event.y_root)  # type: ignore[attr-defined]
        finally:
            menu.grab_release()

    def on_show_inventory_details(self) -> None:
        row = self._selected_inventory_row()
        if row is None:
            self._set_hint("Bitte zuerst einen Inventar-Eintrag auswählen.")
            return
        error = row.get("error") or "-"
        text = "\n".join(
            [
                f"Typ: {row.get('display_type', '')} ({row.get('kind', '')})",
                f"Assay-Schlüssel: {row.get('assay_key', '')}",
                f"Assay-Name: {row.get('assay_name', '')}",
                f"Datei: {row.get('ruleset_file', '')}",
                f"Pfad: {row.get('path', '')}",
                f"SHA-256: {row.get('sha256', '')}",
                f"Feldzahl: {row.get('field_count', 0)}",
                f"Änderungszeit: {row.get('modified_at', '')}",
                f"Gültig: {row.get('valid', False)}",
                f"Nur lesen: {row.get('read_only', False)}",
                f"Status/Fehler: {error}",
            ]
        )
        messagebox.showinfo("Details", text, parent=self)

    def on_open_clone_ruleset_dialog(self, *, initial_source_key: str = "") -> None:
        active_rows = self._inventory_rows_by_kind("active")
        if not active_rows:
            self._set_hint("Kein aktives Regelwerk zum Duplizieren vorhanden.")
            return

        selected = self._selected_inventory_row()
        if not initial_source_key and selected and selected.get("kind") == "active":
            initial_source_key = str(selected.get("assay_key", ""))

        CloneRulesetDialog(
            self,
            rules=self._rules,
            active_rows=active_rows,
            initial_source_key=initial_source_key,
            on_completed=self._on_clone_completed,
        )

    def _on_clone_completed(self, result: dict[str, object]) -> None:
        draft_path = str(result.get("draft_path", ""))
        status = str(result.get("status", ""))
        opened = self._open_draft_in_editor(draft_path)
        self._refresh_ruleset_overview()
        if opened == "abort":
            self._set_hint("Wechsel abgebrochen. Der geklonte Entwurf wurde nicht in den Editor geladen.")
            return
        if opened not in {"loaded", "focus"}:
            return
        self._reload_assays()
        self._log(f"Entwurf dupliziert ({status}): {draft_path}")
        self._set_hint(f"Entwurf dupliziert ({status}).")

    def on_adopt_fields_from_ruleset(self) -> None:
        if getattr(self, "_field_mutation_guard", False) or getattr(self, "_dialog_guard", False):
            return
        guard = getattr(self, "_resolve_dirty_field_form", None)
        if callable(guard) and not guard():
            return
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
            result = self._rules.adopt_candidate_fields(
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

    def on_open_wizard(self, *, intent: str = "new") -> None:
        if not self._prepare_dirty_editor_for_wizard():
            return
        NewRulesetWizard(
            self,
            rules=self._rules,
            on_open_in_editor=self._wizard_open_draft,
            on_activate_requested=self._wizard_activate_draft,
            start_intent="neutral" if intent == "neutral" else "new",
            on_session_closed=self._sync_editor_after_wizard,
        )

    def _prepare_dirty_editor_for_wizard(self) -> bool:
        guard = getattr(self, "_resolve_dirty_field_form", None)
        if callable(guard) and not guard():
            return False
        current = str(getattr(self, "current_draft_path", "") or "").strip()
        if not current or not bool(getattr(self, "_dirty", False)):
            return True
        choice = messagebox.askyesnocancel(
            "Ungespeicherte Änderungen",
            (
                "Der geladene Entwurf enthält ungespeicherte Änderungen.\n\n"
                "Ja = speichern und die geführte Prüfung öffnen\n"
                "Nein = Änderungen verwerfen und den Entwurf neu aus der Datei laden\n"
                "Abbrechen = die geführte Prüfung nicht öffnen"
            ),
            parent=self._dialog_parent(),
        )
        if choice is None:
            return False
        if choice is False:
            reloaded = self.on_load_draft_into_editor(current)
            return reloaded is not False
        try:
            self._save_meta_to_draft(push_undo=True)
        except Exception as exc:
            messagebox.showerror("Speichern", str(exc), parent=self._dialog_parent())
            return False
        return True

    def _sync_editor_after_wizard(self, draft_path: str | None) -> None:
        current = str(getattr(self, "current_draft_path", "") or "").strip()
        target = str(draft_path or "").strip()
        if not current or not target or not self._same_draft_path(current, target):
            return
        self.on_load_draft_into_editor(current)

    def _wizard_open_draft(self, draft_path: str) -> None:
        current = str(getattr(self, "current_draft_path", "") or "").strip()
        if current and self._same_draft_path(current, draft_path):
            if self.on_load_draft_into_editor(draft_path) is False:
                return
            self._focus_loaded_workspace()
            self._reload_assays()
            self._refresh_ruleset_overview()
            self._set_hint("Geführte Prüfung abgeschlossen. Der geladene Entwurf wurde neu eingelesen.")
            return
        if self._open_draft_in_editor(draft_path) not in {"loaded", "focus"}:
            return
        self._reload_assays()
        self._refresh_ruleset_overview()
        self._set_hint("Geführte Prüfung abgeschlossen. Entwurf im Editor geladen.")

    def _wizard_activate_draft(self, draft_path: str) -> None:
        current = str(getattr(self, "current_draft_path", "") or "").strip()
        if current and self._same_draft_path(current, draft_path):
            if self.on_load_draft_into_editor(draft_path) is False:
                return
        else:
            opened = self._open_draft_in_editor(draft_path)
            if opened in {"abort", "error"}:
                return
        self.on_activate()
        self._reload_assays()
        self._refresh_ruleset_overview()

    def _on_editor_close(self) -> None:
        if getattr(self, "_field_mutation_guard", False) or getattr(self, "_dialog_guard", False):
            return
        guard = getattr(self, "_resolve_dirty_field_form", None)
        if callable(guard) and not guard():
            return
        if self.current_draft_path and bool(getattr(self, "_dirty", False)):
            choice = messagebox.askyesnocancel(
                "Ungespeicherte Änderungen",
                (
                    "Der geladene Entwurf enthält ungespeicherte Änderungen.\n\n"
                    "Ja = speichern und schliessen\n"
                    "Nein = Änderungen verwerfen und schliessen\n"
                    "Abbrechen = Fenster offen lassen"
                ),
                parent=self._dialog_parent(),
            )
            if choice is None:
                return
            if choice is True:
                try:
                    self._save_meta_to_draft(push_undo=True)
                except Exception as exc:
                    messagebox.showerror("Speichern", str(exc), parent=self._dialog_parent())
                    return
        self.destroy()

    def _dialog_parent(self) -> tk.Misc | None:
        if hasattr(self, "winfo_toplevel"):
            return self
        return None

    def _predicted_draft_path(self, assay_key: str) -> str:
        key = str(assay_key or "").strip()
        if not key:
            return ""
        predictor = getattr(getattr(self, "_rules", None), "draft_path_for_assay", None)
        if not callable(predictor):
            return ""
        try:
            return str(predictor(key))
        except Exception:
            return ""

    def _confirm_draft_switch(self, target_path: str) -> str:
        """Decide whether the editor may leave the loaded draft. No inventory backend calls."""
        current = str(getattr(self, "current_draft_path", "") or "").strip()
        if target_path and current and self._same_draft_path(current, target_path):
            return "focus"
        guard = getattr(self, "_resolve_dirty_field_form", None)
        if callable(guard) and not guard():
            return "abort"
        if not self._resolve_pending_meta_changes(
            save_label="speichern und wechseln",
            discard_label="Änderungen verwerfen und wechseln",
            cancel_label="im aktuellen Entwurf bleiben",
        ):
            return "abort"
        return "proceed"

    def _resolve_pending_meta_changes(self, *, save_label: str, discard_label: str, cancel_label: str) -> bool:
        """Save, discard, or abort unsaved meta edits. True lets the caller continue."""
        current = str(getattr(self, "current_draft_path", "") or "").strip()
        if not current or not bool(getattr(self, "_dirty", False)):
            return True
        if getattr(self, "_dialog_guard", False) or getattr(self, "_field_mutation_guard", False):
            return False
        self._dialog_guard = True
        try:
            choice = messagebox.askyesnocancel(
                "Ungespeicherte Änderungen",
                (
                    "Der geladene Entwurf enthält ungespeicherte Änderungen.\n\n"
                    f"Ja = {save_label}\n"
                    f"Nein = {discard_label}\n"
                    f"Abbrechen = {cancel_label}"
                ),
                parent=self._dialog_parent(),
            )
            if choice is None:
                return False
            if choice is False:
                return True
            try:
                self._save_meta_to_draft(push_undo=True)
            except Exception as exc:
                messagebox.showerror("Speichern", str(exc), parent=self._dialog_parent())
                return False
            return True
        finally:
            self._dialog_guard = False

    def _focus_loaded_workspace(self) -> None:
        show_page = getattr(self, "_show_page", None)
        if callable(show_page):
            show_page("workspace")

    def _open_draft_in_editor(self, draft_path: str) -> str:
        decision = self._confirm_draft_switch(draft_path)
        if decision == "abort":
            return "abort"
        if decision == "focus":
            self._focus_loaded_workspace()
            return "focus"
        if not self._load_target_draft(draft_path):
            return "error"
        return "loaded"

    def _load_target_draft(self, draft_path: str) -> bool:
        variable = getattr(self, "var_draft_path", None)
        previous_backing = variable.get() if variable is not None and hasattr(variable, "get") else ""
        previous_current = getattr(self, "current_draft_path", None)
        result = self.on_load_draft_into_editor(draft_path)
        if result is False:
            if variable is not None and hasattr(variable, "set"):
                variable.set(previous_backing)
            self.current_draft_path = previous_current
            return False
        return True

    def _load_restored_draft(self, draft_path: str, *, status: str, hint: str, log_line: str) -> None:
        if status == "exists":
            open_existing = messagebox.askyesno(
                "Entwurf vorhanden",
                (
                    f"Es existiert bereits ein Entwurf:\n{draft_path}\n\n"
                    "Vorhandenen Entwurf öffnen?\n"
                    "(Nein = Abbruch ohne Überschreiben)"
                ),
                parent=self._dialog_parent(),
            )
            if not open_existing:
                self._set_hint("Abgebrochen: vorhandener Entwurf wurde nicht überschrieben.")
                return
        current = str(getattr(self, "current_draft_path", "") or "")
        if current and self._same_draft_path(current, draft_path):
            self._focus_loaded_workspace()
            self._set_hint(hint)
            return
        if not self._load_target_draft(draft_path):
            return
        log = getattr(self, "_log", None)
        if callable(log):
            log(log_line)
        self._set_hint(hint)

    def on_manage_edit_selected(self) -> None:
        row = self._selected_inventory_row()
        if row is None:
            self._set_hint("Bitte zuerst einen Inventar-Eintrag auswaehlen.")
            return

        kind = row.get("kind")
        if kind == "draft":
            if self._open_draft_in_editor(str(row.get("path", ""))) in {"loaded", "focus"}:
                self._set_hint("Draft geladen.")
            return

        if kind == "trash":
            self._set_hint("Trash-Eintraege sind nur lesbar.")
            return

        if kind in {"history", "inactive"}:
            source_path = str(row.get("path", ""))
            predicted = self._predicted_draft_path(str(row.get("assay_key", "")))
            decision = self._confirm_draft_switch(predicted)
            if decision == "abort":
                return
            if decision == "focus":
                self._focus_loaded_workspace()
                self._set_hint("Der Entwurf ist bereits geladen.")
                return
            try:
                if kind == "history":
                    result = self._rules.open_history_as_draft(source_path)
                else:
                    result = self._rules.open_inactive_as_draft(source_path)
            except Exception as exc:
                title = "Historie oeffnen" if kind == "history" else "Inaktiv oeffnen"
                messagebox.showerror(title, str(exc), parent=self._dialog_parent())
                return
            draft_path = str(result.get("draft_path", ""))
            if kind == "history":
                self._load_restored_draft(
                    draft_path,
                    status=str(result.get("status", "")),
                    hint="Historie als Draft geladen.",
                    log_line=(
                        f"Historie als Draft geoeffnet ({result.get('status')}): {draft_path} "
                        f"(Quelle: {source_path})"
                    ),
                )
            else:
                self._load_restored_draft(
                    draft_path,
                    status=str(result.get("status", "")),
                    hint="Inaktives Regelwerk als Draft geladen.",
                    log_line=(
                        f"Inaktiv als Draft geoeffnet ({result.get('status')}): {draft_path} "
                        f"(Quelle: {source_path})"
                    ),
                )
            self._refresh_ruleset_overview()
            return

        assay_key = str(row.get("assay_key", "")).strip()
        if not assay_key:
            self._set_hint("Das aktive Regelwerk hat keinen Assay-Schlüssel.")
            return
        decision = self._confirm_draft_switch(self._predicted_draft_path(assay_key))
        if decision == "abort":
            return
        if decision == "focus":
            self._focus_loaded_workspace()
            self._set_hint(f"Regelset {assay_key} ist bereits geladen.")
            return
        try:
            result = self._rules.open_active_as_draft(assay_key)
        except Exception as exc:
            messagebox.showerror("Bearbeiten", str(exc), parent=self._dialog_parent())
            return
        draft_path = str(result.get("draft_path", ""))
        self._load_restored_draft(
            draft_path,
            status=str(result.get("status", "")),
            hint=f"Regelset {assay_key} als Entwurf geladen.",
            log_line=f"Aktiv als Entwurf geoeffnet ({result.get('status')}): {draft_path}",
        )
        self._refresh_ruleset_overview()

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
            f"Zur Bestätigung den Assay-Schlüssel exakt eintippen:\n{key}",
            parent=self,
        )
        if typed is None:
            return
        if typed.strip() != key:
            self._set_hint("Deaktivieren abgebrochen: Eingabe stimmt nicht mit dem Assay-Schlüssel überein.")
            return

        try:
            result = self._rules.deactivate_ruleset(key)
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
            if not messagebox.askyesno(
                "Entwurf verwerfen",
                (
                    "Entwurf in den Papierkorb verschieben?\n"
                    "Das ist keine endgültige Löschung; der Eintrag bleibt unter rules/trash/ erhalten.\n\n"
                    f"{path}"
                ),
            ):
                return
        else:
            label = str(row.get("assay_key", "")).strip() or Path(path).name
            if not messagebox.askyesno(
                "Inaktives Regelwerk loeschen",
                f"Inaktives Regelwerk wirklich nach rules/trash/ verschieben?\n\n{label}\n{path}",
            ):
                return

        try:
            result = self._rules.delete_inventory_item(kind, path)
        except Exception as exc:
            messagebox.showerror("Loeschen", str(exc))
            return
        trash = result.get("trash_path") or "(unbekannt)"
        self._log(f"Inventar geloescht ({kind}): {path} -> {trash}")
        self._refresh_ruleset_overview()
        if kind == "draft" and self._same_draft_path(str(getattr(self, "current_draft_path", "") or ""), path):
            self._clear_loaded_draft()
        self._set_hint(f"Eintrag nach rules/trash/ verschoben: {trash}")

    def _same_draft_path(self, left: str, right: str) -> bool:
        a = str(left or "").strip()
        b = str(right or "").strip()
        if not a or not b:
            return False
        if a == b:
            return True
        try:
            return Path(a).resolve() == Path(b).resolve()
        except OSError:
            return False

    def _clear_editor_var(self, name: str, value: object) -> None:
        variable = getattr(self, name, None)
        if variable is not None and hasattr(variable, "set"):
            variable.set(value)

    def _clear_text_widget(self, widget: object) -> None:
        if widget is None or not hasattr(widget, "delete"):
            return
        previous = None
        try:
            if hasattr(widget, "cget"):
                previous = str(widget.cget("state"))
            if previous == "disabled" and hasattr(widget, "configure"):
                widget.configure(state="normal")
            widget.delete("1.0", "end")
        except tk.TclError:
            return
        finally:
            if previous and hasattr(widget, "configure"):
                try:
                    widget.configure(state=previous)
                except tk.TclError:
                    pass

    def _clear_preview_widgets(self) -> None:
        writer = getattr(self, "_set_field_preview_text", None)
        if callable(writer):
            try:
                writer("")
                return
            except tk.TclError:
                pass
        self._clear_text_widget(getattr(self, "txt_field_preview", None))
        self._clear_text_widget(getattr(self, "txt_marking_regex_preview", None))

    def _clear_regex_residue(self) -> None:
        clearer = getattr(self, "_clear_regex_results", None)
        if callable(clearer) and getattr(self, "tree_regex_results", None) is not None:
            try:
                clearer()
            except tk.TclError:
                data = getattr(self, "_regex_result_data", None)
                if isinstance(data, dict):
                    data.clear()
        else:
            data = getattr(self, "_regex_result_data", None)
            if isinstance(data, dict):
                data.clear()
        if hasattr(self, "_regex_result_counter"):
            self._regex_result_counter = 0

    def _clear_marking_residue(self) -> None:
        clearer = getattr(self, "_clear_field_markings", None)
        if callable(clearer) and getattr(self, "txt_block", None) is not None:
            try:
                clearer()
                return
            except tk.TclError:
                pass
        if hasattr(self, "_field_marking_tags"):
            self._field_marking_tags = set()
        if hasattr(self, "_visible_marking_keys"):
            self._visible_marking_keys = set()
        if hasattr(self, "_field_marking_data"):
            self._field_marking_data = {}
        if hasattr(self, "_active_marking_key"):
            self._active_marking_key = None
        legend = getattr(self, "tree_marking_legend", None)
        if legend is not None and hasattr(legend, "get_children") and hasattr(legend, "delete"):
            try:
                for row in legend.get_children():
                    legend.delete(row)
            except tk.TclError:
                pass

    def _clear_loaded_draft(self) -> None:
        previous = getattr(self, "_suspend_dirty_tracking", False)
        self._suspend_dirty_tracking = True
        try:
            self.current_draft_path = None
            self._clear_editor_var("var_draft_path", "")
            self._dirty = False
            for stack_name in ("_undo_stack", "_redo_stack"):
                stack = getattr(self, stack_name, None)
                if stack is not None:
                    stack.clear()
            for name in (
                "var_new_assay_key",
                "var_new_assay_name",
                "var_lot_regex",
                "var_dedupe_fields",
                "var_field_key",
                "var_field_regex",
                "var_search_after",
                "var_search_line",
                "var_col_key",
                "var_col_name",
                "var_field_guidance",
                "var_field_excel_column",
            ):
                self._clear_editor_var(name, "")
            self._clear_editor_var("var_excel_filename", "{assay_name}.xlsx")
            self._clear_editor_var("var_sheet_template", "{lot_id}")
            self._clear_editor_var("var_search_mode", "none")
            self._clear_editor_var("var_regex_group", "1")
            self._clear_editor_var("var_marking_status", "Kein Assay-Text geladen.")
            self._clear_editor_var("var_field_required", False)
            self._clear_editor_var("var_field_dedupe", False)
            if hasattr(self, "_selected_field_key"):
                self._selected_field_key = None
            if hasattr(self, "_field_form_dirty"):
                self._field_form_dirty = False
            if hasattr(self, "_field_form_is_new"):
                self._field_form_is_new = False
            if hasattr(self, "fields_data"):
                self.fields_data = []
            if hasattr(self, "column_mapping_data"):
                self.column_mapping_data = {}
            if hasattr(self, "assay_block_text"):
                self.assay_block_text = ""
            self._clear_regex_residue()
            self._clear_marking_residue()
            for method_name in ("_refresh_fields_tree", "_refresh_cols_tree", "_clear_validation_list"):
                method = getattr(self, method_name, None)
                if not callable(method):
                    continue
                try:
                    method()
                except (tk.TclError, AttributeError):
                    pass
            reset_form = getattr(self, "_reset_field_form", None)
            if (
                callable(reset_form)
                and getattr(self, "tree_fields", None) is not None
                and getattr(self, "txt_block", None) is not None
            ):
                try:
                    reset_form()
                except (tk.TclError, AttributeError):
                    pass
            self._clear_text_widget(getattr(self, "txt_block", None))
            self._clear_preview_widgets()
        finally:
            self._suspend_dirty_tracking = previous
        show_page = getattr(self, "_show_page", None)
        if callable(show_page):
            show_page("inventory")

    def on_delete_never_active_selected(self) -> None:
        row = self._selected_inventory_row()
        if row is None:
            self._set_hint("Bitte zuerst einen Inventar-Eintrag auswählen.")
            return
        if row.get("kind") != "draft":
            self._set_hint("Endgültig löschen ist nur für Entwürfe verfügbar, die nie aktiviert wurden.")
            return

        path = str(row.get("path", ""))
        key = str(row.get("assay_key", "")).strip()
        confirmed = messagebox.askyesno(
            "Endgültig löschen",
            (
                "Dieser Entwurf wird unwiderruflich gelöscht.\n"
                "Es entsteht kein Papierkorb-Eintrag und keine Wiederherstellung.\n"
                "Nur ein Entwurf ohne Aktivierungs- oder Lebenszyklusspur kann so entfernt werden.\n\n"
                f"Assay-Schlüssel: {key}\n{path}"
            ),
            parent=self,
        )
        if not confirmed:
            self._set_hint("Endgültiges Löschen abgebrochen.")
            return
        typed = simpledialog.askstring(
            "Endgültig löschen bestätigen",
            f"Zur Bestätigung den Assay-Schlüssel exakt eintippen:\n{key}",
            parent=self,
        )
        if typed is None:
            self._set_hint("Endgültiges Löschen abgebrochen.")
            return
        if typed.strip() != key:
            self._set_hint("Endgültiges Löschen abgebrochen: Eingabe stimmt nicht mit dem Assay-Schlüssel überein.")
            return

        try:
            self._rules.delete_never_active_ruleset(path)
        except Exception as exc:
            messagebox.showerror("Endgültig löschen", str(exc), parent=self)
            self._set_hint("Endgültiges Löschen abgelehnt. Der Entwurf bleibt erhalten.")
            return

        if self._same_draft_path(str(getattr(self, "current_draft_path", "") or ""), path):
            self._clear_loaded_draft()
        self._refresh_ruleset_overview()
        self._set_hint(f"Entwurf {key} endgültig gelöscht.")
