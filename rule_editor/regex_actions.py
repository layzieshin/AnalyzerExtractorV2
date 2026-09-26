"""RegexMixin: Regex-Einzeltest, Ergebnistabelle, Vorschau und Batch-Check."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

from .regex_library import RegexLibraryPopup


class RegexMixin:
    def on_open_regex_library(self, target_entry: tk.Entry | None = None) -> None:
        entry = target_entry if target_entry is not None else getattr(self, "ent_field_regex", None)
        if entry is None:
            self._set_hint("Kein Regex-Eingabefeld verfuegbar.")
            return
        RegexLibraryPopup(self, entry)

    def on_test_regex(self) -> None:
        regex = self.var_field_regex.get().strip()
        if not regex:
            self._set_hint("Bitte regex eingeben. Tipp: Mit einfacher Basisregex starten und dann verfeinern.")
            return
        if not self.assay_block_text:
            self._set_hint("Bitte zuerst Assay-Text laden. Tipp: PDF waehlen und 'Text laden' ausfuehren.")
            return

        try:
            group = int(self.var_regex_group.get().strip() or "1")
        except ValueError:
            self._set_hint("regex_group muss integer sein.")
            return

        res = self._rules.test_regex(self.assay_block_text, regex, group=group)
        self.txt_block.tag_remove("hit", "1.0", tk.END)
        record = self._build_regex_result_record(
            regex,
            res,
            group=group,
            source="single",
            field_name=self.var_field_key.get().strip(),
        )
        self._append_regex_result_row(record)
        self._render_regex_record_preview(record)
        self._log_regex_result(record)

        if res.get("matched") and res.get("span"):
            start, end = res["span"]
            start_idx = f"1.0+{start}c"
            end_idx = f"1.0+{end}c"
            self.txt_block.tag_add("hit", start_idx, end_idx)
            self.txt_block.see(start_idx)
            self._set_hint("Regex-Treffer markiert (Feldeditor und PDF-Testbericht).")
        elif res.get("error"):
            self._set_hint("Regex-Fehler. Details in den Feldeinstellungen und im Log.")
        else:
            if regex.lstrip().startswith("^"):
                self._set_hint("Kein Treffer. Hinweis: '^' sucht nur am Zeilenanfang; vor dem Begriff kann noch Text stehen.")
            else:
                self._set_hint("Kein Regex-Treffer.")

    def _write_preview_text(self, widget: tk.Text | None, text: str, span: tuple[int, int] | None = None) -> None:
        if widget is None:
            return
        widget.configure(state="normal")
        widget.delete("1.0", tk.END)
        widget.insert(tk.END, text)
        widget.tag_remove("hit", "1.0", tk.END)
        if span is not None:
            start_idx = f"1.0+{span[0]}c"
            end_idx = f"1.0+{span[1]}c"
            widget.tag_add("hit", start_idx, end_idx)
            widget.see(start_idx)
        widget.configure(state="disabled")

    def _set_field_preview_text(self, text: str, span: tuple[int, int] | None = None) -> None:
        self._write_preview_text(self.txt_field_preview, text, span)
        self._write_preview_text(getattr(self, "txt_marking_regex_preview", None), text, span)

    def _build_regex_result_record(
        self,
        regex: str,
        result: dict,
        group: int,
        source: str = "single",
        field_name: str = "",
    ) -> dict[str, object]:
        context = str(result.get("context_snippet") or "")
        context_single = context.replace("\n", " ").strip()
        value = str(result.get("value") or "").strip()
        error = str(result.get("error") or "").strip()
        matched = bool(result.get("matched"))

        if error:
            status = "ERROR"
            result_text = f"FEHLER - {error}"
        elif matched:
            status = "HIT"
            result_text = value if value else "(leer)"
        else:
            status = "MISS"
            result_text = "Kein Treffer"

        context_short = context_single if len(context_single) <= 180 else context_single[:177] + "..."
        preview_title = f"Regex: /{regex}/ | Gruppe: {group} | Status: {status}"
        preview_body = context if context else f"Ergebnis: {result_text}"
        preview_text = preview_title + "\n" + preview_body

        preview_span: tuple[int, int] | None = None
        if context and value:
            pos = context.find(value)
            if pos >= 0:
                offset = len(preview_title) + 1
                preview_span = (offset + pos, offset + pos + len(value))

        return {
            "field_name": field_name.strip() or "-",
            "source": source,
            "status": status,
            "regex": regex,
            "group": group,
            "result_text": result_text,
            "context": context_single,
            "context_short": context_short,
            "preview_text": preview_text,
            "preview_span": preview_span,
            "matched": matched,
            "error": error,
            "span": result.get("span"),
        }

    def _render_regex_record_preview(self, record: dict[str, object]) -> None:
        self._set_field_preview_text(str(record.get("preview_text", "")), record.get("preview_span"))

    def _log_regex_result(self, record: dict[str, object]) -> None:
        regex = str(record.get("regex", ""))
        context = str(record.get("context", "")).strip()
        result_text = str(record.get("result_text", "")).strip()
        self._log(f'getesteter regex "/{regex}/"')
        self._log(f"Kontext: {context if context else '-'}")
        self._log(f"Ergebnis: {result_text if result_text else '-'}")

    def _append_regex_result_row(self, record: dict[str, object]) -> None:
        if self.tree_regex_results is None:
            return
        self._regex_result_counter += 1
        row_id = f"regex_{self._regex_result_counter}"
        self._regex_result_data[row_id] = record
        self.tree_regex_results.insert(
            "",
            tk.END,
            iid=row_id,
            values=(
                record.get("field_name", ""),
                record.get("status", ""),
                record.get("regex", ""),
                record.get("result_text", ""),
                record.get("context_short", ""),
            ),
        )
        self.tree_regex_results.selection_set(row_id)
        self.tree_regex_results.focus(row_id)
        self.tree_regex_results.see(row_id)

    def _clear_regex_results(self) -> None:
        if self.tree_regex_results is None:
            return
        for row in self.tree_regex_results.get_children():
            self.tree_regex_results.delete(row)
        self._regex_result_data.clear()
        self._set_hint("Regex-Ergebnisliste geleert.")

    def on_regex_result_selected(self, _event: object = None) -> None:
        if self.tree_regex_results is None:
            return
        sel = self.tree_regex_results.selection()
        if not sel:
            return
        rec = self._regex_result_data.get(sel[0])
        if not rec:
            return
        self._render_regex_record_preview(rec)

    def on_batch_regex_check(self) -> None:
        if not self.current_draft_path:
            self._set_hint("Bitte zuerst Draft laden.")
            return
        if not self.assay_block_text:
            self._set_hint("Bitte zuerst Assay-Text laden. Tipp: Sonst kann kein Batch-Regex-Check erfolgen.")
            return
        try:
            group = int(self.var_regex_group.get().strip() or "1")
            out = self._rules.batch_check_fields(self.current_draft_path, self.assay_block_text, group=group)
            self._log(
                f"[BATCH] total={out.get('total_fields')} hits={out.get('hits')} "
                f"misses={out.get('misses')} errors={out.get('errors')}"
            )
            for row in out.get("results", []):
                status = "HIT" if row.get("matched") else "MISS"
                self._log(
                    f"  - {row.get('key')} [{status}] required={row.get('required')} "
                    f"value={row.get('value')} error={row.get('error')}"
                )
                field_regex = ""
                for field_row in self.fields_data:
                    if str(field_row.get("key", "")).strip() == str(row.get("key", "")).strip():
                        field_regex = str(field_row.get("regex", "")).strip()
                        break
                batch_record = self._build_regex_result_record(
                    field_regex or str(row.get("key", "")),
                    {
                        "matched": bool(row.get("matched")),
                        "value": row.get("value"),
                        "context_snippet": "",
                        "error": row.get("error"),
                        "span": None,
                    },
                    group=group,
                    source="batch",
                    field_name=str(row.get("key", "")).strip(),
                )
                self._append_regex_result_row(batch_record)
            self._set_hint("Batch-Regex-Check abgeschlossen.")
        except Exception as e:
            messagebox.showerror("Fehler", str(e))
