"""DraftMixin: Draft-Lifecycle, Assay-Index und Datenuebernahme in die Widgets."""
from __future__ import annotations

import json
from pathlib import Path
from tkinter import filedialog, messagebox

from src.rulesuite.api import create_draft, create_draft_from_template, derive_draft, load_draft


class DraftMixin:
    def _selected_assay_key(self) -> str | None:
        display = self.var_assay.get().strip()
        return self.assay_display_to_key.get(display)

    def _rules_root(self) -> Path:
        return Path(self.var_root.get().strip()) / "rules"

    def _reload_assays(self) -> None:
        rules_root = self._rules_root()
        index_path = rules_root / "index.json"
        if not index_path.exists():
            self.cmb_assay["values"] = []
            self._set_hint("Kein rules/index.json gefunden.")
            return
        try:
            idx = json.loads(index_path.read_text(encoding="utf-8"))
        except Exception as e:
            messagebox.showerror("Fehler", f"index.json konnte nicht gelesen werden: {e}")
            return

        entries: list[str] = []
        mapping: dict[str, str] = {}
        known: set[str] = set()
        for row in idx.get("assays", []):
            if not isinstance(row, dict):
                continue
            key = str(row.get("assay_key", "")).strip()
            file_name = str(row.get("ruleset_file", "")).strip()
            if not key or not file_name:
                continue
            known.add(key)
            assay_name = file_name.rsplit(".", 1)[0]
            display = f"{key} | {assay_name}"
            entries.append(display)
            mapping[display] = key

        self.assay_display_to_key = mapping
        self.known_assay_keys = known
        self.cmb_assay["values"] = entries
        if entries and self.var_assay.get() not in entries:
            self.var_assay.set(entries[0])
        self._set_hint(f"{len(entries)} aktive Assays geladen.")

    def on_pick_root(self) -> None:
        d = filedialog.askdirectory(title="Projekt-Root")
        if d:
            self.var_root.set(d)
            self._reload_assays()

    def on_pick_draft(self) -> None:
        p = filedialog.askopenfilename(title="Draft wählen", filetypes=[("JSON", "*.json")])
        if p:
            self.var_draft_path.set(p)

    def on_pick_pdf(self) -> None:
        p = filedialog.askopenfilename(title="PDF wählen", filetypes=[("PDF", "*.pdf")])
        if p:
            self.var_pdf.set(p)

    def on_create_from_active(self) -> None:
        assay_key = self._selected_assay_key()
        if not assay_key:
            self._set_hint("Bitte zuerst ein aktives Assay auswählen.")
            return
        try:
            path = create_draft(self.var_root.get().strip(), assay_key)
            self.var_draft_path.set(path)
            self.on_load_draft_into_editor()
            self._log(f"Draft erstellt: {path}")
        except Exception as e:
            messagebox.showerror("Fehler", str(e))

    def on_create_blank(self) -> None:
        key = self.var_new_assay_key.get().strip()
        name = self.var_new_assay_name.get().strip()
        if not key or not name:
            self._set_hint("neuer assay_key und assay_name sind erforderlich.")
            return
        try:
            path = create_draft_from_template(self.var_root.get().strip(), key, name)
            self.var_draft_path.set(path)
            self.on_load_draft_into_editor()
            self._log(f"Draft mit Header-Vertrag erstellt: {path}")
            self._set_hint("Draft mit Header-Vertrag erstellt.")
        except Exception as e:
            messagebox.showerror("Fehler", str(e))

    def on_derive(self) -> None:
        source_key = self._selected_assay_key()
        target_key = self.var_new_assay_key.get().strip()
        target_name = self.var_new_assay_name.get().strip()
        if not source_key:
            self._set_hint("Bitte zuerst ein Quell-Assay auswählen.")
            return
        if not target_key or not target_name:
            self._set_hint("neuer assay_key und assay_name sind erforderlich.")
            return
        try:
            path = derive_draft(self.var_root.get().strip(), source_key, target_key, target_name)
            self.var_draft_path.set(path)
            self.on_load_draft_into_editor()
            self._log(f"Draft abgeleitet: {path}")
        except Exception as e:
            messagebox.showerror("Fehler", str(e))

    def on_load_draft_into_editor(self) -> None:
        path = self.var_draft_path.get().strip()
        if not path:
            self._set_hint("Bitte draft_path setzen.")
            return
        try:
            data = load_draft(path)
            self.current_draft_path = path
            self._apply_data_to_widgets(data)
            self._set_hint(f"Draft geladen: {path}")
            self._log(f"Draft geladen: {path}")
        except Exception as e:
            messagebox.showerror("Fehler", str(e))

    def _apply_data_to_widgets(self, data: dict) -> None:
        self._suspend_dirty_tracking = True
        try:
            self.var_new_assay_key.set(str(data.get("assay_key", "")))
            self.var_new_assay_name.set(str(data.get("assay_name", "")))

            lot = data.get("lot_rule", {})
            self.var_lot_regex.set(str(lot.get("regex", "")) if isinstance(lot, dict) else "")

            extract_rules = data.get("extract_rules", {}) if isinstance(data.get("extract_rules"), dict) else {}
            self.fields_data = list(extract_rules.get("fields", [])) if isinstance(extract_rules.get("fields"), list) else []
            dedupe = extract_rules.get("dedupe_fields", [])
            if isinstance(dedupe, list):
                self.var_dedupe_fields.set(",".join(str(x) for x in dedupe if str(x).strip()))
            else:
                self.var_dedupe_fields.set("")

            excel_rules = data.get("excel_rules", {}) if isinstance(data.get("excel_rules"), dict) else {}
            self.var_excel_filename.set(str(excel_rules.get("excel_filename_template", "{assay_name}.xlsx")))
            self.var_sheet_template.set(str(excel_rules.get("sheetname_template", "{lot_id}")))
            col_map = excel_rules.get("column_mapping", {})
            self.column_mapping_data = dict(col_map) if isinstance(col_map, dict) else {}

            self._refresh_fields_tree()
            self._refresh_cols_tree()
            self._clear_validation_list()
            self._reset_field_form()
            self._maybe_refresh_field_markings()
        finally:
            self._suspend_dirty_tracking = False
            self._dirty = False
