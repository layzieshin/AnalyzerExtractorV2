"""FieldsMixin: Feld-CRUD, Feldformular und Felder-Tabelle."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, simpledialog

from src.rulesuite.api import (
    add_field,
    duplicate_field,
    load_draft,
    move_field,
    remove_field,
    rename_field,
    update_field,
)


class FieldsMixin:
    def _refresh_fields_tree(self, selected_key: str | None = None) -> None:
        for row in self.tree_fields.get_children():
            self.tree_fields.delete(row)
        selected_item = None
        for f in self.fields_data:
            key = str(f.get("key", ""))
            regex = str(f.get("regex", ""))
            required = bool(f.get("required", False))
            sf = self._render_search_from(f.get("search_from"))
            item = self.tree_fields.insert("", tk.END, values=(key, regex, str(required), sf))
            if selected_key and key == selected_key:
                selected_item = item

        if selected_item:
            self.tree_fields.selection_set(selected_item)
            self.tree_fields.focus(selected_item)
            self.tree_fields.see(selected_item)

    def _render_search_from(self, search_from: object) -> str:
        if not isinstance(search_from, dict):
            return ""
        if "after" in search_from:
            return f"after:{search_from.get('after', '')}"
        if "line" in search_from:
            return f"line:{search_from.get('line', '')}"
        return ""

    def on_field_selected(self, _event: object = None) -> None:
        sel = self.tree_fields.selection()
        if not sel:
            return
        key = str(self.tree_fields.item(sel[0], "values")[0])
        # Bereits synchron (Formular + Markierung zeigen dieses Feld) -> abbrechen,
        # damit asynchrone <<TreeviewSelect>>-Ketten nicht endlos weiterlaufen.
        if key == self._active_marking_key and self.var_field_key.get().strip() == key:
            return
        if not self._load_field_form_for_key(key):
            return

        if not self._marking_sync_guard:
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
                "Kein Beispiel-PDF geladen - im Tab 'PDF / Assay-Text' Text laden, um die Fundstelle zu pruefen."
            )
            return
        row = self._field_marking_data.get(key)
        if row is None:
            self.var_field_guidance.set(
                "Fundstelle noch nicht geprueft - im PDF-Tab 'Markierungen aktualisieren' ausfuehren."
            )
            return
        error = str(row.get("error") or "").strip()
        if error:
            self.var_field_guidance.set(f"Regex-Fehler: {error}")
        elif row.get("matched"):
            self.var_field_guidance.set(f"Fundstelle vorhanden: {row.get('value')} (im PDF-Tab markiert).")
        else:
            self.var_field_guidance.set(
                "Keine Fundstelle im Beispiel-PDF - bitte Stelle hinterlegen: im PDF-Tab Text markieren "
                "und Regex/'Suche ab' uebernehmen."
            )

    def _load_field_form_for_key(self, key: str) -> bool:
        row = next((f for f in self.fields_data if str(f.get("key", "")) == key), None)
        if row is None:
            return False

        prev_suspend = self._suspend_dirty_tracking
        self._suspend_dirty_tracking = True
        try:
            self.var_field_key.set(key)
            self.var_field_regex.set(str(row.get("regex", "")))
            self.var_field_required.set(bool(row.get("required", False)))

            sf = row.get("search_from")
            if isinstance(sf, dict) and "after" in sf:
                self.var_search_mode.set("after")
                self.var_search_after.set(str(sf.get("after", "")))
                self.var_search_line.set("")
            elif isinstance(sf, dict) and "line" in sf:
                self.var_search_mode.set("line")
                self.var_search_line.set(str(sf.get("line", "")))
                self.var_search_after.set("")
            else:
                self.var_search_mode.set("none")
                self.var_search_after.set("")
                self.var_search_line.set("")
        finally:
            self._suspend_dirty_tracking = prev_suspend
        return True

    def _reset_field_form(self) -> None:
        self.var_field_key.set("")
        self.var_field_regex.set("")
        self.var_field_required.set(False)
        self.var_search_mode.set("none")
        self.var_search_after.set("")
        self.var_search_line.set("")
        self.var_regex_group.set("1")
        self.tree_fields.selection_remove(self.tree_fields.selection())
        self.txt_block.tag_remove("field_emphasis", "1.0", tk.END)
        self._active_marking_key = None
        self.var_field_guidance.set("")
        self._set_hint("Feldformular zurückgesetzt.")

    def _build_search_from(self) -> dict | None:
        mode = self.var_search_mode.get().strip()
        if mode == "after":
            after = self.var_search_after.get().strip()
            return {"after": after} if after else None
        if mode == "line":
            line_raw = self.var_search_line.get().strip()
            if not line_raw:
                return None
            try:
                return {"line": int(line_raw)}
            except ValueError:
                raise ValueError("search_from.line muss integer sein")
        return None

    def _reload_column_mapping_from_draft(self) -> None:
        if not self.current_draft_path:
            return
        data = load_draft(self.current_draft_path)
        excel_rules = data.get("excel_rules")
        if not isinstance(excel_rules, dict):
            excel_rules = {}
        col_map = excel_rules.get("column_mapping")
        self.column_mapping_data = dict(col_map) if isinstance(col_map, dict) else {}
        self._refresh_cols_tree()

    def on_add_field(self) -> None:
        if not self.current_draft_path:
            self._set_hint("Bitte zuerst Draft laden. Tipp: Oben 'Draft aus aktivem Assay' oder 'Draft laden in Editor' nutzen.")
            return
        key = self.var_field_key.get().strip()
        regex = self.var_field_regex.get().strip()
        if not key or not regex:
            self._set_hint("Feld key und regex sind erforderlich. Tipp: key eindeutig setzen und regex mit 'Regex testen' pruefen.")
            return
        try:
            self._push_undo_snapshot()
            sf = self._build_search_from()
            add_field(self.current_draft_path, key, regex, required=self.var_field_required.get(), search_from=sf)
            self.fields_data = load_draft(self.current_draft_path).get("extract_rules", {}).get("fields", [])
            self._reload_column_mapping_from_draft()
            self._refresh_fields_tree(selected_key=key)
            self._set_hint(f"Feld hinzugefügt: {key}")
            self._log(f"Feld hinzugefügt: {key}")
            self._dirty = False
            self._maybe_refresh_field_markings()
        except Exception as e:
            messagebox.showerror("Fehler", str(e))

    def on_apply_field(self) -> None:
        if not self.current_draft_path:
            self._set_hint("Bitte zuerst Draft laden. Tipp: Erst Draft laden, dann Feld aendern.")
            return
        key = self.var_field_key.get().strip()
        regex = self.var_field_regex.get().strip()
        if not key or not regex:
            self._set_hint("Feld key und regex sind erforderlich. Tipp: Feld in Tabelle auswaehlen oder neuen key setzen.")
            return
        try:
            self._push_undo_snapshot()
            sf = self._build_search_from()
            update_field(
                self.current_draft_path,
                key,
                regex=regex,
                required=self.var_field_required.get(),
                search_from=sf if self.var_search_mode.get() != "none" else {},
            )
            self.fields_data = load_draft(self.current_draft_path).get("extract_rules", {}).get("fields", [])
            self._reload_column_mapping_from_draft()
            self._refresh_fields_tree(selected_key=key)
            self._set_hint(f"Feld aktualisiert: {key}")
            self._log(f"Feld aktualisiert: {key}")
            self._dirty = False
            self._maybe_refresh_field_markings()
        except Exception as e:
            messagebox.showerror("Fehler", str(e))

    def on_duplicate_field(self) -> None:
        if not self.current_draft_path:
            self._set_hint("Bitte zuerst Draft laden. Tipp: Erst Draft laden, dann Feld duplizieren.")
            return
        sel = self.tree_fields.selection()
        if not sel:
            self._set_hint("Bitte ein Feld zum Duplizieren auswählen.")
            return
        source_key = str(self.tree_fields.item(sel[0], "values")[0]).strip()
        new_key = simpledialog.askstring("Feld duplizieren", f"Neuer Key für Kopie von '{source_key}':")
        if not new_key:
            return
        try:
            self._push_undo_snapshot()
            duplicate_field(self.current_draft_path, source_key, new_key)
            self.fields_data = load_draft(self.current_draft_path).get("extract_rules", {}).get("fields", [])
            self._reload_column_mapping_from_draft()
            self._refresh_fields_tree(selected_key=new_key)
            self._set_hint(f"Feld dupliziert: {source_key} -> {new_key}")
            self._log(f"Feld dupliziert: {source_key} -> {new_key}")
            self._dirty = False
            self._maybe_refresh_field_markings()
        except Exception as e:
            messagebox.showerror("Fehler", str(e))

    def on_move_field(self, direction: str) -> None:
        if not self.current_draft_path:
            self._set_hint("Bitte zuerst Draft laden. Tipp: Erst Draft laden, dann Feld verschieben.")
            return
        sel = self.tree_fields.selection()
        if not sel:
            self._set_hint("Bitte ein Feld auswählen.")
            return
        key = str(self.tree_fields.item(sel[0], "values")[0]).strip()
        try:
            self._push_undo_snapshot()
            move_field(self.current_draft_path, key, direction)
            self.fields_data = load_draft(self.current_draft_path).get("extract_rules", {}).get("fields", [])
            self._refresh_fields_tree(selected_key=key)
            self._set_hint(f"Feld verschoben ({direction}): {key}")
            self._dirty = False
            self._maybe_refresh_field_markings()
        except Exception as e:
            messagebox.showerror("Fehler", str(e))

    def on_remove_field(self) -> None:
        if not self.current_draft_path:
            self._set_hint("Bitte zuerst Draft laden. Tipp: Erst Draft laden, dann Feld entfernen.")
            return
        key = self.var_field_key.get().strip()
        if not key:
            self._set_hint("Bitte Feld auswählen.")
            return
        try:
            self._push_undo_snapshot()
            remove_field(self.current_draft_path, key)
            self.fields_data = load_draft(self.current_draft_path).get("extract_rules", {}).get("fields", [])
            self._reload_column_mapping_from_draft()
            self._refresh_fields_tree()
            self._reset_field_form()
            self._set_hint(f"Feld entfernt: {key}")
            self._log(f"Feld entfernt: {key}")
            self._dirty = False
            self._maybe_refresh_field_markings()
        except Exception as e:
            messagebox.showerror("Fehler", str(e))

    def on_rename_field(self) -> None:
        if not self.current_draft_path:
            self._set_hint("Bitte zuerst Draft laden. Tipp: Erst Draft laden, dann Feld umbenennen.")
            return
        sel = self.tree_fields.selection()
        if not sel:
            self._set_hint("Bitte ein Feld auswählen.")
            return
        old_key = str(self.tree_fields.item(sel[0], "values")[0])
        new_key = self.var_field_key.get().strip()
        if not new_key:
            self._set_hint("Bitte neuen Feld-Key eintragen.")
            return
        try:
            self._push_undo_snapshot()
            rename_field(self.current_draft_path, old_key, new_key)
            self.fields_data = load_draft(self.current_draft_path).get("extract_rules", {}).get("fields", [])
            self._reload_column_mapping_from_draft()
            self._refresh_fields_tree(selected_key=new_key)
            self._set_hint(f"Feld umbenannt: {old_key} -> {new_key}")
            self._log(f"Feld umbenannt: {old_key} -> {new_key}")
            self._dirty = False
            self._maybe_refresh_field_markings()
        except Exception as e:
            messagebox.showerror("Fehler", str(e))
