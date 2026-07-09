"""MetaMixin: column_mapping, dedupe_fields und Meta-Speichern in den Draft."""
from __future__ import annotations

import tkinter as tk

from src.rulesuite.api import load_draft, save_draft, set_dedupe_fields, set_excel_rules, set_lot_rule


class MetaMixin:
    def _refresh_cols_tree(self) -> None:
        for row in self.tree_cols.get_children():
            self.tree_cols.delete(row)
        for k, v in sorted(self.column_mapping_data.items()):
            self.tree_cols.insert("", tk.END, values=(k, v))

    def on_col_selected(self, _event: object = None) -> None:
        sel = self.tree_cols.selection()
        if not sel:
            return
        vals = self.tree_cols.item(sel[0], "values")
        self.var_col_key.set(str(vals[0]))
        self.var_col_name.set(str(vals[1]))

    def on_set_col(self) -> None:
        key = self.var_col_key.get().strip()
        name = self.var_col_name.get().strip()
        if not key or not name:
            self._set_hint("Spaltenzuordnung benoetigt Feldname und Excel-Spalte.")
            return
        self._push_undo_snapshot()
        self.column_mapping_data[key] = name
        self._refresh_cols_tree()
        self._set_hint(f"Spaltenzuordnung gesetzt: {key} -> {name}")
        self._dirty = True

    def on_remove_col(self) -> None:
        key = self.var_col_key.get().strip()
        if not key:
            self._set_hint("Bitte Feldname fuer Entfernen angeben.")
            return
        self._push_undo_snapshot()
        self.column_mapping_data.pop(key, None)
        self._refresh_cols_tree()
        self._set_hint(f"Spaltenzuordnung entfernt: {key}")
        self._dirty = True

    def _normalize_column_mapping(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for key, value in self.column_mapping_data.items():
            k = str(key).strip()
            v = str(value).strip()
            if not k or not v:
                continue
            out[k] = v
        return out

    def _normalize_dedupe_fields(self) -> list[str]:
        raw = [x.strip() for x in self.var_dedupe_fields.get().split(",")]
        out: list[str] = []
        seen: set[str] = set()
        for item in raw:
            if item and item not in seen:
                out.append(item)
                seen.add(item)
        return out

    def _save_meta_to_draft(self, push_undo: bool = False) -> dict:
        if not self.current_draft_path:
            raise RuntimeError("draft missing")

        assay_key = self.var_new_assay_key.get().strip()
        assay_name = self.var_new_assay_name.get().strip()
        if not assay_key or not assay_name:
            raise ValueError("assay_key und assay_name sind erforderlich")

        lot_regex = self.var_lot_regex.get().strip()
        if not lot_regex:
            raise ValueError("lot_rule.regex darf nicht leer sein")

        excel_filename = self.var_excel_filename.get().strip()
        sheet_template = self.var_sheet_template.get().strip()
        if not excel_filename or not sheet_template:
            raise ValueError("excel_filename_template und sheetname_template sind erforderlich")

        dedupe = self._normalize_dedupe_fields()
        col_map = self._normalize_column_mapping()

        if push_undo:
            self._push_undo_snapshot()
        set_lot_rule(self.current_draft_path, lot_regex)
        set_dedupe_fields(self.current_draft_path, dedupe)
        set_excel_rules(
            self.current_draft_path,
            excel_filename,
            sheet_template,
            col_map,
        )

        data = load_draft(self.current_draft_path)
        data["assay_key"] = assay_key
        data["assay_name"] = assay_name
        save_draft(self.current_draft_path, data)

        self.column_mapping_data = col_map
        self.var_dedupe_fields.set(",".join(dedupe))
        self._dirty = False
        return data
