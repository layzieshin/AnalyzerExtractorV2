"""ReleaseMixin: Speichern, Validieren, Diff, Preview und kontrollierte Aktivierung."""
from __future__ import annotations

import tkinter as tk
import os
from tkinter import messagebox

from .report_panel import clear_authoring_result, render_authoring_result


class ReleaseMixin:
    def _show_rule_results(self, *, reveal=True, toggle=False):
        frame = getattr(self, "authoring_values_frame", None)
        if frame is None:
            self.report_notebook.select(self.authoring_result_tab)
        elif not reveal or (toggle and frame.winfo_manager()):
            frame.pack_forget()
        else:
            frame.pack(fill="both", expand=True)
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
            if save:
                self._save_meta_to_draft(push_undo=False)
            report = self._rules.validate_draft(self.current_draft_path or "")
        except Exception as e:
            self._set_hint(f"{phase}: Speichern oder Strukturprüfung fehlgeschlagen")
            messagebox.showerror("Fehler", str(e))
            return False

        self._render_validation_report(report)
        if report.get("ok"):
            return True

        if not messagebox.askyesno(
            "Strukturprüfung",
            f"{phase}: Der Entwurf ist strukturell nicht in Ordnung ({len(report.get('errors', []))} Fehler). Trotzdem fortfahren?",
        ):
            return False
        return True

    def _check_authoring_readiness_for_activate(self) -> bool:
        if not self.current_draft_path:
            return False
        assay_key = self.var_new_assay_key.get().strip()
        try:
            report = self._rules.verify_authoring_proof(assay_key, self.current_draft_path)
        except Exception as e:
            messagebox.showerror("Readiness", str(e))
            return False

        if report.get("ok"):
            return True
        errors = ", ".join(str(item) for item in report.get("errors", [])) or "Nachweis fehlt"
        messagebox.showerror(
            "Aktivierung blockiert",
            "Der Aktivierungsnachweis fehlt oder ist nicht mehr aktuell.\n\n"
            f"Details: {errors}\n\n"
            "Bitte 'Extraktion testen' mit der gewählten Test-PDF erneut ausführen.",
            parent=self._dialog_parent(),
        )
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

        try:
            metadata = self._draft_meta_inputs() if self._dirty else None
        except Exception as exc:
            self._invalidate_authoring_test()
            messagebox.showerror("Speichern", str(exc), parent=self._dialog_parent())
            return
        target = self._authoring_target()
        self.request_authoring_test(target, origin=self, is_current=lambda: self._authoring_target() == target,
                                    metadata=metadata)

    def _authoring_target(self) -> tuple[str, str, str]:
        return str(self.current_draft_path or ""), self.var_new_assay_key.get().strip(), self.var_pdf.get().strip()

    def _invalidate_authoring_test(self, *_args, origin=None) -> None:
        if origin is not None and origin is not getattr(self, "_proof_origin", None):
            return
        self._proof_generation = getattr(self, "_proof_generation", 0) + 1
        self._proof_request = None
        self._proof_result = None
        self._proof_target = None
        self._proof_origin = None
        self._completion_visible = False
        if hasattr(self, "tree_authoring_values"):
            clear_authoring_result(self, "Auswahl oder Entwurf geändert – bitte Extraktion testen")
        self._sync_authoring_controls()

    def _sync_authoring_controls(self) -> None:
        for name in ("btn_inventory_discard", "btn_draft_discard"):
            button = getattr(self, name, None)
            if button is not None:
                button.configure(state="disabled" if self._busy or (name == "btn_draft_discard" and not self.current_draft_path) else "normal")
        if hasattr(self, "editor_action_flow"):
            for button in self.editor_action_flow._controls:
                button.configure(state="disabled" if self._busy else "normal")
            self.btn_rule_undo.configure(state="normal" if self._undo_stack and not self._busy else "disabled")
            self.btn_rule_redo.configure(state="normal" if self._redo_stack and not self._busy else "disabled")
            self.btn_inventory_new.configure(state="disabled" if self._busy else "normal")
            self._update_field_commit_button()
        if hasattr(self, "btn_rule_test"):
            target = self._authoring_target()
            self.btn_rule_test.configure(state="normal" if all(target) and not self._busy else "disabled")
        if hasattr(self, "btn_activate"):
            self.btn_activate.configure(state="normal" if self.authoring_target_ready(self._authoring_target(), origin=self) else "disabled")
            if hasattr(self, "editor_footer_flow"):
                visible = bool(getattr(self, "_completion_visible", False))
                self.editor_footer_flow.set_visible(self.btn_activate, visible)
                self.btn_completion.configure(style="RuleSuite.Secondary.TButton" if visible else "RuleSuite.Primary.TButton")

    def authoring_target_ready(self, target, *, origin=None) -> bool:
        result = getattr(self, "_proof_result", None)
        if self._busy or not result or result.get("status") != "ready" or target != getattr(self, "_proof_target", None):
            return False
        if origin is not None and origin is not getattr(self, "_proof_origin", None):
            return False
        # Readiness is cached presentation state. External byte/source changes
        # are checked in the worker and again in the core's activation lock.
        return True

    def request_authoring_test(self, target, *, origin, is_current, on_complete=None, metadata=None) -> bool:
        if self._busy or self._task_runner.is_active("editor-rule-test"):
            return False
        self._invalidate_authoring_test()
        self._proof_target, self._proof_origin = target, origin
        rules, context = self._rules, self._context_generation
        request = (self._proof_generation, context, target, origin)
        self._proof_request = request
        self._set_busy(True, "Regeltest läuft …")
        if origin is self:
            clear_authoring_result(self, "Regeltest läuft …")
            self._show_rule_results()

        def finish(result=None, error=None):
            if self._closed:
                return
            self._set_busy(False, "Bereit")
            current = request == self._proof_request and rules is self._rules and context == self._context_generation and is_current()
            if request == self._proof_request:
                self._proof_request = None
            if current and error is None:
                self._proof_result = result
                if metadata is not None:
                    self._dirty = False
                if origin is self:
                    render_authoring_result(self, result)
                self._set_hint("Regeltest abgeschlossen. Aktivierung erfolgt nur ausdrücklich." if result.get("status") == "ready" else "Regeltest fehlgeschlagen. Bitte die markierten Felder nacharbeiten.")
            elif current:
                self._proof_result = None
                self._set_hint(f"Regeltest fehlgeschlagen: {error}")
                if origin is self:
                    clear_authoring_result(self, "Regeltest fehlgeschlagen")
            if on_complete is not None:
                on_complete(result if current and error is None else None)
            self._sync_authoring_controls()

        draft, key, pdf = target
        def work():
            if metadata is not None:
                rules.update_draft_meta(draft, **metadata)
            return rules.create_authoring_proof(key, draft, pdf)

        accepted = self._task_runner.submit("editor-rule-test", work,
            on_success=lambda result: finish(result=result), on_error=lambda error: finish(error=error))
        if not accepted:
            self._set_busy(False, "Bereit")
            self._invalidate_authoring_test()
        return accepted

    def _capture_authoring_completion(self, draft):
        target = getattr(self, "_proof_target", None)
        if target is not None and os.path.normcase(os.path.abspath(target[0])) == os.path.normcase(os.path.abspath(draft)) and self.authoring_target_ready(target):
            return target, self._proof_result
        return None

    def _adopt_authoring_completion(self, completion) -> None:
        if completion is None:
            return
        target, result = completion
        self.var_pdf.set(target[2])
        if self._authoring_target() != target:
            return
        self._proof_target, self._proof_result, self._proof_origin = target, result, self
        self._completion_visible = True
        render_authoring_result(self, result)
        self._show_rule_results()
        self._sync_authoring_controls()

    def on_activate(self) -> None:
        if self._busy:
            self._set_hint("Eine Prüfung läuft bereits. Bitte kurz warten.")
            return
        if not self.authoring_target_ready(self._authoring_target(), origin=self):
            self._invalidate_authoring_test()
            self._set_hint("Bitte zuerst die gewählte Test-PDF mit 'Extraktion testen' prüfen.")
            return
        # Activation never resolves a dirty form by writing it first. The
        # explicit test action is the only route back to a fresh proof.
        key = self.var_new_assay_key.get().strip()
        name = self.var_new_assay_name.get().strip()
        if not key or not name:
            self._set_hint("Assay-Schlüssel und Assay-Name sind erforderlich.")
            return

        if self._dirty or self._field_form_dirty:
            self._invalidate_authoring_test()
            self._set_hint("Entwurf geändert – bitte Extraktion testen.")
            return
        target, rules, context = self._authoring_target(), self._rules, self._context_generation
        generation = self._proof_generation
        tested_identity = tuple(self._proof_result.get(field) for field in ("attempt_id", "proof_sha256"))
        self._set_busy(True, "Aktivierung wird geprüft …")

        def current():
            return (not self._closed and rules is self._rules and context == self._context_generation
                    and generation == self._proof_generation and target == self._authoring_target())

        def failed(error):
            if not self._closed:
                self._activation_pending = False
                self._set_busy(False, "Bereit")
                if current():
                    self._invalidate_authoring_test()
                    messagebox.showerror("Aktivierung blockiert", str(error) + "\nBitte Extraktion testen.", parent=self._dialog_parent())

        def prepare():
            proof = rules.verify_authoring_proof(key, target[0])
            if not proof.get("ok"):
                raise RuntimeError(", ".join(proof.get("errors", ())) or "Nachweis fehlt")
            receipt = proof.get("proof", {})
            if tuple(receipt.get(field) for field in ("attempt_id", "proof_sha256")) != tested_identity:
                raise RuntimeError("authoring_proof_attempt_changed")
            diff = rules.diff_draft_vs_active(key, target[0])
            if receipt.get("version") == 2 and diff.get("mode") != receipt.get("activation_baseline", {}).get("mode"):
                raise RuntimeError("authoring_proof_active_mapping_changed")
            return diff, receipt

        def prepared(preparation):
            diff, receipt = preparation
            self._set_busy(False, "Bereit")
            if not current():
                return
            action = "Bestehende Regel aktualisieren" if diff.get("mode") == "update" else "Neue Regel aktivieren"
            case_context = getattr(self, "_identity_case_context", None)
            case_bound = bool(case_context and case_context.get("assay_key") == key and case_context.get("draft_path") == target[0])
            follow_up = ("\n\nDanach werden ausschließlich die betroffenen PDF-Importaufträge dieses Kennungsfalls erneut verarbeitet. "
                         "Fehlende oder weiterhin fehlerhafte Quellen bleiben unter Änderungen offen.") if case_bound else ""
            if not messagebox.askyesno("Aktivierung bestätigen",
                    f"{action}?\n\nAssay: {name}\nSchlüssel: {key}\nÄnderungen: {len(diff.get('changes', ())) }{follow_up}",
                    parent=self._dialog_parent()) or not current():
                return
            self._activation_pending = True
            self._set_busy(True, "Regel wird aktiviert …")

            def activated(path):
                if self._closed:
                    return
                self._activation_pending = False
                self._set_busy(False, "Bereit")
                self._reload_assays()
                if current():
                    self._log(f"Aktiviert: {path}")
                    self._invalidate_authoring_test()
                    self._set_hint("Aktivierung abgeschlossen.")
                    callback = getattr(self, "_identity_activation_callback", None)
                    if case_bound and callable(callback) and case_context == getattr(self, "_identity_case_context", None):
                        callback(case_context)

            if not self._task_runner.submit("editor-activate", lambda: rules.activate_draft(key, target[0], assay_name=name,
                                            authoring_proof=receipt, expected_mode=diff.get("mode")),
                                            on_success=activated, on_error=failed):
                failed(RuntimeError("Aktivierung konnte nicht gestartet werden."))

        if not self._task_runner.submit("editor-activate-check", prepare, on_success=prepared, on_error=failed):
            failed(RuntimeError("Aktivierungsprüfung konnte nicht gestartet werden."))
