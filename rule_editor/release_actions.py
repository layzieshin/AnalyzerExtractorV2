"""ReleaseMixin: Speichern, Validieren, Diff, Preview und kontrollierte Aktivierung."""
from __future__ import annotations

import json
import threading
import tkinter as tk
from tkinter import messagebox

from src.rulesuite.api import (
    activate_draft,
    activate_new_draft,
    check_authoring_readiness,
    diff_draft_vs_active,
    preview_extract,
    validate_draft,
)


class ReleaseMixin:
    def _clear_validation_list(self) -> None:
        self.list_validation.delete(0, tk.END)

    def _render_validation_report(self, report: dict) -> None:
        self._clear_validation_list()
        if report.get("ok"):
            self.list_validation.insert(tk.END, "OK: Draft ist valide")
            self._set_hint("Validierung erfolgreich.")
            return

        for err in report.get("errors", []):
            self.list_validation.insert(tk.END, f"- {err}")
        self._set_hint(f"Validierung fehlgeschlagen ({len(report.get('errors', []))} Fehler).")

    def _quick_validate(self, phase: str) -> bool:
        try:
            self._save_meta_to_draft(push_undo=False)
            report = validate_draft(self.current_draft_path or "")
        except Exception as e:
            self._set_hint(f"{phase}: Speichern/Validieren fehlgeschlagen")
            messagebox.showerror("Fehler", str(e))
            return False

        self._render_validation_report(report)
        if report.get("ok"):
            return True

        if not messagebox.askyesno(
            "Validierung",
            f"{phase}: Draft ist nicht valide ({len(report.get('errors', []))} Fehler). Trotzdem fortfahren?",
        ):
            return False
        return True

    def _check_authoring_readiness_for_activate(self) -> bool:
        if not self.current_draft_path:
            return False
        assay_text = (getattr(self, "assay_block_text", "") or "").strip()
        try:
            report = check_authoring_readiness(
                self.current_draft_path,
                assay_text if assay_text else None,
            )
        except Exception as e:
            messagebox.showerror("Readiness", str(e))
            return False

        if report.get("structural_errors"):
            messagebox.showerror(
                "Aktivierung blockiert",
                "Strukturfehler im Draft:\n" + "\n".join(report["structural_errors"][:12]),
            )
            return False

        if assay_text:
            if not report.get("ok"):
                missing = report.get("missing_required") or []
                messagebox.showerror(
                    "Aktivierung blockiert",
                    "Pflichtfelder nicht bestätigt im Beispieltext:\n"
                    + (", ".join(missing) if missing else "unbekannt"),
                )
                return False
            return True

        if not messagebox.askyesno(
            "Kein Beispieltext geprüft",
            "Kein Beispieltext geladen. Pflichtfeld-Treffer gegen PDF wurden nicht verifiziert.\n\n"
            "Trotzdem aktivieren?",
        ):
            return False
        return True

    def on_save_all(self) -> None:
        if not self.current_draft_path:
            self._set_hint("Bitte zuerst Draft laden. Tipp: Erst Draft laden, dann speichern/validieren.")
            return
        try:
            self._save_meta_to_draft(push_undo=True)
            self.on_load_draft_into_editor()
            self._log("Draft gespeichert.")
            self._set_hint("Draft erfolgreich gespeichert.")
        except Exception as e:
            messagebox.showerror("Fehler", str(e))

    def on_validate(self) -> None:
        if not self.current_draft_path:
            self._set_hint("Bitte zuerst Draft laden.")
            return
        try:
            self._save_meta_to_draft(push_undo=True)
            report = validate_draft(self.current_draft_path)
            self._render_validation_report(report)
            self._log("=== Validierung ===")
            if report.get("ok"):
                self._log("OK: Draft ist valide")
                messagebox.showinfo("Validierung", "Draft ist valide.")
            else:
                for err in report.get("errors", []):
                    self._log(f"- {err}")
                messagebox.showwarning("Validierung", "Draft ist nicht valide. Details in Liste/Log.")
        except Exception as e:
            messagebox.showerror("Fehler", str(e))

    def on_show_diff(self) -> None:
        if not self.current_draft_path:
            self._set_hint("Bitte zuerst Draft laden.")
            return
        key = self.var_new_assay_key.get().strip()
        if not key:
            self._set_hint("assay_key ist erforderlich. Tipp: Oben im Draft-Bereich einen gueltigen Assay-Key setzen.")
            return
        try:
            self._save_meta_to_draft(push_undo=False)
            diff = diff_draft_vs_active(self.var_root.get().strip(), key, self.current_draft_path)
            self._log(f"[DIFF] mode={diff.get('mode')} ruleset={diff.get('ruleset_file')}")
            changes = diff.get("changes", [])
            if not changes:
                self._log("[DIFF] Keine Unterschiede")
            else:
                for ch in changes[:80]:
                    self._log(f"  - {ch.get('path')}: active={ch.get('active')} -> draft={ch.get('draft')}")
                if len(changes) > 80:
                    self._log(f"  ... {len(changes) - 80} weitere Änderungen")
            self._set_hint(f"Diff angezeigt ({len(changes)} Änderungen).")
        except Exception as e:
            messagebox.showerror("Fehler", str(e))

    def on_preview(self) -> None:
        if self._busy:
            return
        if not self.current_draft_path:
            self._set_hint("Bitte zuerst Draft laden.")
            return
        pdf = self.var_pdf.get().strip()
        key = self.var_new_assay_key.get().strip()
        if not pdf or not key:
            self._set_hint("preview_pdf und assay_key sind erforderlich. Tipp: PDF waehlen und Assay-Key aus dem Draft pruefen.")
            return

        if not self._quick_validate("Preview"):
            return

        self._set_busy(True, "Preview läuft...")
        threading.Thread(target=self._preview_thread, args=(pdf, key), daemon=True).start()

    def _preview_thread(self, pdf: str, key: str) -> None:
        root = self.var_root.get().strip()
        draft_path = self.current_draft_path
        try:
            out = preview_extract(root, pdf, key, draft_path=draft_path)
            payload = json.dumps(out, ensure_ascii=False, indent=2)
            self.after(0, lambda p=payload: self._finish_preview_success(p))
        except Exception as e:
            msg = str(e)
            self.after(0, lambda m=msg: self._finish_preview_error(m))

    def _finish_preview_success(self, payload: str) -> None:
        try:
            self._log("=== Preview ===")
            self._log(payload)
            self._set_hint("Preview erfolgreich.")
        finally:
            self._set_busy(False, "Bereit")

    def _finish_preview_error(self, msg: str) -> None:
        try:
            self._log(f"[ERROR] preview: {msg}")
            self._set_hint("Preview fehlgeschlagen. Siehe Log.")
        finally:
            self._set_busy(False, "Bereit")

    def on_activate(self) -> None:
        if not self.current_draft_path:
            self._set_hint("Bitte zuerst Draft laden.")
            return

        key = self.var_new_assay_key.get().strip()
        name = self.var_new_assay_name.get().strip()
        if not key or not name:
            self._set_hint("assay_key und assay_name sind erforderlich. Tipp: Beide Felder im Meta-Bereich ausfuellen.")
            return

        if not self._quick_validate("Aktivierung"):
            return

        if not self._check_authoring_readiness_for_activate():
            return

        mode = "update" if key in self.known_assay_keys else "create"
        diff = diff_draft_vs_active(self.var_root.get().strip(), key, self.current_draft_path)
        change_count = len(diff.get("changes", []))
        action_text = (
            f"Bestehendes Assay {key} wird überschrieben.\n\n"
            if mode == "update"
            else f"Neues Assay {key} wird angelegt und in index.json eingetragen.\n\n"
        )
        confirm = (
            action_text
            + f"Fortfahren?\nName: {name}\nÄnderungen: {change_count}\n\n"
            + "Hinweis: 'Diff anzeigen' zeigt Details vorab."
        )
        if not messagebox.askyesno("Aktivierung bestätigen", confirm):
            return

        try:
            if mode == "update":
                path = activate_draft(self.var_root.get().strip(), key, self.current_draft_path)
                self._log(f"Aktualisiert: {path}")
            else:
                path = activate_new_draft(self.var_root.get().strip(), key, name, self.current_draft_path)
                self._log(f"Neues Assay aktiviert: {path}")
            self._set_hint("Aktivierung abgeschlossen.")
            self._reload_assays()
        except Exception as e:
            messagebox.showerror("Fehler", str(e))
