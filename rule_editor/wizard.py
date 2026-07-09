"""Gefuehrter Anlage-Wizard fuer neue Regelsets.

Eigenes modales Fenster mit festen Schritten:
1. Basis (assay_key/assay_name, aehnlich-wie-Vorlage oder nur Header-Regeln)
2. Beispiel-PDF laden
3. Feld fuer Feld bestaetigen (Treffer im Text markiert)
4. Eigene Felder hinzufuegen (mit Regex-Test und Regex-Bibliothek)
5. Abschluss (validieren, im Editor oeffnen oder direkt aktivieren)

Der Wizard erzeugt einen normalen Draft und schreibt ausschliesslich ueber die
RuleSuite-API; Abbruch laesst den Draft als Entwurf liegen.
"""
from __future__ import annotations

import threading
import tkinter as tk
from typing import Callable
from tkinter import filedialog, messagebox

from src.rulesuite.api import (
    HEADER_FIELD_KEYS,
    REQUIRED_HEADER_FIELD_KEYS,
    add_field,
    check_required_fields,
    create_draft_from_template,
    derive_draft,
    get_assay_text,
    load_draft,
    locate_fields,
    remove_field,
    test_regex,
    update_field,
    validate_draft,
)

from .wizard_ui import _REQUIRED_STATUS_LABELS, _STEP_TITLES, _STEPS, WizardUiMixin


class NewRulesetWizard(WizardUiMixin, tk.Toplevel):
    def __init__(
        self,
        master: tk.Misc,
        project_root: str,
        assay_display_to_key: dict[str, str],
        on_open_in_editor: Callable[[str], None],
        on_activate_requested: Callable[[str], None],
    ) -> None:
        super().__init__(master)
        self.title("Neues Regelset (gefuehrt)")
        self.geometry("1100x780")
        self.transient(master)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

        self._project_root = project_root
        self._assay_display_to_key = assay_display_to_key
        self._on_open_in_editor = on_open_in_editor
        self._on_activate_requested = on_activate_requested

        self._step = 0
        self.draft_path: str | None = None
        self.assay_text: str = ""
        self._fields: list[dict] = []
        self._field_idx = 0
        self._busy = False
        self._template_mode = False
        self._required_check: dict | None = None

        self.var_key = tk.StringVar(value="")
        self.var_name = tk.StringVar(value="")
        self.var_mode = tk.StringVar(value="derive")
        self.var_source = tk.StringVar(value="")
        self.var_pdf = tk.StringVar(value="")
        self.var_status = tk.StringVar(value="")
        self.var_match = tk.StringVar(value="")
        self.var_progress = tk.StringVar(value="")
        self.var_custom_count = tk.StringVar(value="")
        self.var_finish_action = tk.StringVar(value="editor")

        self.var_f_key = tk.StringVar(value="")
        self.var_f_regex = tk.StringVar(value="")
        self.var_f_required = tk.BooleanVar(value=False)
        self.var_f_mode = tk.StringVar(value="none")
        self.var_f_after = tk.StringVar(value="")
        self.var_f_line = tk.StringVar(value="")

        self._build_ui()
        self._show_step(0)

    # ------------------------------------------------------------ Navigation

    def _show_step(self, idx: int) -> None:
        self._step = idx
        key = _STEPS[idx]
        self.lbl_title.config(text=_STEP_TITLES[key])
        self._card_frames[key].tkraise()
        self.btn_back.config(state=tk.NORMAL if idx > 0 else tk.DISABLED)
        if key == "confirm":
            self.btn_next.config(text="Passt - weiter")
        elif key == "finish":
            self.btn_next.config(text="Fertig stellen")
        else:
            self.btn_next.config(text="Weiter")
        self.var_match.set("")
        if key == "basis":
            self.var_status.set("Grunddaten eintragen und Vorlage waehlen.")
        elif key == "pdf":
            self._refresh_required_checklist()
            self.var_status.set("Beispiel-PDF waehlen und 'Text laden' klicken.")
        elif key == "confirm":
            self._configure_confirm_step()
        elif key == "custom":
            self._refresh_custom_count()
            self._clear_field_form()
            self.var_status.set("Eigene Felder hinzufuegen oder direkt mit 'Weiter' fortfahren.")
        elif key == "finish":
            self._render_summary()
            self.var_status.set("Pruefen Sie die Zusammenfassung und schliessen Sie ab.")

    def _on_next(self) -> None:
        if self._busy:
            return
        key = _STEPS[self._step]
        if key == "basis":
            if self._create_draft():
                self._show_step(1)
        elif key == "pdf":
            if not self.assay_text.strip():
                self.var_status.set("Bitte zuerst eine PDF waehlen und 'Text laden' ausfuehren.")
                return
            self._reload_fields()
            if self._template_mode:
                self._fields = self._ordered_required_fields()
            if not self._fields:
                self._show_step(3)
                return
            self._field_idx = 0
            self._show_step(2)
            self._show_current_field()
        elif key == "confirm":
            if not self._apply_current_field():
                return
            if self._field_idx + 1 < len(self._fields):
                self._field_idx += 1
                self._show_current_field()
            else:
                self._show_step(3)
        elif key == "custom":
            if self._template_mode and not self._required_fields_confirmed():
                self.var_status.set(
                    "Noch nicht alle Pflichtfelder bestaetigt. Bitte Schritt 3 abschliessen oder Regex manuell pruefen."
                )
                return
            self._show_step(4)
        elif key == "finish":
            self._finish()

    def _on_back(self) -> None:
        if self._busy:
            return
        key = _STEPS[self._step]
        if key == "pdf":
            self._show_step(0)
        elif key == "confirm":
            if self._field_idx > 0:
                self._field_idx -= 1
                self._show_current_field()
            else:
                self._show_step(1)
        elif key == "custom":
            self._reload_fields()
            if self._fields:
                self._field_idx = len(self._fields) - 1
                self._show_step(2)
                self._show_current_field()
            else:
                self._show_step(1)
        elif key == "finish":
            self._show_step(3)

    def _on_cancel(self) -> None:
        msg = "Wizard abbrechen?"
        if self.draft_path:
            msg += "\n\nDer bisherige Stand bleibt als Draft erhalten:\n" + self.draft_path
        if messagebox.askyesno("Abbrechen", msg, parent=self):
            self.destroy()

    # ------------------------------------------------------------ Schritt 1: Draft anlegen

    def _create_draft(self) -> bool:
        key = self.var_key.get().strip()
        name = self.var_name.get().strip()
        if not key or not name:
            self.var_status.set("Assay-Key und Assay-Name sind erforderlich.")
            return False
        if key in set(self._assay_display_to_key.values()):
            self.var_status.set(f"Assay-Key {key} existiert bereits. Bitte einen neuen Key vergeben.")
            return False
        try:
            if self.var_mode.get() == "derive":
                source_key = self._assay_display_to_key.get(self.var_source.get().strip())
                if not source_key:
                    self.var_status.set("Bitte eine Vorlage auswaehlen.")
                    return False
                self.draft_path = derive_draft(self._project_root, source_key, key, name)
                self._template_mode = False
            else:
                self.draft_path = create_draft_from_template(self._project_root, key, name)
                self._template_mode = True
        except Exception as e:
            messagebox.showerror("Fehler", str(e), parent=self)
            return False
        self._reload_fields()
        label = "Pflichtfelder" if self._template_mode else "Felder"
        self.var_status.set(f"Draft erstellt ({len(self._fields)} {label} uebernommen): {self.draft_path}")
        return True

    def _ordered_required_fields(self) -> list[dict]:
        if not self.draft_path:
            return []
        data = load_draft(self.draft_path)
        fields = data.get("extract_rules", {}).get("fields", [])
        if not isinstance(fields, list):
            return []
        by_key = {str(f.get("key", "")).strip(): f for f in fields if isinstance(f, dict)}
        return [by_key[key] for key in REQUIRED_HEADER_FIELD_KEYS if key in by_key]

    def _reload_fields(self) -> None:
        if not self.draft_path:
            self._fields = []
            return
        data = load_draft(self.draft_path)
        fields = data.get("extract_rules", {}).get("fields", [])
        self._fields = [f for f in fields if isinstance(f, dict)] if isinstance(fields, list) else []

    # ------------------------------------------------------------ Schritt 2: PDF laden

    def _on_pick_pdf(self) -> None:
        p = filedialog.askopenfilename(title="PDF waehlen", filetypes=[("PDF", "*.pdf")], parent=self)
        if p:
            self.var_pdf.set(p)

    def _on_load_text(self) -> None:
        if self._busy:
            return
        pdf = self.var_pdf.get().strip()
        if not pdf or not self.draft_path:
            self.var_status.set("Bitte zuerst eine PDF waehlen.")
            return
        self._busy = True
        self.var_status.set("Text wird geladen...")
        threading.Thread(
            target=self._load_text_thread,
            args=(pdf, self.var_key.get().strip(), self.var_name.get().strip()),
            daemon=True,
        ).start()

    def _load_text_thread(self, pdf: str, key: str, name: str) -> None:
        try:
            out = get_assay_text(self._project_root, pdf, key, name, draft_path=self.draft_path)
            block = str(out.get("assay_block", ""))
            self.after(0, lambda b=block: self._finish_text_load(b, None))
        except Exception as e:
            msg = str(e)
            fallback = ""
            if "assay_block_empty" in msg:
                fallback = self._load_full_pdf_text(pdf)
            self.after(0, lambda m=msg, fb=fallback: self._finish_text_load(fb, m))

    @staticmethod
    def _load_full_pdf_text(pdf: str) -> str:
        try:
            from src.normalizer.api import normalize_lines
            from src.parser.api import parse

            doc = parse(pdf)
            lines = [ln for p in doc.pages for ln in p.lines]
            return "\n".join(normalize_lines(lines))
        except Exception:
            return ""

    def _finish_text_load(self, text: str, error: str | None) -> None:
        self._busy = False
        if not text.strip():
            self.var_status.set(f"Text konnte nicht geladen werden: {error}")
            return
        self.assay_text = text
        self._set_preview_text(text)
        self._refresh_required_checklist()
        if error:
            self.var_status.set(
                "Assay-Abschnitt nicht gefunden - Volltext der PDF geladen. "
                "Pruefen Sie ggf. Assay-Key/Name."
            )
        else:
            self.var_status.set(f"Assay-Text geladen ({len(text)} Zeichen). Weiter mit 'Weiter'.")

    def _refresh_required_checklist(self) -> None:
        self.list_required.delete(0, tk.END)
        if not self.draft_path or not self.assay_text.strip():
            return
        try:
            self._required_check = check_required_fields(self.draft_path, self.assay_text, group=1)
        except Exception as exc:
            self._required_check = None
            self.list_required.insert(tk.END, f"Pruefung fehlgeschlagen: {exc}")
            return
        for row in self._required_check.get("results", []):
            if not isinstance(row, dict):
                continue
            key = str(row.get("key", ""))
            status = str(row.get("status", ""))
            label = _REQUIRED_STATUS_LABELS.get(status, status)
            self.list_required.insert(tk.END, f"{key:<12} {label}")

    def _required_fields_confirmed(self) -> bool:
        if not self.draft_path or not self.assay_text.strip():
            return False
        try:
            report = check_required_fields(self.draft_path, self.assay_text, group=1)
        except Exception:
            return False
        self._required_check = report
        return bool(report.get("all_confirmed"))

    def _on_required_field_selected(self, _event=None) -> None:
        if self._step != 1 or not self.draft_path:
            return
        sel = self.list_required.curselection()
        if not sel:
            return
        line = self.list_required.get(sel[0])
        key = line.split()[0].strip()
        if key not in REQUIRED_HEADER_FIELD_KEYS:
            return
        self._reload_fields()
        if self._template_mode:
            self._fields = self._ordered_required_fields()
        try:
            self._field_idx = next(i for i, field in enumerate(self._fields) if field.get("key") == key)
        except StopIteration:
            return
        self._show_step(2)
        self._show_current_field()

    def _configure_confirm_step(self) -> None:
        if self._template_mode:
            self.btn_remove_field.config(state=tk.DISABLED)
            self.chk_required.config(state=tk.DISABLED)
        else:
            self.btn_remove_field.config(state=tk.NORMAL)
            self.chk_required.config(state=tk.NORMAL)
        self._set_preview_editable(True)

    # ------------------------------------------------------------ Schritt 3: Pflichtfelder bestaetigen

    def _show_current_field(self) -> None:
        field = self._fields[self._field_idx]
        key = str(field.get("key", ""))

        tag = " (Pflichtfeld)" if key in REQUIRED_HEADER_FIELD_KEYS else ""
        if key in HEADER_FIELD_KEYS and key not in REQUIRED_HEADER_FIELD_KEYS:
            tag = " (Header-Regel)"
        self.var_progress.set(f"Feld {self._field_idx + 1} von {len(self._fields)}: {key}{tag}")
        self.var_f_key.set(key)
        self.var_f_regex.set(str(field.get("regex", "")))
        self.var_f_required.set(
            True if key in REQUIRED_HEADER_FIELD_KEYS else bool(field.get("required", False))
        )
        sf = field.get("search_from")
        if isinstance(sf, dict) and "after" in sf:
            self.var_f_mode.set("after")
            self.var_f_after.set(str(sf.get("after", "")))
            self.var_f_line.set("")
        elif isinstance(sf, dict) and "line" in sf:
            self.var_f_mode.set("line")
            self.var_f_line.set(str(sf.get("line", "")))
            self.var_f_after.set("")
        else:
            self.var_f_mode.set("none")
            self.var_f_after.set("")
            self.var_f_line.set("")
        self._locate_and_highlight(key)
        self._refresh_required_checklist()
        self.var_status.set(
            "Regex manuell pflegen, Fundstelle im Text pruefen und 'Pflichtfeld pruefen' oder 'Passt - weiter' nutzen."
        )

    def _on_confirm_required_field(self) -> None:
        if not self._apply_current_field(save_only=True):
            return
        key = self.var_f_key.get().strip()
        self._locate_and_highlight(key)
        self._refresh_required_checklist()
        row = self._required_row_for_key(key)
        if row and row.get("status") == "confirmed":
            self.var_status.set(f"Pflichtfeld {key} bestaetigt.")
        elif row:
            label = _REQUIRED_STATUS_LABELS.get(str(row.get("status", "")), str(row.get("status", "")))
            self.var_status.set(f"Pflichtfeld {key}: {label}")
        else:
            self.var_status.set(f"Pflichtfeld {key} geprueft.")

    def _required_row_for_key(self, key: str) -> dict | None:
        if not self._required_check:
            return None
        return next(
            (row for row in self._required_check.get("results", []) if isinstance(row, dict) and row.get("key") == key),
            None,
        )

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
                raise ValueError("Suche ab 'line' muss eine ganze Zahl sein")
        return None

    def _apply_current_field(self, save_only: bool = False) -> bool:
        if not self.draft_path or not self._fields:
            return True
        key = self.var_f_key.get().strip()
        regex = self.var_f_regex.get().strip()
        is_contract_required = key in REQUIRED_HEADER_FIELD_KEYS
        if not regex and not save_only:
            if is_contract_required:
                self.var_status.set("Regex darf fuer Pflichtfelder nicht leer sein.")
            else:
                self.var_status.set("Regex darf nicht leer sein. Tipp: 'Feld entfernen', wenn das Feld nicht gebraucht wird.")
            return False
        try:
            sf = self._build_search_from()
            update_field(
                self.draft_path,
                key,
                regex=regex,
                required=True if is_contract_required else self.var_f_required.get(),
                search_from=sf if self.var_f_mode.get() != "none" else {},
            )
        except Exception as e:
            messagebox.showerror("Fehler", str(e), parent=self)
            return False
        self._reload_fields()
        if self._template_mode:
            self._fields = self._ordered_required_fields()
        return True

    def _on_retest_field(self) -> None:
        if not self._apply_current_field():
            return
        self._locate_and_highlight(self.var_f_key.get().strip())

    def _on_remove_field(self) -> None:
        if not self.draft_path or not self._fields:
            return
        key = self.var_f_key.get().strip()
        if key in REQUIRED_HEADER_FIELD_KEYS:
            self.var_status.set("Pflichtfelder aus dem Vertrag koennen nicht entfernt werden.")
            return
        if not messagebox.askyesno("Feld entfernen", f"Feld '{key}' wirklich aus dem Regelset entfernen?", parent=self):
            return
        try:
            remove_field(self.draft_path, key)
        except Exception as e:
            messagebox.showerror("Fehler", str(e), parent=self)
            return
        self._reload_fields()
        if not self._fields:
            self._show_step(3)
            return
        self._field_idx = min(self._field_idx, len(self._fields) - 1)
        self._show_current_field()

    def _locate_and_highlight(self, key: str) -> None:
        self._clear_highlight()
        if not self.draft_path or not self.assay_text.strip():
            return
        try:
            out = locate_fields(self.draft_path, self.assay_text, group=1)
        except Exception as e:
            self.var_match.set(f"Pruefung fehlgeschlagen: {e}")
            return
        row = next((r for r in out.get("results", []) if isinstance(r, dict) and r.get("key") == key), None)
        if row is None:
            self.var_match.set("Feld nicht pruefbar (leerer key/regex).")
            return
        if row.get("error"):
            self.var_match.set(f"FEHLER: {row['error']}")
        elif row.get("matched"):
            span = row.get("span")
            self.var_match.set(f"TREFFER: {row.get('value')}")
            if isinstance(span, list) and len(span) == 2:
                self._highlight_span(int(span[0]), int(span[1]))
        else:
            self.var_match.set("KEIN TREFFER im Beispiel-Text.")

    def _on_use_cursor_line(self) -> None:
        line = self._cursor_line_index()
        self.var_f_mode.set("line")
        self.var_f_line.set(str(line))
        self.var_f_after.set("")
        self.var_status.set(f"search_from auf Zeile {line} gesetzt (0-basiert).")

    def _on_use_previous_line(self) -> None:
        line = max(0, self._cursor_line_index() - 1)
        self.var_f_mode.set("line")
        self.var_f_line.set(str(line))
        self.var_f_after.set("")
        self.var_status.set(f"search_from auf vorherige Zeile {line} gesetzt (0-basiert).")

    def _cursor_line_index(self) -> int:
        try:
            line = int(str(self.txt_preview.index(tk.INSERT)).split(".")[0])
            return max(0, line - 1)
        except Exception:
            return 0

    # ------------------------------------------------------------ Schritt 4: Eigene Felder

    def _refresh_custom_count(self) -> None:
        self._reload_fields()
        self.var_custom_count.set(f"Aktuell {len(self._fields)} Felder im Regelset.")

    def _clear_field_form(self) -> None:
        self.var_f_key.set("")
        self.var_f_regex.set("")
        self.var_f_required.set(False)
        self.var_f_mode.set("none")
        self.var_f_after.set("")
        self.var_f_line.set("")

    def _on_test_custom(self) -> None:
        regex = self.var_f_regex.get().strip()
        if not regex:
            self.var_status.set("Bitte zuerst einen Regex eingeben.")
            return
        if not self.assay_text.strip():
            self.var_status.set("Kein Assay-Text geladen.")
            return
        self._clear_highlight()
        res = test_regex(self.assay_text, regex, group=1)
        if res.get("error"):
            self.var_match.set(f"FEHLER: {res['error']}")
        elif res.get("matched"):
            self.var_match.set(f"TREFFER: {res.get('value')}")
            span = res.get("span")
            if isinstance(span, list) and len(span) == 2:
                self._highlight_span(int(span[0]), int(span[1]))
        else:
            self.var_match.set("KEIN TREFFER im Beispiel-Text.")

    def _on_add_custom(self) -> None:
        if not self.draft_path:
            return
        key = self.var_f_key.get().strip()
        regex = self.var_f_regex.get().strip()
        if not key or not regex:
            self.var_status.set("Feldname und Regex sind erforderlich.")
            return
        try:
            sf = self._build_search_from()
            add_field(self.draft_path, key, regex, required=self.var_f_required.get(), search_from=sf)
        except Exception as e:
            messagebox.showerror("Fehler", str(e), parent=self)
            return
        self._refresh_custom_count()
        self._clear_field_form()
        self.var_status.set(f"Feld '{key}' hinzugefuegt. Weiteres Feld anlegen oder 'Weiter' klicken.")

    # ------------------------------------------------------------ Schritt 5: Abschluss

    def _render_summary(self) -> None:
        self.list_summary.delete(0, tk.END)
        if not self.draft_path:
            return
        self._reload_fields()
        self.list_summary.insert(tk.END, f"Assay: {self.var_key.get().strip()}  {self.var_name.get().strip()}")
        self.list_summary.insert(tk.END, f"Felder: {len(self._fields)}")
        self.list_summary.insert(tk.END, f"Draft: {self.draft_path}")
        if self.assay_text.strip():
            try:
                req = check_required_fields(self.draft_path, self.assay_text, group=1)
                self._required_check = req
                self.lbl_required_summary.config(
                    text=(
                        f"Pflichtfelder: {req.get('confirmed', 0)}/{req.get('total', 0)} bestaetigt. "
                        + ("Alle Pflichtfelder haben Treffer." if req.get("all_confirmed") else "Aktivierung erst moeglich, wenn alle Pflichtfelder Treffer haben.")
                    ),
                    fg="#2f6b2f" if req.get("all_confirmed") else "#9a6700",
                )
                for row in req.get("results", []):
                    if not isinstance(row, dict):
                        continue
                    label = _REQUIRED_STATUS_LABELS.get(str(row.get("status", "")), str(row.get("status", "")))
                    self.list_summary.insert(tk.END, f"  Pflicht {row.get('key')}: {label}")
            except Exception as exc:
                self.lbl_required_summary.config(text=f"Pflichtfeld-Check fehlgeschlagen: {exc}", fg="#a33")
        try:
            report = validate_draft(self.draft_path)
        except Exception as e:
            self.list_summary.insert(tk.END, f"Validierung fehlgeschlagen: {e}")
            return
        if report.get("ok"):
            self.list_summary.insert(tk.END, "Validierung: OK")
        else:
            self.list_summary.insert(tk.END, f"Validierung: {len(report.get('errors', []))} Fehler")
            for err in report.get("errors", []):
                self.list_summary.insert(tk.END, f"  - {err}")

    def _finish(self) -> None:
        if not self.draft_path:
            self.destroy()
            return
        action = self.var_finish_action.get()
        if action == "activate" and self.assay_text.strip() and not self._required_fields_confirmed():
            messagebox.showwarning(
                "Pflichtfelder unvollstaendig",
                "Direkte Aktivierung ist blockiert, solange nicht alle Pflichtfelder "
                "einen Treffer im Beispieltext haben.\n\n"
                "Bitte Regex manuell pflegen und pruefen, oder den Draft im Editor oeffnen.",
                parent=self,
            )
            return
        draft = self.draft_path
        self.destroy()
        if action == "activate":
            self._on_activate_requested(draft)
        else:
            self._on_open_in_editor(draft)

    # ------------------------------------------------------------ Vorschau-Helfer

    def _set_preview_text(self, text: str) -> None:
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
        self.txt_preview.tag_remove("hit", "1.0", tk.END)

    def _highlight_span(self, start: int, end: int) -> None:
        start_idx = f"1.0+{start}c"
        end_idx = f"1.0+{end}c"
        self.txt_preview.tag_add("hit", start_idx, end_idx)
        self.txt_preview.see(start_idx)
