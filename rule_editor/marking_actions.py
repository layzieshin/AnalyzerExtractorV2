"""MarkingsMixin: interaktive Markierungs-Ansicht im PDF-Tab.

Felder werden im Assay-Text farbig markiert, eine Legende zeigt Treffer-Status,
und aus Textauswahlen lassen sich Regex- und search_from-Vorschlaege ableiten.
"""
from __future__ import annotations

import re
import tkinter as tk

from src.rulesuite.api import locate_fields

from .constants import FIELD_MARKING_COLORS as _FIELD_MARKING_COLORS


class MarkingsMixin:
    def _toggle_marking_panel(self) -> None:
        if self.frame_marking_panel is None or self.btn_toggle_markings is None:
            return
        if self._marking_panel_visible:
            self.frame_marking_panel.pack_forget()
            self._marking_panel_visible = False
            self.btn_toggle_markings.config(text="Markierungs-Ansicht einblenden")
        else:
            self.frame_marking_panel.pack(side="right", fill="y", padx=(8, 0))
            self._marking_panel_visible = True
            self.btn_toggle_markings.config(text="Markierungs-Ansicht ausblenden")
            self._render_field_markings()

    def _maybe_refresh_field_markings(self) -> None:
        if self._marking_panel_visible and self.assay_block_text and self.current_draft_path:
            self._render_field_markings()

    def _field_marking_tag(self, key: str) -> str:
        return f"field::{key}"

    def _clear_field_markings(self) -> None:
        for tag in list(self._field_marking_tags):
            self.txt_block.tag_remove(tag, "1.0", tk.END)
            self.txt_block.tag_unbind(tag, "<Button-1>")
        self._field_marking_tags.clear()
        self.txt_block.tag_remove("field_emphasis", "1.0", tk.END)
        self._field_marking_data.clear()
        self._active_marking_key = None
        if self.tree_marking_legend is not None:
            for row in self.tree_marking_legend.get_children():
                self.tree_marking_legend.delete(row)

    def _render_search_from_label(self, search_from: object) -> str:
        if not isinstance(search_from, dict):
            return "-"
        if "after" in search_from:
            return f"after: {search_from.get('after', '')}"
        if "line" in search_from:
            return f"line: {search_from.get('line', '')}"
        return "-"

    def _get_block_selection(self) -> dict[str, object] | None:
        try:
            if not self.txt_block.tag_ranges(tk.SEL):
                return None
            start_idx = self.txt_block.index(tk.SEL_FIRST)
            end_idx = self.txt_block.index(tk.SEL_LAST)
            selected = self.txt_block.get(start_idx, end_idx)
            if not selected.strip():
                return None

            line_start = self.txt_block.index(f"{start_idx} linestart")
            line_end = self.txt_block.index(f"{start_idx} lineend")
            line_text = self.txt_block.get(line_start, line_end)
            line_idx = int(str(start_idx).split(".")[0]) - 1
            # Text.count liefert je nach Tk-Version None (bei 0), int oder Tupel.
            raw_count = self.txt_block.count(line_start, start_idx, "chars")
            if isinstance(raw_count, (tuple, list)):
                sel_start_in_line = int(raw_count[0]) if raw_count else 0
            else:
                sel_start_in_line = int(raw_count or 0)
            return {
                "text": selected,
                "line_text": line_text,
                "line_idx": line_idx,
                "sel_start_in_line": sel_start_in_line,
                "sel_end_in_line": sel_start_in_line + len(selected),
            }
        except tk.TclError:
            return None

    def _suggest_regex_from_line_selection(self, line_text: str, selected: str) -> str:
        idx = line_text.find(selected)
        if idx < 0:
            if re.fullmatch(r"\d+", selected):
                return rf"(\d+)"
            if re.fullmatch(r"[\w.\-/]+", selected):
                return r"(\S+)"
            return re.escape(selected)

        before = line_text[:idx]
        after = line_text[idx + len(selected) :]

        def _part(text: str) -> str:
            if not text:
                return ""
            chunks = re.split(r"(\s+)", text)
            out: list[str] = []
            for chunk in chunks:
                if not chunk:
                    continue
                if chunk.isspace():
                    out.append(r"\s+")
                else:
                    out.append(re.escape(chunk))
            return "".join(out)

        if re.fullmatch(r"\d+", selected):
            cap = r"(\d+)"
        elif re.fullmatch(r"[\w.\-/]+", selected):
            cap = r"(\S+)"
        else:
            cap = f"({re.escape(selected)})"

        return _part(before) + cap + _part(after)

    def _on_block_selection_changed(self, _event: object = None) -> None:
        sel = self._get_block_selection()
        if sel is None:
            self.var_marking_selection.set("(keine Auswahl)")
            return
        preview = str(sel["text"]).replace("\n", " ").strip()
        if len(preview) > 90:
            preview = preview[:87] + "..."
        self.var_marking_selection.set(preview)

    def on_marking_regex_from_selection(self) -> None:
        sel = self._get_block_selection()
        if sel is None:
            self._set_hint("Bitte zuerst Text im Assay-Block markieren.")
            return
        regex = self._suggest_regex_from_line_selection(str(sel["line_text"]), str(sel["text"]))
        self.var_field_regex.set(regex)
        self._set_hint("Regex-Vorschlag aus Auswahl übernommen. Feldname prüfen und speichern.")

    def on_marking_set_search_line(self) -> None:
        sel = self._get_block_selection()
        if sel is None:
            self._set_hint("Bitte zuerst Text im Assay-Block markieren.")
            return
        self.var_search_mode.set("line")
        self.var_search_line.set(str(sel["line_idx"]))
        self.var_search_after.set("")
        self._set_hint(f"Suche ab Zeile {sel['line_idx']} gesetzt.")

    def on_marking_set_search_after_prev_line(self) -> None:
        sel = self._get_block_selection()
        if sel is None:
            self._set_hint("Bitte zuerst Text im Assay-Block markieren.")
            return
        line_idx = int(sel["line_idx"])
        if line_idx <= 0:
            self._set_hint("Keine Zeile davor vorhanden.")
            return
        lines = self.assay_block_text.splitlines()
        prev_line = lines[line_idx - 1]
        marker = re.escape(prev_line.strip())
        if not marker:
            self._set_hint("Vorherige Zeile ist leer.")
            return
        self.var_search_mode.set("after")
        self.var_search_after.set(marker)
        self.var_search_line.set("")
        self._set_hint("Suche ab: Marker aus Zeile davor gesetzt.")

    def _select_field_in_tree(self, key: str) -> None:
        for item in self.tree_fields.get_children():
            if str(self.tree_fields.item(item, "values")[0]) == key:
                # Nur setzen, wenn Selektion abweicht: selection_set erzeugt sonst
                # ein erneutes <<TreeviewSelect>>-Event (Endlosschleifen-Gefahr).
                if self.tree_fields.selection() != (item,):
                    self.tree_fields.selection_set(item)
                self.tree_fields.focus(item)
                self.tree_fields.see(item)
                return

    def _emphasize_field_marking(self, key: str) -> None:
        self.txt_block.tag_remove("field_emphasis", "1.0", tk.END)
        self._active_marking_key = key
        tag = self._field_marking_tag(key)
        ranges = self.txt_block.tag_ranges(tag)
        if ranges:
            self.txt_block.tag_add("field_emphasis", ranges[0], ranges[1])
            self.txt_block.see(ranges[0])
        if self.tree_marking_legend is not None:
            for item in self.tree_marking_legend.get_children():
                if self.tree_marking_legend.item(item, "text") == key:
                    # Idempotent: identische Selektion nicht erneut setzen,
                    # sonst feuert <<TreeviewSelect>> endlos weiter.
                    if self.tree_marking_legend.selection() != (item,):
                        self.tree_marking_legend.selection_set(item)
                    self.tree_marking_legend.focus(item)
                    self.tree_marking_legend.see(item)
                    break

    def on_marking_selected(self, key: str) -> None:
        if self._marking_sync_guard:
            return
        if key not in self._field_marking_data:
            return
        # Zustand bereits synchron -> nichts tun (bricht asynchrone Event-Ketten).
        if key == self._active_marking_key and self.var_field_key.get().strip() == key:
            return
        self._marking_sync_guard = True
        try:
            self._emphasize_field_marking(key)
            self._load_field_form_for_key(key)
            self._select_field_in_tree(key)
        finally:
            self._marking_sync_guard = False

    def on_marking_legend_selected(self, _event: object = None) -> None:
        if self.tree_marking_legend is None:
            return
        sel = self.tree_marking_legend.selection()
        if not sel:
            return
        key = str(self.tree_marking_legend.item(sel[0], "text"))
        self.on_marking_selected(key)

    def _render_field_markings(self) -> None:
        if not self._marking_panel_visible:
            return
        if not self.current_draft_path or not self.assay_block_text.strip():
            self._clear_field_markings()
            self.var_marking_status.set("Kein Assay-Text geladen.")
            return

        try:
            group = int(self.var_regex_group.get().strip() or "1")
        except ValueError:
            group = 1

        try:
            out = locate_fields(self.current_draft_path, self.assay_block_text, group=group)
        except Exception as e:
            self._clear_field_markings()
            self.var_marking_status.set(f"Markierungen fehlgeschlagen: {e}")
            return

        self._clear_field_markings()
        results = out.get("results", [])
        if not isinstance(results, list):
            results = []

        for idx, row in enumerate(results):
            if not isinstance(row, dict):
                continue
            key = str(row.get("key", "")).strip()
            if not key:
                continue

            color = _FIELD_MARKING_COLORS[idx % len(_FIELD_MARKING_COLORS)]
            tag = self._field_marking_tag(key)
            self.txt_block.tag_config(tag, background=color)
            self._field_marking_tags.add(tag)
            self._field_marking_data[key] = row

            matched = bool(row.get("matched"))
            value = str(row.get("value") or "").strip()
            error = str(row.get("error") or "").strip()
            if error:
                status = "FEHLER"
                display_value = error
            elif matched:
                status = "TREFFER"
                display_value = value if value else "(leer)"
            else:
                status = "KEIN TREFFER"
                display_value = "-"

            legend_tag = f"legend_{idx}"
            if self.tree_marking_legend is not None:
                self.tree_marking_legend.tag_configure(legend_tag, background=color)
                self.tree_marking_legend.insert(
                    "",
                    tk.END,
                    text=key,
                    values=(status, display_value),
                    tags=(legend_tag,),
                )

            span = row.get("span")
            if matched and isinstance(span, list) and len(span) == 2:
                start_idx = f"1.0+{int(span[0])}c"
                end_idx = f"1.0+{int(span[1])}c"
                self.txt_block.tag_add(tag, start_idx, end_idx)
                self.txt_block.tag_bind(tag, "<Button-1>", lambda _e, field_key=key: self.on_marking_selected(field_key))

        hits = int(out.get("hits", 0))
        total = int(out.get("total_fields", 0))
        self.var_marking_status.set(f"{hits} von {total} Feldern gefunden.")

        active_key = self.var_field_key.get().strip()
        if active_key and active_key in self._field_marking_data:
            self._emphasize_field_marking(active_key)
        if active_key:
            self._update_field_guidance(active_key)

    def on_goto_field_marking(self) -> None:
        """Springt in den PDF-Tab, um die Fundstelle eines Feldes zu zeigen oder zu hinterlegen."""
        key = self.var_field_key.get().strip()
        if not key:
            self._set_hint("Bitte zuerst ein Feld auswaehlen.")
            return
        self._select_tab("pdf")
        if not self._marking_panel_visible:
            self._toggle_marking_panel()
        else:
            self._maybe_refresh_field_markings()
        row = self._field_marking_data.get(key)
        if row is not None and row.get("matched"):
            self._emphasize_field_marking(key)
            self._set_hint(f"Fundstelle fuer '{key}' ist im Text hervorgehoben.")
        else:
            self._set_hint(
                f"'{key}' hat noch keine Fundstelle: Text markieren, 'Regex aus Auswahl' bzw. "
                "'Suche ab' setzen und 'Feld uebernehmen' klicken."
            )
