"""FieldsMixin: Feld-CRUD, Feldformular und Feldliste."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, simpledialog

from .history_actions import _RECEIPT_ERROR, history_entry_from_receipt

SEARCH_MODE_LABELS = {
    "none": "Gesamter Assay-Text",
    "after": "Ab Textmarker",
    "line": "Ab Zeile",
}
SEARCH_LABEL_TO_MODE = {label: mode for mode, label in SEARCH_MODE_LABELS.items()}


class FieldsMixin:
    def _refresh_fields_tree(self, selected_key: str | None = None) -> None:
        previous = getattr(self, "_suppress_field_select", False)
        self._suppress_field_select = True
        try:
            for row in self.tree_fields.get_children():
                self.tree_fields.delete(row)
            selected_item = None
            for field in self.fields_data:
                key = str(field.get("key", ""))
                regex = str(field.get("regex", ""))
                search_label = self._render_search_from(field.get("search_from"))
                item = self.tree_fields.insert("", tk.END, values=(key, regex, search_label))
                if selected_key and key == selected_key:
                    selected_item = item
            if selected_item:
                self.tree_fields.selection_set(selected_item)
                self.tree_fields.focus(selected_item)
                self.tree_fields.see(selected_item)
        finally:
            self._suppress_field_select = previous

    def _render_search_from(self, search_from: object) -> str:
        if isinstance(search_from, dict) and "after" in search_from:
            return SEARCH_MODE_LABELS["after"]
        if isinstance(search_from, dict) and "line" in search_from:
            return SEARCH_MODE_LABELS["line"]
        return SEARCH_MODE_LABELS["none"]

    def on_field_selected(self, _event: object = None) -> None:
        if getattr(self, "_suppress_field_select", False) or getattr(self, "_field_selection_guard", False):
            return
        sel = self.tree_fields.selection()
        if not sel:
            return
        key = str(self.tree_fields.item(sel[0], "values")[0])
        self._select_field(key)

    def _select_field(self, key: str) -> bool:
        if getattr(self, "_field_selection_guard", False):
            return False
        if key == self._selected_field_key and not self._field_form_is_new:
            self._sync_field_chrome(key)
            return True
        self._field_selection_guard = True
        previous = self._selected_field_key
        try:
            if not self._resolve_dirty_field_form():
                self._restore_field_chrome(previous)
                return False
            if not self._load_field_form_for_key(key):
                self._restore_field_chrome(self._selected_field_key)
                return False
            self._selected_field_key = key
            self._field_form_is_new = False
            self._field_form_dirty = False
            self._update_field_commit_button()
            self._sync_field_chrome(key)
            return True
        finally:
            self._field_selection_guard = False

    def _sync_field_chrome(self, key: str) -> None:
        previous = getattr(self, "_suppress_field_select", False)
        self._suppress_field_select = True
        try:
            self._restore_tree_selection(key)
        finally:
            self._suppress_field_select = previous
        self._sync_marking_for_key(key)

    def _restore_field_chrome(self, key: str | None) -> None:
        previous = getattr(self, "_suppress_field_select", False)
        marking_guard = getattr(self, "_marking_sync_guard", False)
        self._suppress_field_select = True
        self._marking_sync_guard = True
        try:
            self._restore_tree_selection(key)
            self._restore_legend_selection(key)
        finally:
            self._suppress_field_select = previous
            self._marking_sync_guard = marking_guard

    def _restore_legend_selection(self, key: str | None) -> None:
        legend = getattr(self, "tree_marking_legend", None)
        if legend is None:
            return
        selection = legend.selection()
        target = None
        if key:
            target = next(
                (item for item in legend.get_children() if str(legend.item(item, "text")) == key),
                None,
            )
        if target is None:
            if selection:
                legend.selection_remove(selection)
            return
        if selection != (target,):
            legend.selection_set(target)
        legend.focus(target)
        legend.see(target)

    def _restore_tree_selection(self, key: str | None) -> None:
        previous = getattr(self, "_suppress_field_select", False)
        self._suppress_field_select = True
        try:
            selection = self.tree_fields.selection()
            target = None
            if key:
                target = next(
                    (
                        item
                        for item in self.tree_fields.get_children()
                        if str(self.tree_fields.item(item, "values")[0]) == key
                    ),
                    None,
                )
            if target is None:
                if selection:
                    self.tree_fields.selection_remove(selection)
                return
            # TreeviewSelect is delivered after this method returns. Re-selecting
            # the already active row therefore creates an endless event cycle.
            if selection != (target,):
                self.tree_fields.selection_set(target)
            self.tree_fields.focus(target)
            self.tree_fields.see(target)
        finally:
            self._suppress_field_select = previous

    def _sync_marking_for_key(self, key: str) -> None:
        if self._marking_sync_guard:
            return
        if key in self._field_marking_data:
            self._emphasize_field_marking(key)
        elif self._marking_panel_visible:
            self.txt_block.tag_remove("field_emphasis", "1.0", tk.END)
            self._active_marking_key = None
        self._update_field_guidance(key)

    def _update_field_guidance(self, key: str) -> None:
        """Fuehrung beim Ansehen/Bearbeiten: Status der Fundstelle im Beispiel-PDF."""
        if not key:
            self.var_field_guidance.set("")
            return
        if not self.assay_block_text.strip():
            self.var_field_guidance.set(
                "Kein Beispiel-PDF geladen. Im PDF-Testbericht den Text laden, um die Fundstelle zu prüfen."
            )
            return
        row = self._field_marking_data.get(key)
        if row is None:
            self.var_field_guidance.set(
                "Fundstelle noch nicht geprüft. Im PDF-Testbericht 'Markierungen aktualisieren' ausführen."
            )
            return
        error = str(row.get("error") or "").strip()
        if error:
            self.var_field_guidance.set(f"Regex-Fehler: {error}")
        elif row.get("matched"):
            self.var_field_guidance.set(f"Fundstelle vorhanden: {row.get('value')} (im PDF-Testbericht markiert).")
        else:
            self.var_field_guidance.set(
                "Keine Fundstelle im Beispiel-PDF. Bitte im PDF-Testbericht Text markieren "
                "und Regex/'Suche ab' uebernehmen."
            )

    def _load_field_form_for_key(self, key: str) -> bool:
        row = next((field for field in self.fields_data if str(field.get("key", "")) == key), None)
        if row is None:
            return False
        dedupe = self._persisted_dedupe_keys()
        column = self.column_mapping_data.get(key, key)
        self._field_form_loading = True
        previous = self._suspend_dirty_tracking
        self._suspend_dirty_tracking = True
        try:
            self.var_field_key.set(key)
            self.var_field_regex.set(str(row.get("regex", "")))
            self.var_field_required.set(bool(row.get("required", False)))
            self.var_field_excel_column.set(str(column))
            self.var_field_dedupe.set(key in dedupe)
            self._apply_search_from_value(row.get("search_from"))
            self._field_form_is_new = False
            self._field_form_dirty = False
        finally:
            self._suspend_dirty_tracking = previous
            self._field_form_loading = False
        self._sync_search_inputs()
        self._update_field_commit_button()
        return True

    def _apply_search_from_value(self, search_from: object) -> None:
        if isinstance(search_from, dict) and "after" in search_from:
            mode = "after"
            after = str(search_from.get("after", ""))
            line = ""
        elif isinstance(search_from, dict) and "line" in search_from:
            mode = "line"
            after = ""
            line = str(search_from.get("line", ""))
        else:
            mode = "none"
            after = ""
            line = ""
        self._set_search_mode(mode, after=after, line=line, mark_dirty=False)

    def _set_search_mode(
        self,
        mode: str,
        *,
        after: str | None = None,
        line: str | None = None,
        mark_dirty: bool = True,
    ) -> None:
        if mode not in SEARCH_MODE_LABELS:
            return
        self._search_mode_applying = True
        previous = self._suspend_dirty_tracking
        self._suspend_dirty_tracking = True
        try:
            self.var_search_mode.set(mode)
            self.var_search_mode_label.set(SEARCH_MODE_LABELS[mode])
            if after is not None:
                self.var_search_after.set(after)
            if line is not None:
                self.var_search_line.set(line)
            self._sync_search_inputs()
        finally:
            self._suspend_dirty_tracking = previous
            self._search_mode_applying = False
        if mark_dirty and not previous and not self._field_form_loading:
            self._field_form_dirty = True

    def _sync_search_inputs(self) -> None:
        mode = self.var_search_mode.get().strip()
        after_state = tk.NORMAL if mode == "after" else tk.DISABLED
        line_state = tk.NORMAL if mode == "line" else tk.DISABLED
        if getattr(self, "ent_search_after", None) is not None:
            self.ent_search_after.configure(state=after_state)
        if getattr(self, "ent_search_line", None) is not None:
            self.ent_search_line.configure(state=line_state)

    def on_search_mode_label_changed(self, *_args: object) -> None:
        if (
            self._field_form_loading
            or self._suspend_dirty_tracking
            or getattr(self, "_search_mode_applying", False)
        ):
            return
        label = self.var_search_mode_label.get()
        mode = SEARCH_LABEL_TO_MODE.get(label)
        if mode is None or mode == self.var_search_mode.get():
            self._sync_search_inputs()
            return
        self._set_search_mode(mode)

    def _reset_field_form(self) -> None:
        self._field_form_loading = True
        previous = self._suspend_dirty_tracking
        self._suspend_dirty_tracking = True
        try:
            self.var_field_key.set("")
            self.var_field_regex.set("")
            self.var_field_required.set(False)
            self.var_field_excel_column.set("")
            self.var_field_dedupe.set(False)
            self._apply_search_from_value(None)
            self.var_regex_group.set("1")
            self._selected_field_key = None
            self._field_form_is_new = False
            self._field_form_dirty = False
            self._restore_tree_selection(None)
            if getattr(self, "txt_block", None) is not None:
                self.txt_block.tag_remove("field_emphasis", "1.0", tk.END)
            self._active_marking_key = None
            self.var_field_guidance.set("")
        finally:
            self._suspend_dirty_tracking = previous
            self._field_form_loading = False
        self._sync_search_inputs()
        self._update_field_commit_button()
        self._set_hint("Feldformular zurückgesetzt.")

    def _discard_field_form_edits(self) -> None:
        if self._field_form_is_new:
            return_key = getattr(self, "_field_form_return_key", None)
            if return_key and self._load_field_form_for_key(return_key):
                self._selected_field_key = return_key
                self._restore_tree_selection(return_key)
                self._field_form_dirty = False
                self._update_field_commit_button()
                return
            self._reset_field_form()
            return
        key = self._selected_field_key
        if key and self._load_field_form_for_key(key):
            self._field_form_dirty = False
            self._restore_tree_selection(key)
            return
        self._reset_field_form()

    def on_cancel_field_edit(self) -> None:
        if getattr(self, "_field_mutation_guard", False) or getattr(self, "_dialog_guard", False):
            return
        if self._field_form_dirty:
            self._resolve_dirty_field_form()
            return
        self._discard_field_form_edits()
        self._set_hint("Feldformular auf den gespeicherten Stand zurueckgesetzt.")

    def _build_search_from(self) -> dict | None:
        mode = self.var_search_mode.get().strip()
        if mode == "after":
            return {"after": self.var_search_after.get().strip()}
        if mode == "line":
            line_raw = self.var_search_line.get().strip()
            if not line_raw:
                raise ValueError("search_from.line muss integer sein")
            return {"line": int(line_raw)}
        return None

    def _form_excel_column(self) -> str:
        column = self.var_field_excel_column.get().strip()
        if not column:
            raise ValueError("Excel-Spalte ist erforderlich")
        return column

    def _persisted_dedupe_keys(self) -> set[str]:
        raw = [item.strip() for item in self.var_dedupe_fields.get().split(",")]
        return {item for item in raw if item}

    def _reload_column_mapping_from_draft(self) -> None:
        if not self.current_draft_path:
            return
        data = self._rules.load_draft(self.current_draft_path)
        self._apply_persisted_mapping_and_dedupe(data)

    def _apply_persisted_mapping_and_dedupe(self, data: dict) -> None:
        excel_rules = data.get("excel_rules")
        if not isinstance(excel_rules, dict):
            excel_rules = {}
        col_map = excel_rules.get("column_mapping")
        extract_rules = data.get("extract_rules")
        if not isinstance(extract_rules, dict):
            extract_rules = {}
        dedupe = extract_rules.get("dedupe_fields", [])
        previous = self._suspend_dirty_tracking
        self._suspend_dirty_tracking = True
        try:
            self.column_mapping_data = dict(col_map) if isinstance(col_map, dict) else {}
            if isinstance(dedupe, list):
                self.var_dedupe_fields.set(",".join(str(item) for item in dedupe if str(item).strip()))
            else:
                self.var_dedupe_fields.set("")
        finally:
            self._suspend_dirty_tracking = previous
        refresher = getattr(self, "_refresh_cols_tree", None)
        if callable(refresher):
            refresher()

    def _sync_fields_from_draft(self, selected_key: str | None) -> None:
        data = self._rules.load_draft(self.current_draft_path)
        extract_rules = data.get("extract_rules", {})
        fields = extract_rules.get("fields", []) if isinstance(extract_rules, dict) else []
        self.fields_data = list(fields) if isinstance(fields, list) else []
        self._apply_persisted_mapping_and_dedupe(data)
        self._refresh_fields_tree(selected_key=selected_key)

    def _commit_undo_after_success(self, snapshot: dict | None) -> None:
        if snapshot is None:
            return
        self._undo_stack.append(snapshot)
        if len(self._undo_stack) > 50:
            self._undo_stack = self._undo_stack[-50:]
        self._redo_stack.clear()

    def _commit_receipt_undo(self, receipt: object) -> bool:
        entry = history_entry_from_receipt(receipt)
        if entry is None:
            messagebox.showerror("Fehler", _RECEIPT_ERROR)
            return False
        self._commit_undo_after_success(entry)
        return True

    def _report_reload_after_commit(self, exc: Exception) -> None:
        messagebox.showerror(
            "Hinweis",
            "Die Aenderung ist gespeichert, die Ansicht konnte aber nicht neu geladen werden.\n"
            f"{exc}",
        )

    def _resolve_dirty_field_form(self) -> bool:
        if getattr(self, "_dialog_guard", False) or getattr(self, "_field_mutation_guard", False):
            return False
        if not getattr(self, "_field_form_dirty", False):
            return True
        self._dialog_guard = True
        try:
            return self._resolve_dirty_field_form_dialog()
        finally:
            self._dialog_guard = False

    def _resolve_dirty_field_form_dialog(self) -> bool:
        choice = messagebox.askyesnocancel(
            "Feldformular",
            (
                "Das Feldformular enthaelt ungespeicherte Aenderungen.\n\n"
                "Ja = Aenderungen speichern und fortfahren\n"
                "Nein = Aenderungen verwerfen und fortfahren\n"
                "Abbrechen = hier bleiben"
            ),
            parent=self if hasattr(self, "winfo_toplevel") else None,
        )
        if choice is None:
            return False
        if choice is False:
            self._discard_field_form_edits()
            return True
        return self._persist_field_form()

    def _persist_field_form(self) -> bool:
        if self._field_form_is_new:
            return self._commit_new_field()
        if self._selected_field_key:
            return self._commit_replace_field()
        self._set_hint("Kein Feld ausgewaehlt.")
        return False

    def on_begin_new_field(self) -> None:
        if getattr(self, "_field_mutation_guard", False) or getattr(self, "_dialog_guard", False):
            return
        if not self.current_draft_path:
            self._set_hint("Bitte zuerst einen Entwurf laden.")
            return
        if not self._resolve_dirty_field_form():
            return
        self._field_form_loading = True
        previous = self._suspend_dirty_tracking
        self._suspend_dirty_tracking = True
        try:
            self.var_field_key.set("")
            self.var_field_regex.set("")
            self.var_field_required.set(False)
            self.var_field_excel_column.set("")
            self.var_field_dedupe.set(False)
            self._apply_search_from_value(None)
            self._field_form_return_key = self._selected_field_key
            self._selected_field_key = None
            self._field_form_is_new = True
            self._field_form_dirty = False
            self._restore_tree_selection(None)
            self.var_field_guidance.set("Neues Feld: noch nicht gespeichert.")
        finally:
            self._suspend_dirty_tracking = previous
            self._field_form_loading = False
        self._sync_search_inputs()
        self._update_field_commit_button()
        self._set_hint("Neu-Modus: Feld wird erst mit 'Neues Feld anlegen' geschrieben.")

    def on_commit_field_form(self) -> None:
        if not self._persist_field_form():
            return

    def on_add_field(self) -> bool:
        return self._commit_new_field()

    def on_apply_field(self) -> None:
        self.on_commit_field_form()

    def _commit_new_field(self) -> bool:
        if not self.current_draft_path:
            self._set_hint("Bitte zuerst einen Entwurf laden.")
            return False
        if not self._field_form_is_new:
            self._set_hint("Neues Feld nur im Neu-Modus anlegen.")
            return False
        key = self.var_field_key.get().strip()
        regex = self.var_field_regex.get().strip()
        if not key or not regex:
            self._set_hint("Feldschlüssel und Erkennungsregel sind erforderlich.")
            return False
        self._field_mutation_guard = True
        try:
            try:
                search_from = self._build_search_from()
                receipt = self._rules.add_field(
                    self.current_draft_path,
                    key,
                    regex,
                    required=False,
                    search_from=search_from,
                    excel_column=self._form_excel_column(),
                    dedupe_member=bool(self.var_field_dedupe.get()),
                    return_receipt=True,
                )
            except Exception as exc:
                messagebox.showerror("Fehler", str(exc))
                return False
            if not self._commit_receipt_undo(receipt):
                return False
            try:
                self._sync_fields_from_draft(key)
                self._selected_field_key = key
                self._field_form_is_new = False
                self._load_field_form_for_key(key)
            except Exception as exc:
                self._report_reload_after_commit(exc)
                return True
            self._set_hint(f"Feld angelegt: {key}")
            self._log(f"Feld angelegt: {key}")
            self._maybe_refresh_field_markings()
            return True
        finally:
            self._field_mutation_guard = False

    def _commit_replace_field(self) -> bool:
        if not self.current_draft_path:
            self._set_hint("Bitte zuerst einen Entwurf laden.")
            return False
        selected_key = self._selected_field_key
        if not selected_key or self._field_form_is_new:
            self._set_hint("Bitte ein bestehendes Feld markieren.")
            return False
        key = self.var_field_key.get().strip()
        regex = self.var_field_regex.get().strip()
        if not key or not regex:
            self._set_hint("Feldschlüssel und Erkennungsregel sind erforderlich.")
            return False
        self._field_mutation_guard = True
        try:
            try:
                search_from = self._build_search_from()
                receipt = self._rules.replace_field(
                    self.current_draft_path,
                    selected_key,
                    key=key,
                    regex=regex,
                    required=bool(self.var_field_required.get()),
                    search_from=search_from,
                    excel_column=self._form_excel_column(),
                    dedupe_member=bool(self.var_field_dedupe.get()),
                    return_receipt=True,
                )
            except Exception as exc:
                messagebox.showerror("Fehler", str(exc))
                return False
            if not self._commit_receipt_undo(receipt):
                return False
            try:
                self._sync_fields_from_draft(key)
                self._selected_field_key = key
                self._field_form_is_new = False
                self._load_field_form_for_key(key)
            except Exception as exc:
                self._report_reload_after_commit(exc)
                return True
            self._set_hint(f"Feld ersetzt: {selected_key} -> {key}")
            self._log(f"Feld ersetzt: {selected_key} -> {key}")
            self._maybe_refresh_field_markings()
            return True
        finally:
            self._field_mutation_guard = False

    def on_duplicate_field(self) -> None:
        if getattr(self, "_field_mutation_guard", False) or getattr(self, "_dialog_guard", False):
            return
        if not self.current_draft_path:
            self._set_hint("Bitte zuerst einen Entwurf laden.")
            return
        if not self._resolve_dirty_field_form():
            return
        source_key = self._selected_field_key
        if not source_key or self._field_form_is_new:
            self._set_hint("Bitte ein Feld zum Duplizieren auswählen.")
            return
        new_key = simpledialog.askstring("Feld duplizieren", f"Neuer Key für Kopie von '{source_key}':")
        if not new_key:
            return
        self._field_mutation_guard = True
        try:
            try:
                receipt = self._rules.duplicate_field(
                    self.current_draft_path,
                    source_key,
                    new_key,
                    return_receipt=True,
                )
            except Exception as exc:
                messagebox.showerror("Fehler", str(exc))
                return
            if not self._commit_receipt_undo(receipt):
                return
            stored_key = new_key.strip()
            try:
                self._sync_fields_from_draft(stored_key)
                self._selected_field_key = stored_key
                self._field_form_is_new = False
                self._load_field_form_for_key(stored_key)
            except Exception as exc:
                self._report_reload_after_commit(exc)
                return
            self._set_hint(f"Feld dupliziert: {source_key} -> {new_key}")
            self._log(f"Feld dupliziert: {source_key} -> {new_key}")
            self._maybe_refresh_field_markings()
        finally:
            self._field_mutation_guard = False

    def on_move_field(self, direction: str) -> None:
        if getattr(self, "_field_mutation_guard", False) or getattr(self, "_dialog_guard", False):
            return
        if not self.current_draft_path:
            self._set_hint("Bitte zuerst einen Entwurf laden.")
            return
        if not self._resolve_dirty_field_form():
            return
        key = self._selected_field_key
        if not key or self._field_form_is_new:
            self._set_hint("Bitte ein Feld auswählen.")
            return
        self._field_mutation_guard = True
        try:
            try:
                receipt = self._rules.move_field(
                    self.current_draft_path,
                    key,
                    direction,
                    return_receipt=True,
                )
            except Exception as exc:
                messagebox.showerror("Fehler", str(exc))
                return
            if not self._commit_receipt_undo(receipt):
                return
            try:
                self._sync_fields_from_draft(key)
                self._load_field_form_for_key(key)
            except Exception as exc:
                self._report_reload_after_commit(exc)
                return
            self._set_hint(f"Feld verschoben ({direction}): {key}")
            self._maybe_refresh_field_markings()
        finally:
            self._field_mutation_guard = False

    def on_remove_field(self) -> None:
        if getattr(self, "_field_mutation_guard", False) or getattr(self, "_dialog_guard", False):
            return
        if not self.current_draft_path:
            self._set_hint("Bitte zuerst einen Entwurf laden.")
            return
        if not self._resolve_dirty_field_form():
            return
        key = self._selected_field_key
        if not key or self._field_form_is_new:
            self._set_hint("Bitte Feld auswählen.")
            return
        confirmed = messagebox.askyesno(
            "Feld loeschen",
            f"Feld '{key}' wirklich loeschen?",
            parent=self if hasattr(self, "winfo_toplevel") else None,
        )
        if not confirmed:
            return
        self._field_mutation_guard = True
        try:
            try:
                receipt = self._rules.remove_field(self.current_draft_path, key, return_receipt=True)
            except Exception as exc:
                messagebox.showerror("Fehler", str(exc))
                return
            if not self._commit_receipt_undo(receipt):
                return
            try:
                self._sync_fields_from_draft(None)
                self._reset_field_form()
            except Exception as exc:
                self._report_reload_after_commit(exc)
                return
            self._set_hint(f"Feld entfernt: {key}")
            self._log(f"Feld entfernt: {key}")
            self._maybe_refresh_field_markings()
        finally:
            self._field_mutation_guard = False

    def on_rename_field(self) -> None:
        self._commit_replace_field()

    def _update_field_commit_button(self) -> None:
        button = getattr(self, "btn_field_commit", None)
        if button is None:
            return
        if self._field_form_is_new:
            button.configure(text="Neues Feld anlegen", state=tk.NORMAL, command=self.on_add_field)
        elif self._selected_field_key:
            button.configure(text="Markiertes Feld ersetzen", state=tk.NORMAL, command=self._commit_replace_field)
        else:
            button.configure(text="Markiertes Feld ersetzen", state=tk.DISABLED, command=self._commit_replace_field)
