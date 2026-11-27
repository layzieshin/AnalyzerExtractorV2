"""Small Tk popup for backend-driven regex builder specs."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable


class RegexBuilderPopup(tk.Toplevel):
    def __init__(
        self,
        master: tk.Misc,
        *,
        rules: object,
        assay_text: str,
        selection: dict[str, object] | None,
        on_accept: Callable[[str, dict[str, Any] | None], None],
        field_key: str = "",
    ) -> None:
        super().__init__(master)
        self.title("Regex-Baukasten")
        width, height = min(1100, max(760, master.winfo_toplevel().winfo_width() - 20)), min(590, max(510, master.winfo_toplevel().winfo_height() - 40))
        self.geometry(f"{width}x{height}")
        self.minsize(760, 510)
        self._field_key = field_key
        self.transient(master.winfo_toplevel())
        self._rules = rules
        self._assay_text = assay_text
        self._on_accept = on_accept
        self._last_result: dict[str, Any] | None = None

        spec = self._initial_spec(selection)
        initial_mode = "line" if str(spec.get("line_index", "")).strip() else "none"
        self.var_search_anchor_mode = tk.StringVar(value=str(spec.get("search_anchor_mode", initial_mode)))
        self.var_search_anchor = tk.StringVar(value=str(spec.get("search_anchor", "")))
        self.var_search_anchor_regex = tk.BooleanVar(value=bool(spec.get("search_anchor_is_regex", False)))
        self.var_line_contains = tk.StringVar(value=str(spec.get("line_contains", "")))
        self.var_line_contains_regex = tk.BooleanVar(value=bool(spec.get("line_contains_is_regex", False)))
        self.var_line_startswith = tk.StringVar(value=str(spec.get("line_startswith", "")))
        self.var_line_startswith_regex = tk.BooleanVar(value=bool(spec.get("line_startswith_is_regex", False)))
        self.var_line_index = tk.StringVar(value=str(spec.get("line_index", "")))
        self.var_left_marker = tk.StringVar(value=str(spec.get("left_marker", "")))
        self.var_left_occurrence = tk.StringVar(value=str(spec.get("left_marker_occurrence", "")))
        self.var_left_regex = tk.BooleanVar(value=bool(spec.get("left_marker_is_regex", False)))
        self.var_right_marker = tk.StringVar(value=str(spec.get("right_marker", "")))
        self.var_right_occurrence = tk.StringVar(value=str(spec.get("right_marker_occurrence", "")))
        self.var_right_regex = tk.BooleanVar(value=bool(spec.get("right_marker_is_regex", False)))
        self.var_value_type = tk.StringVar(value=str(spec.get("value_type", "auto")))
        self.var_match_index = tk.StringVar(value=str(spec.get("match_index", "")))
        self.var_value_min_len = tk.StringVar(value="")
        self.var_value_max_len = tk.StringVar(value="")
        self.var_expected = tk.StringVar(value=str(spec.get("expected_value", "")))
        self.var_use_search_from = tk.BooleanVar(value=self.var_search_anchor_mode.get() != "none")

        self._build_ui()
        self._build_regex()
        self.grab_set()

    def _initial_spec(self, selection: dict[str, object] | None) -> dict[str, Any]:
        if not selection:
            return {"value_type": "auto"}
        out = self._rules.suggest_builder_spec_from_selection(
            str(selection.get("line_text", "")),
            str(selection.get("text", "")),
            selection_start=int(selection.get("sel_start_in_line", 0)),
            selection_end=int(selection.get("sel_end_in_line", 0)),
            line_index=int(selection.get("line_idx", -1)),
        )
        spec = out.get("spec", {})
        return spec if isinstance(spec, dict) else {"value_type": "auto"}

    def _build_ui(self) -> None:
        from interfaces.tk.widgets.common import Card
        from .toolbar import _configure_button_styles
        _configure_button_styles(self)
        style = ttk.Style(self)
        compact = self.master.winfo_toplevel().winfo_height() < 650 or self.master.winfo_toplevel().winfo_width() < 1000
        size = 8 if compact else 9
        style.configure("Builder.TLabel", background="#ffffff", foreground="#486272", font=("Segoe UI", size))
        style.configure("BuilderTitle.TLabel", background="#ffffff", foreground="#185a71", font=("Segoe UI", 9, "bold"))
        style.configure("Builder.TEntry", padding=(4, 2))
        style.configure("Builder.TCombobox", padding=(4, 2))
        style.configure("Builder.TCheckbutton", font=("Segoe UI", size), padding=0)
        self.configure(background="#f1f5f8")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        header = ttk.Frame(self, style="CardInner.TFrame", padding=(14, 8))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text=f"REGELWERKSTATT · FELD {self._field_key}", style="Eyebrow.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, text="Regex-Baukasten", style="SectionTitle.TLabel").grid(row=1, column=0, sticky="w")
        ttk.Button(header, text="×", command=self.destroy, width=0, style="RuleSuite.Secondary.TButton").grid(row=0, column=1, rowspan=2, sticky="e")
        inside = ttk.Frame(self, style="Content.TFrame", padding=(10, 6))
        inside.grid(row=1, column=0, sticky="nsew")
        inside.columnconfigure((0, 1), weight=1, uniform="groups")
        self._builder_inputs = {}
        def group(title, row, column):
            card = Card(inside, rounded=True, padding=8)
            card.body.pack_configure(padx=8, pady=(3, 3) if compact else (6, 8))
            card.grid(row=row, column=column, sticky="nsew", padx=(0, 6) if column == 0 else 0, pady=(0, 6))
            card.body.columnconfigure((0, 1), weight=1, uniform="pair")
            ttk.Label(card.body, text=title, style="BuilderTitle.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 1 if compact else 3))
            return card.body
        def field(parent, label, variable, name, row, column=0, span=1, values=None):
            cell = ttk.Frame(parent, style="CardInner.TFrame")
            cell.grid(row=row, column=column, columnspan=span, sticky="ew", padx=(0, 6) if column == 0 and span == 1 else 0, pady=(0, 1 if compact else 3))
            cell.columnconfigure(0, weight=1)
            ttk.Label(cell, text=label, style="Builder.TLabel").grid(row=0, column=0, sticky="w")
            control = ttk.Combobox(cell, textvariable=variable, values=values, state="readonly", width=1, font=("Segoe UI", size), style="Builder.TCombobox") if values else ttk.Entry(cell, textvariable=variable, width=1, font=("Segoe UI", size), style="Builder.TEntry")
            control.grid(row=1, column=0, sticky="ew")
            self._builder_inputs[name] = control
            return control
        def flag(parent, text, variable, name, row, column=1, span=1):
            control = ttk.Checkbutton(parent, text=text, variable=variable, style="Builder.TCheckbutton")
            control.grid(row=row, column=column, columnspan=span, sticky="w", pady=(0, 2))
            self._builder_inputs[name] = control
            return control
        mode_labels = {"none": "Gesamter Text", "after": "Nach Textmarker", "line": "Ab Zeile"}
        type_labels = {"auto": "Automatisch", "text": "Text", "token": "Token", "decimal": "Dezimalzahl",
                       "range": "Bereich", "value_with_unit": "Wert mit Einheit", "asy_filename": "ASY-Dateiname", "validation_status": "Validierungsstatus"}
        self.var_search_mode_label = tk.StringVar(master=self, value=mode_labels.get(self.var_search_anchor_mode.get(), "Gesamter Text"))
        self.var_value_type_label = tk.StringVar(master=self, value=type_labels.get(self.var_value_type.get(), "Automatisch"))
        self.var_search_anchor_mode.trace_add("write", lambda *_: self.var_search_mode_label.set(mode_labels.get(self.var_search_anchor_mode.get(), "Gesamter Text")))
        self.var_value_type.trace_add("write", lambda *_: self.var_value_type_label.set(type_labels.get(self.var_value_type.get(), "Automatisch")))
        search = group("01 · Suchbereich", 0, 0)
        mode = field(search, "Modus", self.var_search_mode_label, "search_anchor_mode", 1, values=tuple(mode_labels.values()))
        mode.bind("<<ComboboxSelected>>", lambda _event: self.var_search_anchor_mode.set(next(key for key, value in mode_labels.items() if value == self.var_search_mode_label.get())))
        field(search, "Zeile", self.var_line_index, "line_index", 1, 1)
        anchor = ttk.Frame(search, style="CardInner.TFrame")
        anchor.grid(row=2, column=0, columnspan=2, sticky="ew")
        anchor.columnconfigure(0, weight=1)
        field(anchor, "Suchwort / Marker", self.var_search_anchor, "search_anchor", 0)
        flag(anchor, "als Regex", self.var_search_anchor_regex, "search_anchor_is_regex", 0)
        flag(search, "Suchbereich als search_from übernehmen", self.var_use_search_from, "use_search_from", 3, 0, 2)
        filters = group("02 · Zeilenfilter", 0, 1)
        for row, label, variable, check, name in ((1, "Zeile enthält", self.var_line_contains, self.var_line_contains_regex, "line_contains"),
                                                (2, "Zeile beginnt mit", self.var_line_startswith, self.var_line_startswith_regex, "line_startswith")):
            cell = ttk.Frame(filters, style="CardInner.TFrame")
            cell.grid(row=row, column=0, columnspan=2, sticky="ew")
            cell.columnconfigure(0, weight=1)
            field(cell, label, variable, name, 0)
            flag(cell, "als Regex", check, name + "_is_regex", 0)
        markers = group("03 · Begrenzende Marker", 1, 0)
        for row, label, variable, occurrence, check, name in ((1, "Nach Marker", self.var_left_marker, self.var_left_occurrence, self.var_left_regex, "left_marker"),
                                                             (2, "Vor Marker", self.var_right_marker, self.var_right_occurrence, self.var_right_regex, "right_marker")):
            cell = ttk.Frame(markers, style="CardInner.TFrame")
            cell.grid(row=row, column=0, columnspan=2, sticky="ew")
            cell.columnconfigure((0, 1), weight=1, uniform="marker")
            field(cell, label, variable, name, 0)
            field(cell, "Vorkommen", occurrence, name + "_occurrence", 0, 1)
            flag(cell, "als Regex", check, name + "_is_regex", 0, 2)
        value = group("04 · Wert und Erwartung", 1, 1)
        value_type = field(value, "Werttyp", self.var_value_type_label, "value_type", 1, values=tuple(type_labels.values()))
        value_type.bind("<<ComboboxSelected>>", lambda _event: self.var_value_type.set(next(key for key, label in type_labels.items() if label == self.var_value_type_label.get())))
        field(value, "Treffer-Nr.", self.var_match_index, "match_index", 1, 1)
        field(value, "Min. Wertlänge", self.var_value_min_len, "value_min_len", 2)
        field(value, "Max. Wertlänge", self.var_value_max_len, "value_max_len", 2, 1)
        field(value, "Erwarteter Testwert", self.var_expected, "expected_value", 3, 0, 2)
        output = Card(inside, rounded=True, padding=8)
        output.body.pack_configure(padx=8, pady=(3, 3) if compact else (6, 8))
        output.grid(row=2, column=0, columnspan=2, sticky="nsew")
        output.body.columnconfigure((0, 1), weight=1, uniform="result")
        inside.rowconfigure(2, weight=1)
        ttk.Label(output.body, text="Vorschau · Regex & Capture", style="BuilderTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(output.body, text="Testergebnis", style="BuilderTitle.TLabel").grid(row=0, column=1, sticky="w")
        self.txt_result = tk.Text(output.body, height=2, width=10, wrap="word", font=("Consolas", 9), relief="flat", background="#ffffff", foreground="#23485e", takefocus=True)
        self.txt_result.grid(row=1, column=0, sticky="ew", padx=(0, 8))
        self.var_capture = tk.StringVar(master=self)
        self.var_test_result = tk.StringVar(master=self, value="Noch nicht getestet")
        self.var_test_note = tk.StringVar(master=self)
        self.var_comparison = tk.StringVar(master=self)
        capture = ttk.Label(output.body, textvariable=self.var_capture, style="Builder.TLabel")
        capture.grid(row=2, column=0, sticky="ew", padx=(0, 8))
        ttk.Label(output.body, textvariable=self.var_test_result, foreground="#126854", background="#ffffff").grid(row=1, column=1, sticky="w")
        note = ttk.Label(output.body, textvariable=self.var_test_note, style="Builder.TLabel")
        note.grid(row=2, column=1, sticky="ew")
        comparison = ttk.Label(output.body, textvariable=self.var_comparison, style="Builder.TLabel")
        comparison.grid(row=3, column=1, sticky="ew")
        output.body.bind("<Configure>", lambda event: [label.configure(wraplength=max(150, event.width // 2 - 20)) for label in (capture, note, comparison)])
        footer = ttk.Frame(self, style="CardInner.TFrame", padding=(12, 7))
        footer.grid(row=2, column=0, sticky="ew")
        self.btn_build = ttk.Button(footer, text="Regex bauen", command=self._build_regex, style="RuleSuite.Secondary.TButton", width=0)
        self.btn_build.pack(side="left")
        self.btn_test = ttk.Button(footer, text="Testen", command=self._test_regex, style="RuleSuite.Secondary.TButton", width=0)
        self.btn_test.pack(side="left", padx=6)
        self.btn_accept = ttk.Button(footer, text="Übernehmen", command=self._accept, style="RuleSuite.Primary.TButton", width=0)
        self.btn_accept.pack(side="right")
        ttk.Button(footer, text="Schließen", command=self.destroy, style="RuleSuite.Secondary.TButton", width=0).pack(side="right", padx=6)
        self.bind("<Escape>", lambda _event: self.destroy())

    def _spec(self) -> dict[str, Any]:
        return {
            "search_anchor_mode": self.var_search_anchor_mode.get().strip(),
            "search_anchor": self.var_search_anchor.get().strip(),
            "search_anchor_is_regex": self.var_search_anchor_regex.get(),
            "line_contains": self.var_line_contains.get().strip(),
            "line_contains_is_regex": self.var_line_contains_regex.get(),
            "line_startswith": self.var_line_startswith.get().strip(),
            "line_startswith_is_regex": self.var_line_startswith_regex.get(),
            "line_index": self.var_line_index.get().strip(),
            "left_marker": self.var_left_marker.get().strip(),
            "left_marker_occurrence": self.var_left_occurrence.get().strip(),
            "left_marker_is_regex": self.var_left_regex.get(),
            "right_marker": self.var_right_marker.get().strip(),
            "right_marker_occurrence": self.var_right_occurrence.get().strip(),
            "right_marker_is_regex": self.var_right_regex.get(),
            "value_type": self.var_value_type.get().strip(),
            "match_index": self.var_match_index.get().strip(),
            "value_min_len": self.var_value_min_len.get().strip(),
            "value_max_len": self.var_value_max_len.get().strip(),
            "expected_value": self.var_expected.get().strip(),
        }

    def _build_regex(self) -> dict[str, Any]:
        self._last_result = self._rules.build_regex_from_builder_spec(self._spec())
        self._render_result(self._last_result)
        return self._last_result

    def _test_regex(self) -> None:
        result = self._build_regex()
        regex = str(result.get("regex", ""))
        search_from = None
        if self.var_use_search_from.get():
            proposed = result.get("proposed_search_from")
            if isinstance(proposed, dict):
                search_from = proposed
        if self._assay_text.strip():
            test = self._rules.test_regex(self._assay_text, regex, group=1, search_from=search_from)
        else:
            test = {"error": "no_assay_text"}
        result = dict(result)
        result["test"] = test
        if search_from is not None:
            result["test_search_from"] = search_from
        self._last_result = result
        self._render_result(result)

    def _render_result(self, result: dict[str, Any]) -> None:
        self.txt_result.configure(state="normal")
        self.txt_result.delete("1.0", tk.END)
        self.txt_result.insert(tk.END, str(result.get("regex", "")))
        self.txt_result.configure(state="disabled")
        proposed = result.get("proposed_search_from")
        self.var_capture.set(f"Capture: {result.get('capture', '')}" + (f" · Suchvorschlag: {proposed}" if proposed else ""))
        warnings = result.get("warnings") or []
        note = "Warnungen: " + ", ".join(str(item) for item in warnings) if warnings else "Keine Warnungen"
        context = result.get("test_search_from")
        if isinstance(context, dict):
            note += f" · ab Zeile {context['line']}" if "line" in context else f" · nach {context.get('after', '')}"
        self.var_test_note.set(note)
        test = result.get("test")
        self.var_comparison.set("")
        if not isinstance(test, dict):
            self.var_test_result.set("Noch nicht getestet")
        elif test.get("error"):
            self.var_test_result.set(f"Fehler · {test['error']}")
        elif test.get("matched"):
            raw = test.get("value")
            value = "" if raw is None else str(raw)
            self.var_test_result.set(f"Treffer · {value}")
            expected = self.var_expected.get().strip()
            if expected:
                self.var_comparison.set("Erwartung erfüllt" if value == expected else f"Abweichung · erwartet {expected}")
        else:
            self.var_test_result.set("Kein Treffer")

    def _accept(self) -> None:
        result = self._build_regex()
        regex = str(result.get("regex", ""))
        search_from = result.get("proposed_search_from") if self.var_use_search_from.get() else None
        self._on_accept(regex, search_from if isinstance(search_from, dict) else None)
        self.destroy()
