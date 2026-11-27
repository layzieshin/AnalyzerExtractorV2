"""Document presentation and transient proof values; no file or domain work."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from tkinter import font

from interfaces.tk.widgets.common import OverflowScrollbar, StatusBadge, create_scrollable_tree
from .toolbar import _ActionFlow


class _DocumentStack(ttk.Frame):
    """Two document surfaces with exactly one visible, external tab control."""
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self._pages, self._selected = [], None
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
    def add(self, frame, **_kwargs):
        self._pages.append(frame)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.grid_remove()
        if self._selected is None:
            self.select(frame)
    def select(self, frame=None):
        if frame is None:
            return str(self._selected)
        self._selected = frame
        for page in self._pages:
            page.grid() if str(page) == str(frame) else page.grid_remove()


def build_authoring_result(host, parent) -> None:
    for index, label in enumerate(("Test-PDF", "Automatische Zweitprüfung")):
        row = ttk.Frame(parent, style="CardInner.TFrame")
        row.pack(fill="x", pady=(4, 0))
        ttk.Label(row, text=label, font=("Segoe UI", 9)).pack(side="left")
        badge = StatusBadge(row, "Nicht geprüft" if index == 0 else "Offen")
        badge.configure(font=("Segoe UI", 9))
        badge.pack(side="right")
        if index == 0:
            host.lbl_primary_result = badge
        else:
            host.lbl_secondary_result = badge
    outer = ttk.Frame(parent, style="CardInner.TFrame")
    host.authoring_values_frame = host.authoring_result_tab = outer
    frame, host.tree_authoring_values = create_scrollable_tree(outer, ("field", "primary", "secondary"),
        ("Feld", "Test-PDF", "Zweitprüfung"), height=3, autohide=True)
    frame.pack(fill="both", expand=True)
    host.var_proof_detail = tk.StringVar(master=host, value="Noch nicht geprüft")
    ttk.Label(outer, textvariable=host.var_proof_detail, wraplength=260, style="Muted.TLabel").pack(fill="x", pady=4)
    for column, width, minimum in (("field", 70, 50), ("primary", 85, 65), ("secondary", 100, 80)):
        host.tree_authoring_values.column(column, width=width, minwidth=minimum, stretch=True)


def clear_authoring_result(host, message="Noch nicht geprüft") -> None:
    host.lbl_primary_result.set_status("Läuft …" if "läuft" in message else "Nicht geprüft")
    host.lbl_secondary_result.set_status("Offen")
    if hasattr(host, "var_proof_detail"):
        host.var_proof_detail.set(message)
    for row in host.tree_authoring_values.get_children():
        host.tree_authoring_values.delete(row)


def render_authoring_result(host, proof) -> None:
    clear_authoring_result(host)
    primary, secondary = proof.get("primary", {}), proof.get("secondary", {})
    host.lbl_primary_result.set_status("Bestanden" if primary.get("status") == "passed" else "Fehlgeschlagen",
        kind="success" if primary.get("status") == "passed" else "error")
    second = secondary.get("status")
    host.lbl_secondary_result.set_status("Bestanden" if second == "passed" else "Offen" if second == "not_available" else "Fehlgeschlagen",
        kind="success" if second == "passed" else "warning" if second == "not_available" else "error")
    if hasattr(host, "var_proof_detail"):
        host.var_proof_detail.set("Einmal geprüft – Zweitprüfung noch offen" if second == "not_available" else "Automatische Zweitprüfung bestanden" if second == "passed" else "Zweitprüfung fehlgeschlagen")
    first_values, second_values = primary.get("data", {}), secondary.get("data", {})
    keys = tuple(dict.fromkeys((*primary.get("field_keys", ()), *first_values, *secondary.get("field_keys", ()), *second_values)))
    for key in keys:
        def shown(values, outcome):
            if key not in values:
                return "Nicht geprüft" if outcome.get("status") == "not_available" else "—"
            return "(leer)" if values[key] is None or values[key] == "" else str(values[key])
        host.tree_authoring_values.insert("", "end", values=(key, shown(first_values, primary), shown(second_values, secondary)))


def build_report_panel(host, parent) -> None:
    parent.rowconfigure(2, weight=1)
    parent.columnconfigure(0, weight=1)
    head = ttk.Frame(parent, style="CardInner.TFrame", padding=(10, 8))
    head.grid(row=0, column=0, sticky="ew")
    head.columnconfigure(0, weight=1)
    host.var_pdf_filename = tk.StringVar(master=host, value="Keine Test-PDF gewählt")
    host.ent_test_pdf = ttk.Label(head, textvariable=host.var_pdf_filename, style="ToolbarTitle.TLabel", width=1)
    host.ent_test_pdf.grid(row=0, column=0, sticky="ew", padx=(0, 8))
    ttk.Button(head, text="PDF laden", command=host.on_pick_pdf, style="Doc.RuleSuite.Secondary.TButton", width=0).grid(row=0, column=1)
    tabs = _ActionFlow(head)
    tabs.grid(row=0, column=2, sticky="e", padx=(6, 0))
    host.btn_document_text = tabs.add("Assay-Text", lambda: host.show_document_view("text"), style="Doc.RuleSuite.Selected.TButton", width=0)
    host.btn_document_pdf = tabs.add("Original-PDF", lambda: host.show_document_view("pdf"), style="Doc.RuleSuite.Secondary.TButton", width=0)
    tabs.configure(width=sum(widget.winfo_reqwidth() + 6 for widget in tabs._controls))
    host._document_filename_full = ""
    tooltip = [None]
    def hide_name(_event=None):
        if tooltip[0] is not None:
            tooltip[0].destroy()
            tooltip[0] = None
    def show_name(_event=None):
        hide_name()
        if host.var_pdf_filename.get() == host._document_filename_full or not host._document_filename_full:
            return
        popup = tk.Toplevel(host)
        popup.overrideredirect(True)
        popup.geometry(f"+{host.ent_test_pdf.winfo_rootx()}+{host.ent_test_pdf.winfo_rooty() + host.ent_test_pdf.winfo_height()}")
        ttk.Label(popup, text=host._document_filename_full, padding=6, wraplength=500).pack()
        tooltip[0] = popup
    def fit_filename(_event=None):
        full = host.var_pdf.get().replace("\\", "/").rsplit("/", 1)[-1] or "Keine Test-PDF gewählt"
        host._document_filename_full = full
        available = max(25, host.ent_test_pdf.winfo_width())
        measure = font.Font(root=host, font=host.ent_test_pdf.cget("font") or ttk.Style(host).lookup("ToolbarTitle.TLabel", "font"))
        shown = full
        while len(shown) > 1 and measure.measure(shown) > available:
            shown = shown[:-2] + "…" if shown.endswith("…") else shown[:-1] + "…"
        host.var_pdf_filename.set(shown)
    host.ent_test_pdf.bind("<Configure>", fit_filename, add="+")
    host.var_pdf.trace_add("write", lambda *_: host.after_idle(fit_filename))
    host.ent_test_pdf.bind("<Enter>", show_name)
    host.ent_test_pdf.bind("<Leave>", hide_name)
    host.var_document_note = tk.StringVar(master=host, value="Extrahierter Assay-Abschnitt · Text zum Erstellen einer Regel markieren")
    note = ttk.Label(parent, textvariable=host.var_document_note, style="Muted.TLabel", padding=(10, 6))
    note.grid(row=1, column=0, sticky="ew")
    parent.bind("<Configure>", lambda event: note.configure(wraplength=max(140, event.width - 24)), add="+")
    style = ttk.Style(host)
    host.report_notebook = _DocumentStack(parent, style="CardInner.TFrame")
    host.report_notebook.grid(row=2, column=0, sticky="nsew")
    text_wrap = ttk.Frame(host.report_notebook, style="CardInner.TFrame")
    host.document_text_frame = text_wrap
    host.report_notebook.add(text_wrap, text="Assay-Text")
    text_wrap.rowconfigure(0, weight=1)
    text_wrap.columnconfigure(1, weight=1)
    gutter = tk.Canvas(text_wrap, width=34, borderwidth=0, highlightthickness=0, background="#fcfdfe")
    gutter.grid(row=0, column=0, sticky="ns")
    host.txt_block = tk.Text(text_wrap, wrap="word", width=20, height=4, font=("Consolas", 10),
        relief="flat", padx=7, pady=8, foreground="#16293c", background="#fcfdfe", undo=False, spacing1=3, spacing3=3)
    host.txt_block.grid(row=0, column=1, sticky="nsew")
    bar = OverflowScrollbar(text_wrap, orient="vertical", command=host.txt_block.yview)
    def numbers(_event=None):
        gutter.delete("all")
        line = int(host.txt_block.index("@0,0").split(".")[0])
        while True:
            position = host.txt_block.dlineinfo(f"{line}.0")
            if position is None:
                break
            gutter.create_text(29, position[1] + position[3] / 2, anchor="e", text=f"{line:02d}", fill="#78909c", font=("Consolas", 9))
            line += 1
    def scrolled(first, last):
        bar.set(first, last)
        numbers()
    host.txt_block.configure(yscrollcommand=scrolled)
    host.txt_block.bind("<Configure>", numbers, add="+")
    host.txt_block.tag_config("hit", background="#cdece0")
    host.txt_block.tag_config("field_emphasis", background="#bee3d4")
    host.txt_block.bind("<<Selection>>", host._on_block_selection_changed)
    host.document_pdf_frame = ttk.Frame(host.report_notebook, style="CardInner.TFrame")
    host.report_notebook.add(host.document_pdf_frame, text="Original-PDF")
    pdf = host.document_pdf_frame
    pdf.columnconfigure(0, weight=1)
    pdf.rowconfigure(1, weight=1)
    controls = _ActionFlow(pdf)
    controls.grid(row=0, column=0, sticky="ew", padx=6, pady=3)
    host.btn_rule_pdf_previous = controls.add("‹", lambda: host.change_rule_pdf_page(-1), width=0)
    host.var_rule_pdf_page = tk.StringVar(master=host, value="Keine Seite")
    controls.add_widget(ttk.Label(controls, textvariable=host.var_rule_pdf_page))
    host.btn_rule_pdf_next = controls.add("›", lambda: host.change_rule_pdf_page(1), width=0)
    controls.add("−", lambda: host.zoom_rule_pdf(-.15), width=0)
    controls.add("+", lambda: host.zoom_rule_pdf(.15), width=0)
    controls.add("Breite", host.fit_rule_pdf_width, width=0)
    canvas = tk.Canvas(pdf, background="#e7edf0", borderwidth=0, highlightthickness=0, width=100, height=100)
    host.rule_pdf_canvas = canvas
    canvas.grid(row=1, column=0, sticky="nsew")
    ybar = OverflowScrollbar(pdf, orient="vertical", command=canvas.yview)
    xbar = OverflowScrollbar(pdf, orient="horizontal", command=canvas.xview)
    canvas.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
    canvas.bind("<MouseWheel>", lambda event: canvas.yview_scroll(-int(event.delta / 120), "units"))
    host._document_view = "text"
    host.tree_marking_legend = None
