"""ReleaseMixin: Speichern, Validieren, Diff, Preview und kontrollierte Aktivierung."""
from __future__ import annotations

import json
import threading
import tkinter as tk
from tkinter import messagebox, filedialog
from pathlib import Path


class ReleaseMixin:
    def _clear_validation_list(self) -> None:
        self.list_validation.delete(0, tk.END)

    def _render_validation_report(self, report: dict) -> None:
        self._clear_validation_list()
        if report.get("ok"):
            self.list_validation.insert(tk.END, "OK: Entwurf ist strukturell in Ordnung")
            self._set_hint("Strukturprüfung erfolgreich.")
            return

        for err in report.get("errors", []):
            self.list_validation.insert(tk.END, f"- {err}")
        self._set_hint(f"Strukturprüfung fehlgeschlagen ({len(report.get('errors', []))} Fehler).")

    def _quick_validate(self, phase: str, *, save: bool = True) -> bool:
        try:
            if save and self.__dict__.get("_dirty", False):
                self._save_meta_to_draft(push_undo=False)
            report = self._rules.validate_draft(self.current_draft_path or "")
        except Exception as e:
            self._set_hint(f"{phase}: Speichern oder Strukturprüfung fehlgeschlagen")
            messagebox.showerror("Fehler", str(e))
            return False

        self._render_validation_report(report)
        if report.get("ok"):
            return True

        if phase == "Aktivierung":
            messagebox.showerror("Aktivierung blockiert", "Die Strukturprüfung muss ohne Fehler bestehen.")
            return False
        if not messagebox.askyesno(
            "Strukturprüfung",
            f"{phase}: Der Entwurf ist strukturell nicht in Ordnung ({len(report.get('errors', []))} Fehler). Trotzdem fortfahren?",
        ):
            return False
        return True

    def _proof_set(self, name, value):
        variable = self.__dict__.get(name)
        if variable is not None:
            variable.set(value)

    @staticmethod
    def _proof_path_text(value):
        return str(Path(value).resolve()) if str(value or "").strip() else ""

    def _authoring_ui_context(self):
        def value(name):
            variable = self.__dict__.get(name)
            return str(variable.get()).strip() if variable is not None else ""
        rules = self.__dict__.get("_rules")
        return (id(rules), str(getattr(rules, "project_root", self.__dict__.get("project_root", ""))),
            self._proof_path_text(self.__dict__.get("current_draft_path")), value("var_new_assay_key"),
            value("var_new_assay_name"), self._proof_path_text(value("var_pdf")), self._proof_path_text(value("var_reference_pdf")))

    def _proof_matches_selection(self, proof):
        context = self._authoring_ui_context()
        return (context[2] == self._proof_path_text(proof.get("draft_path")) and context[3] == proof.get("assay_key")
            and context[4] == str(proof.get("assay_name") or "").strip() and context[5] == self._proof_path_text(proof.get("failing_pdf_path"))
            and (proof.get("mode") != "update" or context[6] == self._proof_path_text(proof.get("reference_pdf_path"))))

    def _invalidate_authoring_proof(self, *_args):
        if self.__dict__.get("_suspend_proof_tracking", False):
            return
        self._proof_generation = self.__dict__.get("_proof_generation", 0) + 1
        self._proof_needs_recheck = True
        self._proof_set("var_proof_status", "Änderungen – erneut mit PDFs prüfen.")
        button = self.__dict__.get("btn_activate")
        if button is not None:
            button.configure(state="disabled")

    def _on_proof_pdf_changed(self, *_args):
        self._invalidate_authoring_proof()

    def _proof_result_text(self, value):
        widget = self.__dict__.get("txt_proof_result")
        if widget is not None:
            widget.configure(state="normal")
            widget.delete("1.0", tk.END)
            widget.insert("1.0", value)
            widget.configure(state="disabled")

    @staticmethod
    def _proof_failure_message(error):
        explanations = (("reference_pdf_required", "Bei einer Änderung ist eine andere Referenz-PDF erforderlich."),
            ("reference_pdf_missing", "Die ausgewählte Referenz-PDF fehlt oder ist nicht lesbar."),
            ("reference_must_differ", "Problem- und Referenz-PDF müssen unterschiedliche Dateien mit unterschiedlichem Inhalt sein."),
            ("reference_mismatch", "Der Referenzvergleich ist fehlgeschlagen: bisherige Feldwerte oder Kit-Charge unterscheiden sich."),
            ("configured_fields_empty", "Die Extraktion ist unvollständig: jedes konfigurierte Feld braucht einen nichtleeren Wert."),
            ("inputs_changed", "Entwurf, PDF oder aktive Regel wurden während der Prüfung verändert. Bitte erneut prüfen."))
        prefix = next((message for key, message in explanations if key in str(error)), "Der PDF-Nachweis ist nicht verwendbar. Bitte den Sperrgrund klären.")
        return prefix + "\nDetails: " + str(error)

    def _refresh_authoring_status(self, *, adopt_paths=False):
        button = self.__dict__.get("btn_activate")
        if button is not None:
            button.configure(state="disabled")
        if not self.__dict__.get("current_draft_path"):
            self._proof_set("var_proof_status", "Nachweis fehlt – zuerst einen Entwurf laden.")
            return False
        try:
            report = self._rules.verify_authoring_proof(self.var_new_assay_key.get().strip(), self.current_draft_path)
        except Exception as exc:
            report = {"ok": False, "errors": [str(exc)]}
        proof = report.get("proof") or {}
        identity = self._authoring_ui_context()[:5]
        if adopt_paths and identity != self.__dict__.get("_proof_loaded_identity"):
            self._proof_loaded_identity = identity
            self._suspend_proof_tracking = True
            try:
                if proof.get("failing_pdf_path"):
                    self.var_pdf.set(proof["failing_pdf_path"])
                reference = self.__dict__.get("var_reference_pdf")
                if reference is not None:
                    reference.set(proof.get("reference_pdf_path", ""))
            finally:
                self._suspend_proof_tracking = False
            self._proof_needs_recheck = False
        try:
            structure = self._rules.validate_draft(self.current_draft_path)
            self._proof_set("var_proof_structure", "Struktur: bestanden" if structure.get("ok") else "Struktur: Fehler")
            mode = self._rules.diff_draft_vs_active(self.var_new_assay_key.get().strip(), self.current_draft_path).get("mode")
        except Exception:
            structure, mode = {"ok": False}, None
        dirty = self.__dict__.get("_dirty", False) or self.__dict__.get("_field_form_dirty", False)
        current = bool(report.get("ok") and structure.get("ok") and not dirty
            and not self.__dict__.get("_proof_needs_recheck", False) and self._proof_matches_selection(proof))
        if self.__dict__.get("_proof_running", False):
            status = "Prüfung läuft – es wird nichts aktiviert."
        elif current:
            status = "Prüfung erfolgreich – noch nicht aktiviert."
        elif proof.get("status") == "failed":
            status = "Vorige PDF-Prüfung fehlgeschlagen – aktuell mit PDFs prüfen."
        elif dirty or self.__dict__.get("_proof_needs_recheck", False) or report.get("ok"):
            status = "Änderungen – erneut mit PDFs prüfen."
        else:
            status = "Nachweis fehlt oder ist nicht mehr aktuell – mit PDFs prüfen."
        self._proof_set("var_proof_status", status)
        self._proof_set("var_proof_example", "Beispiel/Problem: bestanden" if current else "Beispiel/Problem: nicht aktuell")
        self._proof_set("var_proof_reference", "Referenz: nicht erforderlich (Neuanlage)" if mode == "create" else
            ("Referenz: Vergleich bestanden" if current else "Referenz: andere PDF erforderlich / erneut prüfen"))
        if self.__dict__.get("_proof_running", False):
            self._proof_set("var_proof_example", "Beispiel/Problem: Prüfung läuft")
            if mode == "update":
                self._proof_set("var_proof_reference", "Referenz: Prüfung läuft")
        if current:
            detail = f"Geprüft: {proof.get('checked_at_utc', '')} · Beispiel: {Path(proof['failing_pdf_path']).name}"
            if proof.get("reference_pdf_path"):
                detail += f" · Referenz: {Path(proof['reference_pdf_path']).name}"
            detail += "\nGeprüfte Felder: " + ", ".join(proof.get("failing_result_fields", []))
            detail += "\nReferenzvergleich: " + (", ".join([*proof.get("compared_fields", []), "lot_id"]) if mode == "update" else "nicht erforderlich")
        else:
            detail = self._proof_failure_message(proof["error"]) if proof.get("error") else (
                "; ".join(report.get("errors", [])) or "Prüfung mit der aktuellen PDF-Auswahl erforderlich.")
        self._proof_result_text(detail)
        if button is not None:
            button.configure(state="normal" if current and not self.__dict__.get("_proof_running", False) else "disabled")
        return current and not self.__dict__.get("_proof_running", False)

    def on_pick_reference_pdf(self):
        path = filedialog.askopenfilename(title="Andere Referenz-PDF auswählen", filetypes=[("PDF", "*.pdf")])
        if path:
            self.var_reference_pdf.set(path)

    def on_check_pdfs(self):
        if self.__dict__.get("_busy", False) or self.__dict__.get("_proof_running", False) or not self._guard_field_form():
            return
        if not self.current_draft_path:
            self._set_hint("Bitte zuerst einen Entwurf laden.")
            return
        try:
            if self.__dict__.get("_dirty", False):
                self._save_meta_to_draft(push_undo=False)
        except Exception as exc:
            self._invalidate_authoring_proof()
            messagebox.showerror("Entwurf speichern", str(exc))
            return
        self._proof_generation = self.__dict__.get("_proof_generation", 0) + 1
        generation, context, rules = self._proof_generation, self._authoring_ui_context(), self._rules
        self._proof_active_request = generation
        self._proof_running = True
        self._set_busy(True, "PDF-Nachweis läuft …")
        self._refresh_authoring_status()
        def work():
            return rules.create_authoring_proof(context[3], context[2], context[5], context[6] or None)
        # Only the existing main-thread poller talks to Tk. A worker-side
        # after() call can fail or lose delivery after Tcl/mainloop changes.
        submitted = self._proof_task_runner.submit(f"rule-authoring-proof-{generation}", work,
            on_success=lambda result: self._complete_authoring_check(generation, context, result, None),
            on_error=lambda error: self._complete_authoring_check(generation, context, None, str(error)))
        if not submitted:
            self._complete_authoring_check(generation, context, None, "Die PDF-Prüfung konnte nicht gestartet werden. Bitte erneut versuchen.")

    def _complete_authoring_check(self, generation, context, result, error):
        if self.__dict__.get("_proof_disposed", False) or generation != self.__dict__.get("_proof_active_request"):
            return
        self._proof_active_request = None
        self._proof_running = False
        self._set_busy(False, "Bereit")
        if generation != self._proof_generation or context != self._authoring_ui_context():
            self._refresh_authoring_status()
            return
        if error:
            self._proof_needs_recheck = True
            self._proof_set("var_proof_status", "PDF-Prüfung fehlgeschlagen – keine Aktivierung.")
            try:
                mode = self._rules.diff_draft_vs_active(self.var_new_assay_key.get().strip(), self.current_draft_path).get("mode")
                structural = self._rules.validate_draft(self.current_draft_path)
            except Exception:
                mode, structural = None, {"ok": False}
            self._proof_set("var_proof_structure", "Struktur: bestanden" if structural.get("ok") else "Struktur: Fehler")
            example_state = "bestanden" if "reference_mismatch" in error else ("nicht geprüft" if "reference_" in error else "nicht aktuell")
            self._proof_set("var_proof_example", "Beispiel/Problem: " + example_state)
            self._proof_set("var_proof_reference", "Referenz: nicht erforderlich (Neuanlage)" if mode == "create" else
                ("Referenz: blockiert / Vergleich fehlgeschlagen" if "reference_" in error else "Referenz: nicht aktuell / erneut prüfen"))
            self._proof_result_text(self._proof_failure_message(error))
            button = self.__dict__.get("btn_activate")
            if button is not None:
                button.configure(state="disabled")
            return
        self._proof_needs_recheck = False
        self._refresh_authoring_status()

    def _check_authoring_readiness_for_activate(self) -> bool:
        if not self.current_draft_path:
            return False
        try:
            report = self._rules.verify_authoring_proof(self.var_new_assay_key.get().strip(), self.current_draft_path)
        except Exception as exc:
            report = {"ok": False, "errors": [str(exc)]}
        dirty = self.__dict__.get("_dirty", False) or self.__dict__.get("_field_form_dirty", False)
        if (report.get("ok") and not dirty and not self.__dict__.get("_proof_running", False)
                and not self.__dict__.get("_proof_needs_recheck", False) and self._proof_matches_selection(report.get("proof") or {})):
            return True
        errors = ", ".join(report.get("errors", [])) or "PDF-Auswahl oder ungespeicherte Änderungen passen nicht zum Nachweis"
        messagebox.showerror("Aktivierung blockiert", "Der Nachweis fehlt oder ist nicht aktuell. Bitte 'Mit PDFs prüfen' ausführen.\n\n" + errors)
        return False

    def _guard_field_form(self) -> bool:
        guard = getattr(self, "_resolve_dirty_field_form", None)
        if not callable(guard):
            return True
        return bool(guard())

    def on_save_all(self) -> None:
        if not self._guard_field_form():
            return
        if not self.current_draft_path:
            self._set_hint("Bitte zuerst einen Entwurf laden.")
            return
        try:
            self._save_meta_to_draft(push_undo=True)
            self.on_load_draft_into_editor()
            self._log("Entwurf gespeichert.")
            self._set_hint("Entwurf gespeichert.")
        except Exception as e:
            messagebox.showerror("Fehler", str(e))

    def on_validate(self) -> None:
        if not self._guard_field_form():
            return
        if not self.current_draft_path:
            self._set_hint("Bitte zuerst einen Entwurf laden.")
            return
        try:
            if self.__dict__.get("_dirty", False):
                self._save_meta_to_draft(push_undo=True)
            report = self._rules.validate_draft(self.current_draft_path)
            self._render_validation_report(report)
            self._log("=== Strukturprüfung ===")
            if report.get("ok"):
                self._log("OK: Entwurf ist strukturell in Ordnung")
                messagebox.showinfo("Strukturprüfung", "Der Entwurf ist strukturell in Ordnung.")
            else:
                for err in report.get("errors", []):
                    self._log(f"- {err}")
                messagebox.showwarning("Strukturprüfung", "Der Entwurf ist strukturell nicht in Ordnung. Details in der Liste und im Protokoll.")
        except Exception as e:
            messagebox.showerror("Fehler", str(e))

    def on_show_diff(self) -> None:
        if not self._guard_field_form():
            return
        if not self.current_draft_path:
            self._set_hint("Bitte zuerst einen Entwurf laden.")
            return
        key = self.var_new_assay_key.get().strip()
        if not key:
            self._set_hint("Assay-Schlüssel ist erforderlich.")
            return
        try:
            if self.__dict__.get("_dirty", False):
                self._save_meta_to_draft(push_undo=False)
            diff = self._rules.diff_draft_vs_active(key, self.current_draft_path)
            self._log(f"[DIFF] mode={diff.get('mode')} ruleset={diff.get('ruleset_file')}")
            changes = diff.get("changes", [])
            if not changes:
                self._log("[DIFF] Keine Unterschiede")
            else:
                for ch in changes[:80]:
                    self._log(f"  - {ch.get('path')}: active={ch.get('active')} -> draft={ch.get('draft')}")
                if len(changes) > 80:
                    self._log(f"  ... {len(changes) - 80} weitere Änderungen")
            show_details = getattr(self, "_show_advanced", None)
            if callable(show_details):
                show_details("log")
            self._set_hint(f"Änderungen angezeigt ({len(changes)} Änderungen).")
        except Exception as e:
            messagebox.showerror("Fehler", str(e))

    def on_preview(self) -> None:
        if not self._guard_field_form():
            return
        if self._busy:
            return
        if not self.current_draft_path:
            self._set_hint("Bitte zuerst einen Entwurf laden.")
            return
        pdf = self.var_pdf.get().strip()
        key = self.var_new_assay_key.get().strip()
        if not pdf or not key:
            self._set_hint("Test-PDF und Assay-Schlüssel sind erforderlich.")
            return

        if not self._quick_validate("Extraktionstest"):
            return

        self._set_busy(True, "Extraktionstest läuft …")
        rules = self._rules
        draft_path = self.current_draft_path
        threading.Thread(
            target=self._preview_thread,
            args=(rules, pdf, key, draft_path),
            daemon=True,
        ).start()

    def _preview_thread(self, rules: object, pdf: str, key: str, draft_path: str | None) -> None:
        try:
            out = rules.preview_extract(pdf, key, draft_path=draft_path)
            payload = json.dumps(out, ensure_ascii=False, indent=2)
            self.after(0, lambda p=payload: self._finish_preview_success(p))
        except Exception as e:
            msg = str(e)
            self.after(0, lambda m=msg: self._finish_preview_error(m))

    def _finish_preview_success(self, payload: str) -> None:
        try:
            self._log("=== Extraktionstest ===")
            self._log(payload)
            self._set_hint("Extraktionstest erfolgreich.")
        finally:
            self._set_busy(False, "Bereit")

    def _finish_preview_error(self, msg: str) -> None:
        try:
            self._log(f"[ERROR] preview: {msg}")
            self._set_hint("Extraktionstest fehlgeschlagen. Siehe Protokoll.")
        finally:
            self._set_busy(False, "Bereit")

    def on_activate(self) -> None:
        if self.__dict__.get("_busy", False) or not self._guard_field_form():
            return
        if not self.current_draft_path:
            self._set_hint("Bitte zuerst einen Entwurf laden.")
            return
        if self.__dict__.get("_dirty", False) or self.__dict__.get("_field_form_dirty", False):
            self._invalidate_authoring_proof()
            messagebox.showerror("Aktivierung blockiert", "Ungespeicherte Änderungen: zuerst mit PDFs prüfen.")
            return

        key = self.var_new_assay_key.get().strip()
        name = self.var_new_assay_name.get().strip()
        if not key or not name:
            self._set_hint("Assay-Schlüssel und Assay-Name sind erforderlich.")
            return

        # A clean, proven draft is inspected without serialization. Dirty UI
        # state needs an explicit new PDF check before final confirmation.
        if not self._quick_validate("Aktivierung", save=False):
            return

        if not self._check_authoring_readiness_for_activate():
            return

        diff = self._rules.diff_draft_vs_active(key, self.current_draft_path)
        mode = diff.get("mode")
        if mode not in {"create", "update"}:
            messagebox.showerror("Aktivierung blockiert", "Der aktuelle Aktivierungsmodus ist nicht eindeutig.")
            return
        change_count = len(diff.get("changes", []))
        action_text = (
            f"Bestehendes Assay {key} wird überschrieben.\n\n"
            if mode == "update"
            else f"Neues Assay {key} wird angelegt und in index.json eingetragen.\n\n"
        )
        confirm = (
            action_text
            + f"Fortfahren?\nName: {name}\nÄnderungen: {change_count}\n\n"
            + "Hinweis: 'Änderungen anzeigen' zeigt die Unterschiede vorab."
        )
        if not messagebox.askyesno("Aktivierung bestätigen", confirm):
            return

        try:
            if mode == "update":
                path = self._rules.activate_draft(key, self.current_draft_path)
                self._log(f"Aktualisiert: {path}")
            else:
                path = self._rules.activate_new_draft(key, name, self.current_draft_path)
                self._log(f"Neues Assay aktiviert: {path}")
            self._set_hint("Aktivierung abgeschlossen.")
            self._proof_set("var_proof_status", "Aktivierung abgeschlossen. Änderungen benötigen eine neue PDF-Prüfung.")
            self._proof_needs_recheck = True
            if self.__dict__.get("btn_activate") is not None:
                self.btn_activate.configure(state="disabled")
            self._reload_assays()
        except Exception as e:
            messagebox.showerror("Fehler", str(e))
