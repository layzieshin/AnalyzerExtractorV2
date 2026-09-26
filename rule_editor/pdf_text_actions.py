"""PdfTextMixin: Assay-Text aus der PDF laden (Worker-Thread + UI-Callbacks)."""
from __future__ import annotations

import threading
import tkinter as tk


class PdfTextMixin:
    def on_load_text(self) -> None:
        if self._busy:
            return
        if not self.current_draft_path:
            self._set_hint("Bitte zuerst ein Draft laden. Tipp: Ohne Draft ist kein Text- oder Preview-Lauf moeglich.")
            return
        pdf = self.var_pdf.get().strip()
        key = self.var_new_assay_key.get().strip()
        name = self.var_new_assay_name.get().strip()
        if not pdf or not key or not name:
            self._set_hint("Test-PDF, Assay-Schlüssel und Assay-Name sind erforderlich.")
            return

        self._set_busy(True, "Text laden...")
        rules = self._rules
        draft_path = self.current_draft_path
        threading.Thread(
            target=self._load_text_thread,
            args=(rules, pdf, key, name, draft_path),
            daemon=True,
        ).start()

    def _load_text_thread(self, rules: object, pdf: str, key: str, name: str, draft_path: str | None) -> None:
        try:
            out = rules.get_assay_text(pdf, key, name, draft_path=draft_path)
            block = str(out.get("assay_block", ""))
            detected = out.get("detected_assays")
            self.after(0, lambda b=block, d=detected: self._finish_text_load_success(b, d))
        except Exception as e:
            msg = str(e)
            fallback_text = ""
            if "assay_block_empty" in msg:
                fallback_text = self._load_normalized_pdf_text(rules, pdf)
            self.after(0, lambda m=msg, fb=fallback_text: self._finish_text_load_error(m, fb))

    def _load_normalized_pdf_text(self, rules: object, pdf: str) -> str:
        try:
            return str(rules.load_normalized_pdf_text(pdf))
        except Exception:
            return ""

    def _finish_text_load_success(self, block: str, detected: object) -> None:
        try:
            self.assay_block_text = block
            self._set_text_widget(block)
            self._log(f"Assay-Text geladen ({len(block)} Zeichen). detected_assays={detected}")
            self._set_hint(f"Assay-Block geladen ({len(block)} Zeichen).")
        finally:
            self._set_busy(False, "Bereit")

    def _finish_text_load_error(self, msg: str, fallback_text: str = "") -> None:
        try:
            if fallback_text.strip():
                self.assay_block_text = fallback_text
                self._set_text_widget(fallback_text)
                self._log(f"[WARN] text_load: {msg}")
                self._log("Volltext der PDF angezeigt (Assay-Block konnte nicht getrennt werden).")
                self._set_hint(
                    "Assay-Abschnitt nicht gefunden – Volltext angezeigt. "
                    "Pruefen Sie assay_key/assay_name im Draft."
                )
            else:
                self._log(f"[ERROR] text_load: {msg}")
                self._set_hint(f"Fehler beim Textladen: {msg}")
        finally:
            self._set_busy(False, "Bereit")

    def _set_text_widget(self, text: str) -> None:
        self.txt_block.delete("1.0", tk.END)
        if text:
            self.txt_block.insert(tk.END, text)
        self.txt_block.see("1.0")
        self._set_field_preview_text("Assay-Text geladen. Testen Sie in den Feldeinstellungen ein Suchmuster.")
        try:
            self._maybe_refresh_field_markings()
        except Exception as e:
            self._log(f"[WARN] Markierungen konnten nicht aktualisiert werden: {e}")
