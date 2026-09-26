"""DraftMixin: Draft-Lifecycle, Assay-Index und Datenuebernahme in die Widgets."""
from __future__ import annotations

from pathlib import Path
from tkinter import filedialog, messagebox


def _index_json_missing(exc: Exception) -> bool:
    message = str(exc).lower()
    if "index.json" not in message:
        return False
    return any(
        marker in message
        for marker in (
            "no such file",
            "cannot find the file",
            "cannot find the path",
            "filenotfounderror",
            "errno 2",
            "datei nicht finden",
            "pfad nicht finden",
        )
    )


class DraftMixin:
    def _selected_assay_key(self) -> str | None:
        display = self.var_assay.get().strip()
        return self.assay_display_to_key.get(display)

    def _reload_assays(self) -> None:
        combo = getattr(self, "cmb_assay", None)
        try:
            items = self._rules.list_inventory(kind="active")
        except Exception as exc:
            if _index_json_missing(exc):
                if combo is not None:
                    combo["values"] = []
                self.assay_display_to_key = {}
                self.known_assay_keys = set()
                self._set_hint("Kein rules/index.json gefunden.")
                return
            messagebox.showerror("Fehler", f"index.json konnte nicht gelesen werden: {exc}")
            return

        entries: list[str] = []
        mapping: dict[str, str] = {}
        known: set[str] = set()
        for item in items:
            key = str(getattr(item, "assay_key", "") or "").strip()
            file_name = str(getattr(item, "ruleset_file", "") or "").strip()
            if not key or not file_name:
                continue
            known.add(key)
            assay_name = file_name.rsplit(".", 1)[0]
            display = f"{key} | {assay_name}"
            entries.append(display)
            mapping[display] = key

        self.assay_display_to_key = mapping
        self.known_assay_keys = known
        if combo is not None:
            combo["values"] = entries
            assay_var = getattr(self, "var_assay", None)
            if assay_var is not None and entries and assay_var.get() not in entries:
                assay_var.set(entries[0])
        self._set_hint(f"{len(entries)} aktive Assays geladen.")

    def _same_project_root(self, left: str, right: str) -> bool:
        if not str(left).strip() or not str(right).strip():
            return False
        try:
            return Path(left).resolve() == Path(right).resolve()
        except OSError:
            return str(left).strip() == str(right).strip()

    def on_pick_root(self) -> None:
        if getattr(self, "_field_mutation_guard", False) or getattr(self, "_dialog_guard", False):
            return
        guard = getattr(self, "_resolve_dirty_field_form", None)
        if callable(guard) and not guard():
            return
        self._dialog_guard = True
        try:
            chosen = filedialog.askdirectory(title="Projekt-Root")
        finally:
            self._dialog_guard = False
        if not chosen:
            return
        if self._same_project_root(chosen, self.var_root.get()):
            return
        pending = getattr(self, "_resolve_pending_meta_changes", None)
        if callable(pending) and not pending(
            save_label="speichern und den Projektordner wechseln",
            discard_label="Änderungen verwerfen und den Projektordner wechseln",
            cancel_label="im aktuellen Projektordner bleiben",
        ):
            return
        self.var_root.set(chosen)
        clearer = getattr(self, "_clear_loaded_draft", None)
        if callable(clearer):
            clearer()
        self._reload_assays()
        refresh = getattr(self, "_refresh_ruleset_overview", None)
        if callable(refresh):
            refresh()

    def on_pick_draft(self) -> None:
        p = filedialog.askopenfilename(title="Draft wählen", filetypes=[("JSON", "*.json")])
        if p:
            self.var_draft_path.set(p)

    def on_pick_pdf(self) -> None:
        p = filedialog.askopenfilename(title="PDF wählen", filetypes=[("PDF", "*.pdf")])
        if p:
            self.var_pdf.set(p)

    def _guard_before_editor_load(self, target_path: str) -> str:
        guard = getattr(self, "_confirm_draft_switch", None)
        if not callable(guard):
            return "proceed"
        return str(guard(target_path))

    def on_create_from_active(self) -> None:
        assay_key = self._selected_assay_key()
        if not assay_key:
            self._set_hint("Bitte zuerst ein aktives Assay auswählen.")
            return
        predicted = ""
        predictor = getattr(self._rules, "draft_path_for_assay", None)
        if callable(predictor):
            try:
                predicted = str(predictor(assay_key))
            except Exception:
                predicted = ""
        decision = self._guard_before_editor_load(predicted)
        if decision == "abort":
            return
        if decision == "focus":
            focus = getattr(self, "_focus_loaded_workspace", None)
            if callable(focus):
                focus()
            return
        try:
            path = self._rules.create_draft(assay_key)
            if self.on_load_draft_into_editor(path) is False:
                return
            self._log(f"Draft erstellt: {path}")
        except Exception as e:
            messagebox.showerror("Fehler", str(e))

    def on_create_blank(self) -> None:
        key = self.var_new_assay_key.get().strip()
        name = self.var_new_assay_name.get().strip()
        if not key or not name:
            self._set_hint("neuer assay_key und assay_name sind erforderlich.")
            return
        predicted = ""
        predictor = getattr(self._rules, "draft_path_for_assay", None)
        if callable(predictor):
            try:
                predicted = str(predictor(key))
            except Exception:
                predicted = ""
        decision = self._guard_before_editor_load(predicted)
        if decision == "abort":
            return
        if decision == "focus":
            focus = getattr(self, "_focus_loaded_workspace", None)
            if callable(focus):
                focus()
            return
        try:
            path = self._rules.create_draft_from_template(key, name)
            if self.on_load_draft_into_editor(path) is False:
                return
            self._log(f"Draft mit Header-Vertrag erstellt: {path}")
            self._set_hint("Draft mit Header-Vertrag erstellt.")
        except Exception as e:
            messagebox.showerror("Fehler", str(e))

    def on_derive(self) -> None:
        self.on_open_clone_ruleset_dialog()

    def _restore_draft_targets(self, variable: object, backing: str, current: object) -> None:
        if variable is not None and hasattr(variable, "set"):
            variable.set(backing)
        self.current_draft_path = current

    def on_load_draft_into_editor(self, target_path: str | None = None) -> bool:
        variable = getattr(self, "var_draft_path", None)
        previous_backing = variable.get() if variable is not None and hasattr(variable, "get") else ""
        requested = str(target_path).strip() if target_path is not None else str(previous_backing).strip()
        if not requested:
            self._set_hint("Bitte draft_path setzen.")
            return False
        previous_current = getattr(self, "current_draft_path", None)
        try:
            data = self._rules.load_draft(requested)
        except Exception as exc:
            self._restore_draft_targets(variable, previous_backing, previous_current)
            messagebox.showerror("Fehler", str(exc))
            return False
        try:
            if variable is not None and hasattr(variable, "set"):
                variable.set(requested)
            self.current_draft_path = requested
            self._apply_data_to_widgets(data)
            previous = str(previous_current or "")
            comparer = getattr(self, "_same_draft_path", None)
            same_draft = comparer(previous, requested) if callable(comparer) else previous == requested
            if previous and not same_draft:
                undo = getattr(self, "_undo_stack", None)
                redo = getattr(self, "_redo_stack", None)
                if undo is not None:
                    undo.clear()
                if redo is not None:
                    redo.clear()
            self._set_hint(f"Draft geladen: {requested}")
            self._log(f"Draft geladen: {requested}")
            show_page = getattr(self, "_show_page", None)
            if callable(show_page):
                show_page("workspace")
            return True
        except Exception as exc:
            self._restore_draft_targets(variable, previous_backing, previous_current)
            messagebox.showerror("Fehler", str(exc))
            return False

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
        if hasattr(self, "_field_form_dirty"):
            self._field_form_dirty = False
        if hasattr(self, "_selected_field_key"):
            self._selected_field_key = None
        if hasattr(self, "_field_form_is_new"):
            self._field_form_is_new = False
