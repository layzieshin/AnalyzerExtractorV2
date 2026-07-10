"""Small Tk popup for backend-driven regex builder specs."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable

from src.rulesuite.api import build_regex_from_builder_spec, suggest_builder_spec_from_selection, test_regex


class RegexBuilderPopup(tk.Toplevel):
    def __init__(
        self,
        master: tk.Misc,
        *,
        assay_text: str,
        selection: dict[str, object] | None,
        on_accept: Callable[[str, dict[str, Any] | None], None],
    ) -> None:
        super().__init__(master)
        self.title("Regex-Baustein")
        self.geometry("760x560")
        self.transient(master)
        self._assay_text = assay_text
        self._on_accept = on_accept
        self._last_result: dict[str, Any] | None = None

        spec = self._initial_spec(selection)
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
        self.var_expected = tk.StringVar(value=str(spec.get("expected_value", "")))
        self.var_use_search_from = tk.BooleanVar(value=bool(spec.get("line_index", "")))

        self._build_ui()
        self._build_regex()

    def _initial_spec(self, selection: dict[str, object] | None) -> dict[str, Any]:
        if not selection:
            return {"value_type": "auto"}
        out = suggest_builder_spec_from_selection(
            str(selection.get("line_text", "")),
            str(selection.get("text", "")),
            selection_start=int(selection.get("sel_start_in_line", 0)),
            selection_end=int(selection.get("sel_end_in_line", 0)),
            line_index=int(selection.get("line_idx", -1)),
        )
        spec = out.get("spec", {})
        return spec if isinstance(spec, dict) else {"value_type": "auto"}

    def _build_ui(self) -> None:
        intro = tk.Label(
            self,
            text=(
                "Optionale Bausteine setzen. Der Builder erzeugt nur einen Regex; "
                "im Ruleset wird keine Baustein-Spec gespeichert."
            ),
            anchor="w",
            justify="left",
            wraplength=720,
            fg="#444",
        )
        intro.pack(fill="x", padx=10, pady=(10, 6))

        form = tk.LabelFrame(self, text="Bausteine")
        form.pack(fill="x", padx=10, pady=(0, 8))
        form.columnconfigure(1, weight=1)
        form.columnconfigure(4, weight=1)

        self._entry_row(form, 0, "Zeile enthaelt", self.var_line_contains, self.var_line_contains_regex)
        self._entry_row(form, 1, "Zeile beginnt", self.var_line_startswith, self.var_line_startswith_regex)
        tk.Label(form, text="Zeilennummer").grid(row=2, column=0, sticky="w", padx=(6, 4), pady=(0, 4))
        tk.Entry(form, textvariable=self.var_line_index, width=10).grid(row=2, column=1, sticky="w", pady=(0, 4))
        tk.Checkbutton(form, text="als search_from uebernehmen", variable=self.var_use_search_from).grid(
            row=2, column=2, columnspan=3, sticky="w", padx=(8, 6), pady=(0, 4)
        )

        self._marker_row(
            form,
            3,
            "Nach Marker",
            self.var_left_marker,
            self.var_left_occurrence,
            self.var_left_regex,
        )
        self._marker_row(
            form,
            4,
            "Vor Marker",
            self.var_right_marker,
            self.var_right_occurrence,
            self.var_right_regex,
        )

        tk.Label(form, text="Werttyp").grid(row=5, column=0, sticky="w", padx=(6, 4), pady=(0, 6))
        ttk.Combobox(
            form,
            textvariable=self.var_value_type,
            values=["auto", "text", "token", "decimal", "range", "value_with_unit", "asy_filename", "validation_status"],
            width=20,
            state="readonly",
        ).grid(row=5, column=1, sticky="w", pady=(0, 6))
        tk.Label(form, text="Treffer Nr.").grid(row=5, column=2, sticky="w", padx=(8, 4), pady=(0, 6))
        tk.Entry(form, textvariable=self.var_match_index, width=8).grid(row=5, column=3, sticky="w", pady=(0, 6))

        tk.Label(form, text="Erwartet").grid(row=6, column=0, sticky="w", padx=(6, 4), pady=(0, 6))
        tk.Entry(form, textvariable=self.var_expected).grid(row=6, column=1, columnspan=4, sticky="we", pady=(0, 6), padx=(0, 6))

        btns = tk.Frame(self)
        btns.pack(fill="x", padx=10, pady=(0, 8))
        tk.Button(btns, text="Regex bauen", command=self._build_regex).pack(side="left")
        tk.Button(btns, text="Testen", command=self._test_regex).pack(side="left", padx=(6, 0))
        tk.Button(btns, text="Uebernehmen", command=self._accept).pack(side="left", padx=(6, 0))
        tk.Button(btns, text="Schliessen", command=self.destroy).pack(side="right")

        self.txt_result = tk.Text(self, wrap="word", height=14)
        self.txt_result.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.txt_result.configure(state="disabled")

    def _entry_row(self, parent: tk.Widget, row: int, label: str, var: tk.StringVar, regex_var: tk.BooleanVar) -> None:
        tk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(6, 4), pady=(6 if row == 0 else 0, 4))
        tk.Entry(parent, textvariable=var).grid(
            row=row,
            column=1,
            columnspan=3,
            sticky="we",
            pady=(6 if row == 0 else 0, 4),
        )
        tk.Checkbutton(parent, text="als Regex", variable=regex_var).grid(
            row=row,
            column=4,
            sticky="w",
            padx=(8, 6),
            pady=(6 if row == 0 else 0, 4),
        )

    def _marker_row(
        self,
        parent: tk.Widget,
        row: int,
        label: str,
        marker_var: tk.StringVar,
        occurrence_var: tk.StringVar,
        regex_var: tk.BooleanVar,
    ) -> None:
        tk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(6, 4), pady=(0, 4))
        tk.Entry(parent, textvariable=marker_var).grid(row=row, column=1, sticky="we", pady=(0, 4))
        tk.Label(parent, text="Vorkommen").grid(row=row, column=2, sticky="w", padx=(8, 4), pady=(0, 4))
        tk.Entry(parent, textvariable=occurrence_var, width=8).grid(row=row, column=3, sticky="w", pady=(0, 4))
        tk.Checkbutton(parent, text="als Regex", variable=regex_var).grid(row=row, column=4, sticky="w", padx=(8, 6), pady=(0, 4))

    def _spec(self) -> dict[str, Any]:
        return {
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
            "expected_value": self.var_expected.get().strip(),
        }

    def _build_regex(self) -> dict[str, Any]:
        self._last_result = build_regex_from_builder_spec(self._spec())
        self._render_result(self._last_result)
        return self._last_result

    def _test_regex(self) -> None:
        result = self._build_regex()
        regex = str(result.get("regex", ""))
        test = test_regex(self._assay_text, regex, group=1) if self._assay_text.strip() else {"error": "no_assay_text"}
        result = dict(result)
        result["test"] = test
        self._last_result = result
        self._render_result(result)

    def _render_result(self, result: dict[str, Any]) -> None:
        lines = [
            "Regex:",
            str(result.get("regex", "")),
            "",
            f"Capture: {result.get('capture', '')}",
        ]
        proposed = result.get("proposed_search_from")
        if proposed:
            lines.append(f"search_from Vorschlag: {proposed}")
        warnings = result.get("warnings") or []
        lines.append("Warnungen: " + (", ".join(str(w) for w in warnings) if warnings else "keine"))

        test = result.get("test")
        if isinstance(test, dict):
            lines.extend(["", "Test:"])
            if test.get("error"):
                lines.append(f"FEHLER: {test.get('error')}")
            elif test.get("matched"):
                value = str(test.get("value") or "")
                lines.append(f"HIT: {value}")
                expected = self.var_expected.get().strip()
                if expected:
                    lines.append("Vergleich: " + ("OK" if value == expected else f"abweichend (erwartet {expected})"))
            else:
                lines.append("MISS")

        self.txt_result.configure(state="normal")
        self.txt_result.delete("1.0", tk.END)
        self.txt_result.insert(tk.END, "\n".join(lines))
        self.txt_result.configure(state="disabled")

    def _accept(self) -> None:
        result = self._last_result or self._build_regex()
        regex = str(result.get("regex", ""))
        search_from = result.get("proposed_search_from") if self.var_use_search_from.get() else None
        self._on_accept(regex, search_from if isinstance(search_from, dict) else None)
        self.destroy()
