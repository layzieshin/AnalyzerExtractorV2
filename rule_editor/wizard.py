"""Geführte, PDF-first Regelerstellung und -prüfung.

Eigenes modales Fenster:
1. PDF und Ziel (neue Regel oder vorhandener Entwurf)
2. Felder prüfen
3. Weitere Felder
4. Abschlussprüfung
"""
from __future__ import annotations

import os
import threading
import tkinter as tk
from typing import Callable
from tkinter import filedialog, messagebox

from .wizard_ui import _SEARCH_LABEL_TO_MODE, _SEARCH_MODE_LABELS, _STEP_TITLES, _STEPS, WizardUiMixin

_WINDOW_TITLE = "Regel aus PDF erstellen oder prüfen"
_FULLTEXT_FALLBACK_WARNING = (
    "Assay-Abschnitt nicht gefunden. Der vollständige PDF-Text ist nur eine sichtbare "
    "Authoring-Hilfe und kann für diesen Entwurf geprüft werden."
)
_TARGET_CONTROL_NAMES = (
    "rad_mode_new",
    "rad_mode_existing",
    "ent_assay_key",
    "ent_assay_name",
    "list_drafts",
)


class NewRulesetWizard(WizardUiMixin, tk.Toplevel):
    def __init__(
        self,
        master: tk.Misc,
        rules: object,
        on_open_in_editor: Callable[[str], None] | None = None,
        on_activate_requested: Callable[[str], None] | None = None,
        *,
        start_intent: str = "neutral",
        on_session_closed: Callable[[str | None], None] | None = None,
    ) -> None:
        super().__init__(master)
        self.withdraw()
        self.title(_WINDOW_TITLE)
        self.geometry("1100x780")
        self.transient(master)
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

        self._rules = rules
        self._on_open_in_editor = on_open_in_editor or (lambda _path: None)
        self._on_activate_requested = on_activate_requested or (lambda _path: None)
        self._on_session_closed = on_session_closed
        self._start_intent = start_intent if start_intent in {"neutral", "new"} else "neutral"

        self._step = 0
        self.draft_path: str | None = None
        self._pending_draft_path: str | None = None
        self._draft_choices: list[dict[str, str]] = []
        self._normalized_pdf_text = ""
        self.assay_text: str = ""
        self._derived_for: tuple[str, str, str] | None = None
        self._using_fulltext_fallback = False
        self._fields: list[dict] = []
        self._field_idx = 0
        self._busy = False
        self._field_report: dict | None = None
        self._pdf_fingerprint = ""
        self._pdf_request_id = 0
        self._closed = False

        self.var_key = tk.StringVar(value="")
        self.var_name = tk.StringVar(value="")
        self.var_mode = tk.StringVar(value="new" if self._start_intent == "new" else "")
        self.var_pdf = tk.StringVar(value="")
        self.var_reference_pdf = tk.StringVar(value="")
        self.var_status = tk.StringVar(value="")
        self.var_match = tk.StringVar(value="")
        self.var_progress = tk.StringVar(value="")
        self.var_custom_count = tk.StringVar(value="")
        self.var_finish_action = tk.StringVar(value="editor")
        self.var_f_key = tk.StringVar(value="")
        self.var_f_regex = tk.StringVar(value="")
        self.var_f_mode = tk.StringVar(value="none")
        self.var_f_search_label = tk.StringVar(value=_SEARCH_MODE_LABELS["none"])
        self.var_f_after = tk.StringVar(value="")
        self.var_f_line = tk.StringVar(value="")
        self.var_pdf.trace_add("write", self._on_pdf_path_changed)
        self.var_key.trace_add("write", self._on_target_identity_changed)
        self.var_name.trace_add("write", self._on_target_identity_changed)
        self.var_mode.trace_add("write", self._on_target_identity_changed)
        self.var_f_search_label.trace_add("write", self._on_search_label_changed)

        self._build_ui()
        self._refresh_draft_choices()
        self._show_step(0)

        self.update_idletasks()
        self.deiconify()
        self.wait_visibility()
        self.lift()
        self.grab_set()
        self.focus_force()

    def _show_step(self, idx: int) -> None:
        self._step = idx
        key = _STEPS[idx]
        self.lbl_title.config(text=_STEP_TITLES[key])
        self._card_frames[key].tkraise()
        can_back = idx > 0 and not (key == "fields" and self._field_idx <= 0)
        self.btn_back.config(state=tk.NORMAL if can_back else tk.DISABLED)
        if key == "fields":
            self.btn_next.config(text="Speichern und nächstes Feld")
        elif key == "custom":
            self.btn_next.config(text="Keine weiteren Felder / Abschluss prüfen")
        elif key == "finish":
            self.btn_next.config(text="Fertig stellen")
        else:
            self.btn_next.config(text="Weiter zu den Feldern")
        self.var_match.set("")
        if key == "target":
            self._refresh_draft_choices()
            self.var_status.set("PDF laden und danach ausdrücklich neue Regel oder vorhandenen Entwurf wählen.")
        elif key == "fields":
            self._set_status("Regex und Suchbereich prüfen. Speichern geht nur mit nichtleerem Treffer.")
        elif key == "custom":
            self._reload_fields()
            self._clear_field_form()
            self.var_custom_count.set(f"Aktuell {len(self._fields)} Felder im Entwurf.")
            self._set_status("Weitere Felder prüfen und hinzufügen oder die Abschlussprüfung starten.")
        elif key == "finish":
            self._render_summary()
            self._set_status("Struktur und Treffer prüfen, dann den Entwurf öffnen oder aktivieren.")

    def _on_next(self) -> None:
        if self._busy:
            return
        key = _STEPS[self._step]
        if key == "target":
            if not self._commit_target():
                return
            self._reload_fields()
            self._fields = self._ordered_configured_fields()
            self._field_idx = 0
            if self._fields:
                self._show_step(1)
                self._show_current_field()
            else:
                self._show_step(2)
        elif key == "fields":
            if not self._save_current_field():
                return
            if self._field_idx + 1 < len(self._fields):
                self._field_idx += 1
                self._show_current_field()
            else:
                self._show_step(2)
        elif key == "custom":
            if not self._all_fields_confirmed():
                self.var_status.set(
                    "Abschlussprüfung blockiert: jedes konfigurierte Feld braucht einen nichtleeren Treffer."
                )
                return
            self._show_step(3)
        elif key == "finish":
            self._finish()

    def _on_back(self) -> None:
        if self._busy:
            return
        key = _STEPS[self._step]
        if key == "fields" and self._field_idx > 0:
            self._field_idx -= 1
            self._show_current_field()
            return
        if key == "custom":
            self._reload_fields()
            if self._fields:
                self._field_idx = len(self._fields) - 1
                self._show_step(1)
                self._show_current_field()
            return
        if key == "finish":
            self._show_step(2)

    def _on_cancel(self) -> None:
        msg = (
            "Geführte Prüfung abbrechen?\n\n"
            "Bereits gespeicherte Feldschritte bleiben im Entwurf erhalten. "
            "Es wird nichts aktiviert und kein Nachweis freigegeben."
        )
        if self.draft_path:
            msg += "\n\nEntwurf:\n" + self.draft_path
        if messagebox.askyesno("Abbrechen", msg, parent=self):
            self._shutdown(None)

    def _shutdown(self, action: str | None) -> None:
        if getattr(self, "_closed", False):
            return
        self._closed = True
        self._pdf_request_id = int(getattr(self, "_pdf_request_id", 0)) + 1
        draft = self.draft_path
        callback = getattr(self, "_on_session_closed", None)
        self.destroy()
        if callable(callback):
            callback(draft)
        if action == "activate" and draft:
            self._on_activate_requested(draft)
        elif action == "editor" and draft:
            self._on_open_in_editor(draft)

    def _on_mode_changed(self) -> None:
        if not self._pdf_ready():
            return
        if self.var_mode.get() == "new":
            self._pending_draft_path = None
        self._apply_target_control_states()

    def _on_pdf_path_changed(self, *_args: object) -> None:
        if self.var_pdf.get().strip() != self._pdf_fingerprint:
            self._invalidate_neutral_pdf()

    def _on_target_identity_changed(self, *_args: object) -> None:
        self._apply_target_control_states()
        if self._derived_for is None:
            return
        if self._current_target_identity() != self._derived_for:
            self._clear_derived_assay_text()

    def _current_target_identity(self) -> tuple[str, str, str]:
        return (
            self.var_mode.get().strip(),
            self.var_key.get().strip(),
            self.var_name.get().strip(),
        )

    def _invalidate_neutral_pdf(self) -> None:
        self._normalized_pdf_text = ""
        self._pdf_fingerprint = ""
        self._clear_derived_assay_text()
        self._pdf_request_id += 1
        self._busy = False
        self._apply_target_control_states()

    def _clear_derived_assay_text(self) -> None:
        self.assay_text = ""
        self._derived_for = None
        self._using_fulltext_fallback = False

    def _pdf_ready(self) -> bool:
        pdf = self.var_pdf.get().strip()
        text = str(getattr(self, "_normalized_pdf_text", "") or "")
        return pdf.lower().endswith(".pdf") and bool(text.strip()) and pdf == self._pdf_fingerprint

    def _configure_target_widget(self, name: str, state: str) -> None:
        widget = getattr(self, name, None)
        if widget is None:
            return
        try:
            widget.configure(state=state)
        except (tk.TclError, AttributeError):
            return

    def _apply_target_control_states(self) -> None:
        if not self._pdf_ready():
            for name in _TARGET_CONTROL_NAMES:
                self._configure_target_widget(name, tk.DISABLED)
            return
        self._configure_target_widget("rad_mode_new", tk.NORMAL)
        self._configure_target_widget("rad_mode_existing", tk.NORMAL)
        mode = self.var_mode.get().strip()
        if mode == "new":
            self._configure_target_widget("ent_assay_key", tk.NORMAL)
            self._configure_target_widget("ent_assay_name", tk.NORMAL)
            self._configure_target_widget("list_drafts", tk.DISABLED)
        elif mode == "existing":
            self._configure_target_widget("ent_assay_key", tk.DISABLED)
            self._configure_target_widget("ent_assay_name", tk.DISABLED)
            self._configure_target_widget("list_drafts", tk.NORMAL)
        else:
            self._configure_target_widget("ent_assay_key", tk.DISABLED)
            self._configure_target_widget("ent_assay_name", tk.DISABLED)
            self._configure_target_widget("list_drafts", tk.DISABLED)

    def _set_status(self, message: str) -> None:
        if getattr(self, "_using_fulltext_fallback", False) and _FULLTEXT_FALLBACK_WARNING not in message:
            message = f"{message} {_FULLTEXT_FALLBACK_WARNING}"
        self.var_status.set(message)

    def _refresh_draft_choices(self) -> None:
        self._draft_choices = []
        if not hasattr(self, "list_drafts"):
            return
        self.list_drafts.delete(0, tk.END)
        try:
            items = self._rules.list_inventory(kind="draft")
        except Exception as exc:
            self.var_status.set(f"Entwürfe konnten nicht gelesen werden: {exc}")
            return
        for item in items:
            kind = str(getattr(item, "kind", "") or "")
            path = str(getattr(item, "path", "") or "").strip()
            key = str(getattr(item, "assay_key", "") or "").strip()
            name = str(getattr(item, "assay_name", "") or "").strip()
            if kind != "draft" or not path or not key:
                continue
            self._draft_choices.append({"path": path, "assay_key": key, "assay_name": name})
            self.list_drafts.insert(tk.END, f"{key}  {name}")

    def _on_draft_selected(self, _event: object = None) -> None:
        if not self._pdf_ready():
            self.var_status.set("Zuerst eine echte PDF laden. Danach kann ein Entwurf gewählt werden.")
            return
        if not self._draft_choices:
            return
        sel = self.list_drafts.curselection()
        if not sel:
            return
        choice = self._draft_choices[sel[0]]
        self.var_mode.set("existing")
        self._pending_draft_path = choice["path"]
        self.var_key.set(choice["assay_key"])
        self.var_name.set(choice["assay_name"])
        self.var_status.set(f"Entwurf gewählt: {choice['assay_key']}.")

    def _commit_target(self) -> bool:
        if not self._pdf_ready():
            self.var_status.set("Zuerst eine echte PDF laden. Ohne PDF-Text wird kein Entwurf angefasst.")
            return False
        mode = self.var_mode.get().strip()
        if mode == "new":
            return self._commit_new_draft()
        if mode == "existing":
            return self._commit_existing_draft()
        self.var_status.set("Bitte ausdrücklich neue Regel oder vorhandenen Entwurf wählen.")
        return False

    def _commit_new_draft(self) -> bool:
        key = self.var_key.get().strip()
        name = self.var_name.get().strip()
        if not key or not name:
            self.var_status.set("Assay-Schlüssel und Assay-Name sind erforderlich.")
            return False
        if self._active_key_blocks_new(key):
            return False
        outcome = self._apply_derived_assay_text()
        if outcome == "error":
            return False
        try:
            result = self._rules.create_draft_from_template_if_missing(key, name)
        except Exception as exc:
            messagebox.showerror("Entwurf", str(exc), parent=self)
            return False
        status = str(result.get("status", ""))
        if status == "exists":
            self.draft_path = None
            self.var_status.set(
                "Dieser Entwurf existiert bereits und wird nicht überschrieben. "
                "Bitte 'Vorhandenen Entwurf mit PDF prüfen/bearbeiten' wählen."
            )
            return False
        if status != "created":
            self.var_status.set("Der Entwurf konnte nicht neu angelegt werden.")
            return False
        self.draft_path = str(result.get("draft_path", "")).strip() or None
        if not self.draft_path:
            self.var_status.set("Der neue Entwurf hat keinen Pfad geliefert.")
            return False
        self.var_key.set(str(result.get("assay_key", key)))
        self.var_name.set(str(result.get("assay_name", name)))
        self._reload_fields()
        if outcome == "block":
            self.var_status.set(f"Entwurf aus der Vorlage angelegt ({len(self._fields)} Felder).")
        return True

    def _active_key_blocks_new(self, key: str) -> bool:
        try:
            items = self._rules.list_inventory(kind="active")
        except Exception as exc:
            self.draft_path = None
            self.var_status.set(f"Aktive Regeln konnten nicht geprüft werden: {exc}")
            return True
        for item in items:
            kind = str(getattr(item, "kind", "") or "")
            item_key = str(getattr(item, "assay_key", "") or "").strip()
            if kind == "active" and item_key == key:
                self.draft_path = None
                self.var_status.set(
                    "Dieser Assay-Schlüssel ist bereits als aktive Regel vorhanden. "
                    "Es wird kein Entwurf erzeugt. "
                    "Öffnen Sie die aktive Regel über die Assay-Verwaltung als Entwurf "
                    "und wählen Sie diesen anschließend ausdrücklich im Modus "
                    "'Vorhandenen Entwurf mit PDF prüfen/bearbeiten'."
                )
                return True
        return False

    def _commit_existing_draft(self) -> bool:
        path = str(self._pending_draft_path or "").strip()
        if not path:
            self.var_status.set("Bitte einen vorhandenen Entwurf ausdrücklich auswählen.")
            return False
        try:
            data = self._rules.load_draft(path)
        except Exception as exc:
            messagebox.showerror("Entwurf", str(exc), parent=self)
            return False
        key = str(data.get("assay_key", "")).strip()
        name = str(data.get("assay_name", "")).strip()
        if not key or not name:
            self.var_status.set("Der Entwurf enthält keinen gültigen Assay-Schlüssel oder Assay-Namen.")
            return False
        self.var_key.set(key)
        self.var_name.set(name)
        outcome = self._apply_derived_assay_text()
        if outcome == "error":
            return False
        self.draft_path = path
        self._reload_fields()
        return True

    def _load_existing_draft(self, draft_path: str) -> bool:
        """Liest einen ausdrücklich gewählten Entwurf, ohne ihn neu zu erzeugen."""
        self._pending_draft_path = draft_path
        self.var_mode.set("existing")
        return self._commit_existing_draft() if self._pdf_ready() else self._read_draft_identity(draft_path)

    def _read_draft_identity(self, draft_path: str) -> bool:
        try:
            data = self._rules.load_draft(draft_path)
        except Exception as exc:
            messagebox.showerror(_WINDOW_TITLE, str(exc), parent=self.master)
            return False
        key = str(data.get("assay_key", "")).strip()
        name = str(data.get("assay_name", "")).strip()
        if not key or not name:
            messagebox.showerror(
                _WINDOW_TITLE,
                "Der Entwurf enthält keinen gültigen Assay-Schlüssel oder Assay-Namen.",
                parent=self.master,
            )
            return False
        self._pending_draft_path = draft_path
        self.var_key.set(key)
        self.var_name.set(name)
        self._reload_fields_from(draft_path)
        return True

    def _ordered_configured_fields(self) -> list[dict]:
        path = self.draft_path or self._pending_draft_path
        if not path:
            return []
        data = self._rules.load_draft(path)
        fields = data.get("extract_rules", {}).get("fields", [])
        if not isinstance(fields, list):
            return []
        return [field for field in fields if isinstance(field, dict)]

    def _reload_fields_from(self, path: str) -> None:
        data = self._rules.load_draft(path)
        fields = data.get("extract_rules", {}).get("fields", [])
        self._fields = [field for field in fields if isinstance(field, dict)] if isinstance(fields, list) else []

    def _reload_fields(self) -> None:
        if not self.draft_path:
            self._fields = []
            return
        self._reload_fields_from(self.draft_path)

    def _on_pick_pdf(self) -> None:
        path = filedialog.askopenfilename(title="PDF wählen", filetypes=[("PDF", "*.pdf")], parent=self)
        if path:
            self.var_pdf.set(path)

    def _on_pick_reference_pdf(self) -> None:
        path = filedialog.askopenfilename(
            title="Referenz-PDF wählen",
            filetypes=[("PDF", "*.pdf")],
            parent=self,
        )
        if path:
            self.var_reference_pdf.set(path)

    def _on_load_text(self) -> None:
        if self._busy:
            return
        pdf = self.var_pdf.get().strip()
        if not pdf.lower().endswith(".pdf"):
            self.var_status.set("Bitte eine echte PDF-Datei wählen.")
            return
        self._pdf_request_id += 1
        request_id = self._pdf_request_id
        self._busy = True
        self.var_status.set("PDF-Text wird geladen...")
        threading.Thread(
            target=self._load_text_thread,
            args=(self._rules, pdf, request_id),
            daemon=True,
        ).start()

    def _load_text_thread(self, rules: object, pdf: str, request_id: int) -> None:
        error: str | None = None
        text = ""
        try:
            text = str(rules.load_normalized_pdf_text(pdf))
        except Exception as exc:
            error = str(exc)
        self._schedule_ui(lambda t=text, e=error, p=pdf, rid=request_id: self._finish_text_load(t, e, p, rid))

    def _schedule_ui(self, callback: Callable[[], None]) -> None:
        if getattr(self, "_closed", False):
            return
        try:
            self.after(0, callback)
        except (tk.TclError, RuntimeError):
            return

    def _finish_text_load(self, text: str, error: str | None, pdf: str, request_id: int) -> None:
        if getattr(self, "_closed", False) or request_id != self._pdf_request_id:
            return
        try:
            current = self.var_pdf.get().strip()
        except tk.TclError:
            return
        if current != pdf:
            return
        self._busy = False
        if not text.strip():
            self._invalidate_neutral_pdf()
            self.var_status.set(f"PDF-Text konnte nicht geladen werden: {error}")
            return
        self._normalized_pdf_text = text
        self._pdf_fingerprint = pdf
        self._clear_derived_assay_text()
        self._set_preview_text(text)
        self._apply_target_control_states()
        self.var_status.set(f"PDF-Text geladen ({len(text)} Zeichen). Ziel jetzt wählen.")

    def _apply_derived_assay_text(self) -> str:
        key = self.var_key.get().strip()
        name = self.var_name.get().strip()
        normalized = str(getattr(self, "_normalized_pdf_text", "") or "")
        block = ""
        if key and name and normalized.strip() and hasattr(self._rules, "derive_assay_block"):
            try:
                block = str(self._rules.derive_assay_block(normalized, key, name)).strip()
            except Exception as exc:
                self._using_fulltext_fallback = False
                self.assay_text = ""
                self._derived_for = None
                self.var_status.set(f"Assay-Abschnitt konnte nicht abgeleitet werden: {exc}")
                return "error"
        if block:
            self._using_fulltext_fallback = False
            self.assay_text = block
            self._derived_for = self._current_target_identity()
            self._set_preview_text(block)
            return "block"
        self._using_fulltext_fallback = True
        self.assay_text = normalized
        self._derived_for = self._current_target_identity()
        self._set_preview_text(normalized)
        self.var_status.set(_FULLTEXT_FALLBACK_WARNING)
        return "fulltext"

    def _all_fields_confirmed(self) -> bool:
        if not self.draft_path or not self.assay_text.strip():
            return False
        try:
            report = self._rules.locate_fields(self.draft_path, self.assay_text, group=1)
        except Exception:
            return False
        self._field_report = report
        rows = [row for row in report.get("results", []) if isinstance(row, dict)]
        self._reload_fields()
        if len(rows) != len(self._fields) or not self._fields:
            return False
        return all(self._row_has_nonempty_value(row) and not row.get("error") for row in rows)

    @staticmethod
    def _row_has_nonempty_value(row: dict) -> bool:
        if row.get("error") or not row.get("matched"):
            return False
        value = row.get("value")
        if value is None:
            return False
        return not isinstance(value, str) or bool(value.strip())

    def _show_current_field(self) -> None:
        field = self._fields[self._field_idx]
        key = str(field.get("key", ""))
        self.var_progress.set(f"Feld {self._field_idx + 1} von {len(self._fields)}: {key}")
        self.var_f_key.set(key)
        self.var_f_regex.set(str(field.get("regex", "")))
        self._apply_search_from_value(field.get("search_from"))
        self._locate_and_highlight(key)
        self._set_status("Feldschlüssel bleibt stabil. Erkennungsregel und Suchbereich prüfen, dann speichern.")

    def _apply_search_from_value(self, search_from: object) -> None:
        if isinstance(search_from, dict) and "after" in search_from:
            mode = "after"
            self.var_f_after.set(str(search_from.get("after", "")))
            self.var_f_line.set("")
        elif isinstance(search_from, dict) and "line" in search_from:
            mode = "line"
            self.var_f_line.set(str(search_from.get("line", "")))
            self.var_f_after.set("")
        else:
            mode = "none"
            self.var_f_after.set("")
            self.var_f_line.set("")
        self.var_f_mode.set(mode)
        self.var_f_search_label.set(_SEARCH_MODE_LABELS[mode])

    def _on_search_label_changed(self, *_args: object) -> None:
        mode = _SEARCH_LABEL_TO_MODE.get(self.var_f_search_label.get().strip(), "none")
        if self.var_f_mode.get() != mode:
            self.var_f_mode.set(mode)

    def _build_search_from(self) -> dict | None:
        mode = self.var_f_mode.get().strip()
        if mode == "after":
            after = self.var_f_after.get().strip()
            return {"after": after} if after else None
        if mode == "line":
            raw = self.var_f_line.get().strip()
            if not raw:
                return None
            try:
                return {"line": int(raw)}
            except ValueError:
                raise ValueError("Die Zeile muss eine ganze Zahl sein.")
        return None

    def _on_check_field(self) -> None:
        key = self.var_f_key.get().strip()
        result = self._test_current_pattern()
        if result is None:
            return
        self._show_match(key, result)

    def _save_current_field(self) -> bool:
        if not self.draft_path or not self._fields:
            self.var_status.set("Es ist kein Entwurf geladen.")
            return False
        key = self.var_f_key.get().strip()
        regex = self.var_f_regex.get().strip()
        if not regex:
            self.var_status.set("Der Regex darf nicht leer sein.")
            return False
        probed = self._test_current_pattern()
        if probed is None or not self._row_has_nonempty_value(probed):
            self.var_status.set(f"Feld {key}: kein nichtleerer Treffer. Regex oder Suchbereich anpassen.")
            return False
        try:
            search_from = self._build_search_from()
            self._rules.update_field(
                self.draft_path,
                key,
                regex=regex,
                search_from=search_from if self.var_f_mode.get() != "none" else {},
            )
        except Exception as exc:
            messagebox.showerror("Feld", str(exc), parent=self)
            return False
        self._reload_fields()
        row = self._locate_row_for_key(key)
        if row is None or not self._row_has_nonempty_value(row):
            self.var_status.set(f"Feld {key}: nach dem Speichern kein nichtleerer Treffer.")
            return False
        try:
            self._field_idx = next(
                idx for idx, field in enumerate(self._fields) if str(field.get("key", "")).strip() == key
            )
        except StopIteration:
            self.var_status.set(f"Feld {key} ist nicht mehr im Entwurf vorhanden.")
            return False
        return True

    def _test_current_pattern(self) -> dict | None:
        regex = self.var_f_regex.get().strip()
        if not regex:
            self.var_status.set("Bitte zuerst einen Regex eintragen.")
            return None
        if not self.assay_text.strip():
            self.var_status.set("Kein PDF-Text geladen.")
            return None
        try:
            search_from = self._build_search_from()
        except ValueError as exc:
            self.var_status.set(str(exc))
            return None
        try:
            result = self._rules.test_regex(
                self.assay_text,
                regex,
                group=1,
                search_from=search_from,
            )
        except Exception as exc:
            self.var_match.set(f"Prüfung fehlgeschlagen: {exc}")
            self.var_status.set(f"Prüfung fehlgeschlagen: {exc}")
            return None
        if not isinstance(result, dict):
            self.var_status.set("Die Prüfung hat kein Ergebnis geliefert.")
            return None
        return result

    def _locate_row_for_key(self, key: str) -> dict | None:
        if not self.draft_path or not self.assay_text.strip():
            return None
        try:
            report = self._rules.locate_fields(self.draft_path, self.assay_text, group=1)
        except Exception:
            return None
        self._field_report = report
        return next(
            (row for row in report.get("results", []) if isinstance(row, dict) and row.get("key") == key),
            None,
        )

    def _locate_and_highlight(self, key: str) -> None:
        self._clear_highlight()
        row = self._locate_row_for_key(key)
        if row is None:
            self.var_match.set("Feld nicht prüfbar.")
            return
        self._show_match(key, row)

    def _show_match(self, key: str, row: dict) -> None:
        self._clear_highlight()
        if row.get("error"):
            self.var_match.set(f"FEHLER: {row['error']}")
            self.var_status.set(f"Feld {key}: Regexfehler.")
            return
        if self._row_has_nonempty_value(row):
            self.var_match.set(f"TREFFER: {row.get('value')}")
            span = row.get("span")
            if isinstance(span, list) and len(span) == 2:
                self._highlight_span(int(span[0]), int(span[1]))
            self.var_status.set(f"Feld {key} hat einen nichtleeren Treffer.")
            return
        self.var_match.set("KEIN NICHTLEERER TREFFER im PDF-Text.")
        self.var_status.set(f"Feld {key}: kein nichtleerer Treffer.")

    def _clear_field_form(self) -> None:
        self.var_f_key.set("")
        self.var_f_regex.set("")
        self.var_f_mode.set("none")
        self.var_f_search_label.set(_SEARCH_MODE_LABELS["none"])
        self.var_f_after.set("")
        self.var_f_line.set("")
        self.var_match.set("")

    def _on_test_custom(self) -> None:
        key = self.var_f_key.get().strip() or "neues Feld"
        result = self._test_current_pattern()
        if result is None:
            return
        self._show_match(key, result)

    def _on_add_custom(self) -> None:
        if not self.draft_path:
            self.var_status.set("Es ist kein Entwurf geladen.")
            return
        key = self.var_f_key.get().strip()
        regex = self.var_f_regex.get().strip()
        if not key or not regex:
            self.var_status.set("Feldschlüssel und Regex sind erforderlich.")
            return
        result = self._test_current_pattern()
        if result is None or not self._row_has_nonempty_value(result):
            self.var_status.set("Feld hinzufügen ist blockiert, solange der Treffer leer ist.")
            return
        try:
            search_from = self._build_search_from()
            self._rules.add_field(self.draft_path, key, regex, required=False, search_from=search_from)
        except Exception as exc:
            messagebox.showerror("Feld", str(exc), parent=self)
            return
        self._reload_fields()
        self.var_custom_count.set(f"Aktuell {len(self._fields)} Felder im Entwurf.")
        self._clear_field_form()
        self.var_status.set(f"Feld '{key}' hinzugefügt. Das nächste eigene Feld kann jetzt angelegt werden.")

    def _authoring_mode(self) -> str:
        if not self.draft_path:
            return ""
        report = self._rules.diff_draft_vs_active(self.var_key.get().strip(), self.draft_path)
        mode = str(report.get("mode", "")).strip()
        if mode not in {"create", "update"}:
            raise RuntimeError("authoring_mode_unbekannt")
        return mode

    def _render_summary(self) -> None:
        self.list_summary.delete(0, tk.END)
        if not self.draft_path:
            return
        self._reload_fields()
        mode = ""
        try:
            mode = self._authoring_mode()
        except Exception as exc:
            self.lbl_mode_summary.config(text=f"Art der Änderung konnte nicht bestimmt werden: {exc}")
            self.frm_reference.pack_forget()
        else:
            if mode == "update":
                self.lbl_mode_summary.config(
                    text="Aktive Regel wird geändert. Problem-PDF und eine davon verschiedene Referenz-PDF sind erforderlich."
                )
                self.frm_reference.pack(fill="x", before=self.lbl_required_summary)
            else:
                self.lbl_mode_summary.config(text="Neuanlage: eine Referenz-PDF ist nicht erforderlich.")
                self.frm_reference.pack_forget()
                self.var_reference_pdf.set("")
        if getattr(self, "_using_fulltext_fallback", False):
            self.list_summary.insert(tk.END, _FULLTEXT_FALLBACK_WARNING)
        self.list_summary.insert(tk.END, f"Assay: {self.var_key.get().strip()}  {self.var_name.get().strip()}")
        self.list_summary.insert(tk.END, f"Art: {mode or '-'}")
        self.list_summary.insert(tk.END, f"Felder: {len(self._fields)}")
        self.list_summary.insert(tk.END, f"Entwurf: {self.draft_path}")
        if self.assay_text.strip():
            try:
                report = self._rules.locate_fields(self.draft_path, self.assay_text, group=1)
                self._field_report = report
                rows = [row for row in report.get("results", []) if isinstance(row, dict)]
                confirmed = sum(1 for row in rows if self._row_has_nonempty_value(row))
                complete = len(rows) == len(self._fields) and confirmed == len(self._fields) and bool(self._fields)
                self.lbl_required_summary.config(
                    text=(
                        f"Felder: {confirmed}/{len(self._fields)} mit nichtleerem Treffer. "
                        + (
                            "Alle konfigurierten Felder sind getroffen."
                            if complete
                            else "Abschluss erst möglich, wenn jedes Feld einen nichtleeren Treffer hat."
                        )
                    ),
                    fg="#2f6b2f" if complete else "#9a6700",
                )
                for row in rows:
                    label = "Treffer" if self._row_has_nonempty_value(row) else "Kein nichtleerer Treffer"
                    self.list_summary.insert(tk.END, f"  Feld {row.get('key')}: {label}")
            except Exception as exc:
                self.lbl_required_summary.config(text=f"Feldprüfung fehlgeschlagen: {exc}", fg="#a33")
        try:
            structure = self._rules.validate_draft(self.draft_path)
        except Exception as exc:
            self.list_summary.insert(tk.END, f"Strukturprüfung fehlgeschlagen: {exc}")
            return
        if structure.get("ok"):
            self.list_summary.insert(tk.END, "Strukturprüfung: in Ordnung")
        else:
            self.list_summary.insert(tk.END, f"Strukturprüfung: {len(structure.get('errors', []))} Fehler")
            for err in structure.get("errors", []):
                self.list_summary.insert(tk.END, f"  - {err}")

    def _same_pdf(self, left: str, right: str) -> bool:
        if not left or not right:
            return False
        return os.path.normcase(os.path.abspath(left)) == os.path.normcase(os.path.abspath(right))

    def _finish(self) -> None:
        if not self.draft_path:
            return
        pdf_path = self.var_pdf.get().strip()
        if not self._pdf_ready():
            messagebox.showwarning(
                "PDF fehlt",
                "Der Abschluss braucht eine erfolgreich geladene PDF.",
                parent=self,
            )
            return
        if not self._all_fields_confirmed():
            messagebox.showwarning(
                "Felder unvollständig",
                "Der Abschluss ist blockiert, solange nicht jedes konfigurierte Feld "
                "einen nichtleeren Treffer im PDF-Text hat.",
                parent=self,
            )
            return
        try:
            structure = self._rules.validate_draft(self.draft_path)
        except Exception as exc:
            messagebox.showerror("Strukturprüfung", str(exc), parent=self)
            return
        if not structure.get("ok"):
            messagebox.showwarning(
                "Strukturprüfung",
                "Der Abschluss ist blockiert, solange die Strukturprüfung Fehler meldet.",
                parent=self,
            )
            return
        try:
            mode = self._authoring_mode()
        except Exception as exc:
            messagebox.showerror("Art der Änderung", str(exc), parent=self)
            return
        reference_pdf = self.var_reference_pdf.get().strip()
        if mode == "update":
            if not reference_pdf.lower().endswith(".pdf"):
                messagebox.showwarning(
                    "Referenz-PDF fehlt",
                "Bei einer Änderung der aktiven Regel fehlt die Referenz-PDF. "
                "Es ist eine zweite, andere PDF nötig, mit der die bisherige Regel funktioniert hat.",
                    parent=self,
                )
                return
            if self._same_pdf(pdf_path, reference_pdf):
                messagebox.showwarning(
                    "Referenz-PDF",
                    "Die Referenz-PDF muss eine andere Datei sein als die Problem-PDF.",
                    parent=self,
                )
                return
        try:
            self._rules.create_authoring_proof(
                self.var_key.get().strip(),
                self.draft_path,
                pdf_path,
                reference_pdf if mode == "update" else None,
            )
        except Exception as exc:
            message = "Der Entwurf hat die PDF-Prüfung nicht bestanden:\n" f"{exc}"
            if getattr(self, "_using_fulltext_fallback", False):
                message += (
                    "\n\nAssay-Name, Assay-Schlüssel oder die Blocktrennung müssen korrigiert werden. "
                    "Der vollständige PDF-Text ist nur eine Authoring-Hilfe; der Nachweis ist nicht erfolgreich."
                )
                self.var_status.set(
                    "Nachweis fehlgeschlagen. Assay-Name, Assay-Schlüssel oder die Blocktrennung korrigieren. "
                    "Kein erfolgreicher Abschluss."
                )
            messagebox.showerror("Nachweis fehlgeschlagen", message, parent=self)
            return
        action = self.var_finish_action.get()
        self._shutdown("activate" if action == "activate" else "editor")

    def _set_preview_text(self, text: str) -> None:
        if not hasattr(self, "txt_preview"):
            return
        self.txt_preview.configure(state="normal")
        self.txt_preview.delete("1.0", tk.END)
        self.txt_preview.insert(tk.END, text)
        self._set_preview_editable(False)
        self.txt_preview.see("1.0")

    def _set_preview_editable(self, editable: bool) -> None:
        self.txt_preview.configure(state="normal")
        self.txt_preview.unbind("<Key>")
        if editable:
            self.txt_preview.bind("<Key>", lambda _event: "break")
        else:
            self.txt_preview.configure(state="disabled")

    def _clear_highlight(self) -> None:
        if hasattr(self, "txt_preview"):
            self.txt_preview.tag_remove("hit", "1.0", tk.END)

    def _highlight_span(self, start: int, end: int) -> None:
        start_idx = f"1.0+{start}c"
        end_idx = f"1.0+{end}c"
        self.txt_preview.tag_add("hit", start_idx, end_idx)
        self.txt_preview.see(start_idx)
