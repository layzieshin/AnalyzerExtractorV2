"""ReleaseMixin: Speichern, Validieren, Diff, Preview und kontrollierte Aktivierung."""
from __future__ import annotations

import json
import threading
import tkinter as tk
from tkinter import messagebox


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
            "Bitte 'Regel aus PDF erstellen oder prüfen' erneut ausführen.",
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
        if not self._guard_field_form():
            return
        if not self.current_draft_path:
            self._set_hint("Bitte zuerst einen Entwurf laden.")
            return

        key = self.var_new_assay_key.get().strip()
        name = self.var_new_assay_name.get().strip()
        if not key or not name:
            self._set_hint("Assay-Schlüssel und Assay-Name sind erforderlich.")
            return

        # A proof is bound to the exact draft bytes. Rewriting an unchanged
        # draft here would invalidate a proof produced by the wizard. Dirty
        # UI state is persisted first, so the proof check correctly requires
        # Step by Step to be run again for those changed bytes.
        if not self._quick_validate("Aktivierung", save=bool(getattr(self, "_dirty", False))):
            return

        if not self._check_authoring_readiness_for_activate():
            return

        mode = "update" if key in self.known_assay_keys else "create"
        diff = self._rules.diff_draft_vs_active(key, self.current_draft_path)
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
            self._reload_assays()
        except Exception as e:
            messagebox.showerror("Fehler", str(e))
