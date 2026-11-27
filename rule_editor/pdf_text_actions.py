"""PdfTextMixin: Assay-Text aus der PDF laden (Worker-Thread + UI-Callbacks)."""
from __future__ import annotations

import tkinter as tk


class PdfTextMixin:
    def show_document_view(self, view: str) -> None:
        if view not in {"text", "pdf"}:
            return
        self._document_view = view
        self.report_notebook.select(self.document_pdf_frame if view == "pdf" else self.document_text_frame)
        self.btn_document_text.configure(style="Doc.RuleSuite.Selected.TButton" if view == "text" else "Doc.RuleSuite.Secondary.TButton")
        self.btn_document_pdf.configure(style="Doc.RuleSuite.Selected.TButton" if view == "pdf" else "Doc.RuleSuite.Secondary.TButton")
        if view == "pdf":
            if not getattr(self, "_rule_pdf_image", None):
                self._request_rule_pdf()
            else:
                self.var_document_note.set(self.var_rule_pdf_page.get())
        else:
            self.var_document_note.set("Extrahierter Assay-Abschnitt · Text zum Erstellen einer Regel markieren" if self.assay_block_text else "Kein Assay-Text · Original-PDF verfügbar" if getattr(self, "_rule_pdf_sha256", "") else "Bitte eine Test-PDF laden")

    def _invalidate_local_pdf(self) -> None:
        self._rule_pdf_generation = getattr(self, "_rule_pdf_generation", 0) + 1
        self._rule_pdf_pending = None
        self._rule_pdf_request = None
        self._rule_pdf_page_index = 0
        self._rule_pdf_page_count = 0
        self._rule_pdf_zoom = 1.0
        self._rule_pdf_fit = True
        self._rule_pdf_image = None
        self._rule_pdf_page = None
        self._rule_pdf_sha256 = ""
        self._rule_pdf_loaded_path = ""
        self._rule_pdf_fit_attempted = False
        if hasattr(self, "rule_pdf_canvas"):
            self.rule_pdf_canvas.delete("all")
            self.rule_pdf_canvas.configure(scrollregion=(0, 0, 0, 0))
            self.var_rule_pdf_page.set("Keine Seite")

    def change_rule_pdf_page(self, delta: int) -> None:
        target = self._rule_pdf_page_index + delta
        if 0 <= target < self._rule_pdf_page_count:
            self._rule_pdf_page_index = target
            self._rule_pdf_fit_attempted = False
            self._request_rule_pdf()

    def zoom_rule_pdf(self, delta: float) -> None:
        self._rule_pdf_fit = False
        self._rule_pdf_zoom = max(.2, min(3.0, self._rule_pdf_zoom + delta))
        self._request_rule_pdf()

    def fit_rule_pdf_width(self) -> None:
        self._rule_pdf_fit = True
        self._rule_pdf_fit_attempted = False
        page = getattr(self, "_rule_pdf_page", None)
        if page is not None:
            self._rule_pdf_zoom = max(.05, min(1.0, page.zoom * max(40, self.rule_pdf_canvas.winfo_width() - 20) / page.width))
        self._request_rule_pdf()

    def _request_rule_pdf(self) -> None:
        if self._closed:
            return
        path = self.var_pdf.get().strip()
        if not path:
            self.var_document_note.set("Bitte eine lokale Test-PDF laden.")
            return
        if not hasattr(self, "_rule_pdf_generation"):
            self._invalidate_local_pdf()
        if not self._rule_pdf_sha256 or self._rule_pdf_loaded_path != path:
            self.var_document_note.set("Bitte die Test-PDF gemeinsam als Text und Original laden.")
            if not self._busy:
                self.on_load_text()
            return
        self._rule_pdf_generation += 1
        request = (self._rule_pdf_generation, self._context_generation, path, self._rule_pdf_page_index, self._rule_pdf_zoom, self._rule_pdf_sha256)
        self._rule_pdf_pending = request
        self._rule_pdf_request = request
        self.var_document_note.set("Original-PDF wird geladen …")
        self._start_rule_pdf()

    def _start_rule_pdf(self) -> None:
        if self._closed or self._task_runner.is_active("editor-rule-pdf"):
            return
        request = self._rule_pdf_pending
        if request is None:
            return
        self._rule_pdf_pending = None
        generation, context, path, index, zoom, expected_hash = request
        rules = self._rules
        def finish(result=None, error=None):
            if self._closed:
                return
            current = (self._rule_pdf_request == request and context == self._context_generation
                       and rules is self._rules and path == self.var_pdf.get().strip())
            if current and error is None:
                page = result["page"]
                self._rule_pdf_sha256 = result["source_sha256"]
                self._rule_pdf_page = page
                self._rule_pdf_page_count = page.page_count
                width = max(40, self.rule_pdf_canvas.winfo_width() - 20)
                fitted = max(.05, page.zoom * width / page.width)
                if self._rule_pdf_fit and not self._rule_pdf_fit_attempted and page.width > width + 2 and fitted < page.zoom - .00001:
                    self._rule_pdf_fit_attempted = True
                    self._rule_pdf_zoom = fitted
                    self._request_rule_pdf()
                else:
                    self._rule_pdf_zoom = page.zoom
                    self._rule_pdf_image = tk.PhotoImage(master=self, data=page.image_data, format="PPM")
                    canvas = self.rule_pdf_canvas
                    canvas.delete("all")
                    canvas.create_image(10, 10, anchor="nw", image=self._rule_pdf_image)
                    canvas.configure(scrollregion=(0, 0, page.width + 20, page.height + 20))
                    canvas.yview_moveto(0)
                    canvas.xview_moveto(0)
                    self.var_rule_pdf_page.set(f"Seite {page.page_index + 1} von {page.page_count} · {page.zoom:.0%}")
                    if self._document_view == "pdf":
                        self.var_document_note.set(self.var_rule_pdf_page.get())
                    self.btn_rule_pdf_previous.configure(state="normal" if page.page_index > 0 else "disabled")
                    self.btn_rule_pdf_next.configure(state="normal" if page.page_index + 1 < page.page_count else "disabled")
            elif current:
                self.var_document_note.set(str(error))
            self._start_rule_pdf()
        self._task_runner.submit("editor-rule-pdf", lambda: rules.render_rule_pdf_page(path, page_index=index, zoom=zoom, expected_sha256=expected_hash),
            on_success=lambda out: finish(result=out), on_error=lambda error: finish(error=error))

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

        if hasattr(self, "rule_pdf_canvas"):
            self._invalidate_local_pdf()
            self.assay_block_text = ""
            self.txt_block.delete("1.0", tk.END)
            self._clear_field_markings()
            self._refresh_field_grid()
            self._set_field_preview_text("")
        self._set_busy(True, "Text laden...")
        rules = self._rules
        draft_path = self.current_draft_path
        generation, context = self._text_generation, self._context_generation

        def completed(result):
            if self._closed:
                return
            current = (rules is self._rules and context == self._context_generation
                       and generation == self._text_generation and draft_path == self.current_draft_path
                       and (pdf, key, name) == (self.var_pdf.get().strip(), self.var_new_assay_key.get().strip(), self.var_new_assay_name.get().strip()))
            if not current:
                self._set_busy(False, "Bereit")
                return
            block, detected, error, fallback, *source = result
            if source:
                self._rule_pdf_sha256 = source[0]
                self._rule_pdf_loaded_path = pdf
            if error is None:
                self._finish_text_load_success(block, detected)
            else:
                self._finish_text_load_error(error, fallback)
                if source and getattr(self, "_document_view", "text") == "text":
                    self.var_document_note.set("Kein Assay-Text · Original-PDF verfügbar")
            if getattr(self, "_document_view", "text") == "pdf" and source:
                self._request_rule_pdf()

        if not self._task_runner.submit("editor-pdf-text", lambda: self._load_text_thread(rules, pdf, key, name, draft_path),
                                        on_success=completed, on_error=lambda error: completed(("", None, str(error), ""))):
            self._set_busy(False, "Bereit")

    def _load_text_thread(self, rules: object, pdf: str, key: str, name: str, draft_path: str | None) -> tuple:
        try:
            out = rules.get_assay_text(pdf, key, name, draft_path=draft_path)
            block = str(out.get("assay_block", ""))
            detected = out.get("detected_assays")
            return (block, detected, out.get("text_error"), "", out["source_sha256"]) if out.get("source_sha256") else (block, detected, None, "")
        except Exception as e:
            msg = str(e)
            fallback_text = ""
            if "assay_block_empty" in msg:
                fallback_text = self._load_normalized_pdf_text(rules, pdf)
            return "", None, msg, fallback_text

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
