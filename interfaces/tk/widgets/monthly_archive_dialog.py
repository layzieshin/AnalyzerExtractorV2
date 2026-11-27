"""Native adapter for ResultsController's immutable monthly archive preview."""
from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, ttk

from .common import create_scrollable_tree


class MonthlyArchiveDialog(tk.Toplevel):
    def __init__(self, master, *, on_preview, on_commit, on_recover, initial_cutoff, initials=""):
        super().__init__(master)
        self.title("Eingang aufräumen · Monatsarchiv")
        self.transient(master.winfo_toplevel())
        self.geometry(f"{min(1100, max(760, master.winfo_width()-40))}x{min(740, max(500, master.winfo_height()-40))}")
        self.minsize(720, 480)
        self._on_preview, self._on_commit, self._on_recover = on_preview, on_commit, on_recover
        self.generation = 0
        self.preview = None
        self.assignments, self.exceptions, self._choice_sha = {}, set(), {}
        self._sources, self._groups = {}, {}
        self._busy = False
        self._write_busy, self.closed = False, False
        body = ttk.Frame(self, padding=16)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(2, weight=1)
        ttk.Label(body, text="Eingang aufräumen", font=("Segoe UI", 16, "bold")).grid(row=0, column=0, sticky="w")
        self._toolbar = toolbar = ttk.Frame(body)
        toolbar.grid(row=1, column=0, sticky="ew", pady=(10, 10))
        self._date_controls = dates = ttk.Frame(toolbar)
        ttk.Label(dates, text="Stichtag einschließlich (JJJJ-MM-TT)").pack(side="left")
        self._var_cutoff = tk.StringVar(value=initial_cutoff)
        self._cutoff_entry = ttk.Entry(dates, textvariable=self._var_cutoff, width=13)
        self._cutoff_entry.pack(side="left", padx=8)
        self._btn_preview = ttk.Button(toolbar, text="Vorschau prüfen", command=self.request_preview)
        self._btn_recover = ttk.Button(toolbar, text="Unterbrochenen Vorgang fortsetzen", command=lambda: self._on_recover(self))
        frame, self._tree = create_scrollable_tree(body, ("plate", "date", "count", "target", "status"),
            ("Platte / Datei", "Messdatum", "Dateien", "Monatsziel", "Prüfstatus"), height=10, autohide=True)
        frame.grid(row=2, column=0, sticky="nsew")
        self._tree.configure(show="tree headings", selectmode="extended")
        self._tree.column("#0", width=24, stretch=False)
        for key, width in (("plate", 230), ("date", 110), ("count", 70), ("target", 170), ("status", 180)):
            self._tree.column(key, width=width, minwidth=60, stretch=key in {"plate", "status"})
        self._tree.bind("<<TreeviewSelect>>", self._selected)
        self._details = ttk.Label(body, text="Vollständige Gruppen werden vorausgewählt. Keine Datei wird durch die Vorschau geändert.", wraplength=850)
        self._details.grid(row=3, column=0, sticky="ew", pady=(8, 8))
        options = ttk.Frame(body)
        options.grid(row=4, column=0, sticky="ew")
        self._btn_assign = ttk.Button(options, text="RES für ausgewählte PDF zuordnen", command=self._assign_res, state="disabled")
        self._btn_assign.pack(side="left")
        self._btn_no_res = ttk.Button(options, text="Nur diese PDF ohne RES", command=self._without_res, state="disabled")
        self._btn_no_res.pack(side="left", padx=8)
        footer = ttk.Frame(body)
        footer.grid(row=5, column=0, sticky="ew", pady=(12, 0))
        ttk.Label(footer, text="Initialen").pack(side="left")
        self._var_initials = tk.StringVar(value=initials)
        ttk.Entry(footer, textvariable=self._var_initials, width=10).pack(side="left", padx=8)
        self._btn_commit = ttk.Button(footer, text="Ausgewählte Läufe ablegen", style="Primary.TButton", command=self._commit, state="disabled")
        self._btn_commit.pack(side="left")
        self._btn_close = ttk.Button(footer, text="Schließen", command=self.destroy)
        self._btn_close.pack(side="right")
        self._var_cutoff.trace_add("write", lambda *_: self._invalidate())
        self.bind("<Configure>", self._layout)
        self.bind("<Escape>", lambda _event: self.destroy() if not self._write_busy else None)
        self.protocol("WM_DELETE_WINDOW", lambda: self.destroy() if not self._write_busy else None)
        self.bind("<Destroy>", lambda event: self._closed() if event.widget is self else None)
        self.grab_set()
        self.after_idle(self.request_preview)

    def _layout(self, event):
        if event.widget is not self:
            return
        width = max(300, event.width - 40)
        self._details.configure(wraplength=width)
        required = sum(widget.winfo_reqwidth() for widget in (self._date_controls, self._btn_preview, self._btn_recover)) + 24
        compact = width < required
        self._toolbar.columnconfigure(0, weight=1 if not compact else 0)
        self._toolbar.columnconfigure(1, weight=0 if not compact else 1)
        self._date_controls.grid(row=0, column=0, columnspan=2 if compact else 1, sticky="w", pady=(0, 8 if compact else 0))
        self._btn_preview.grid(row=1 if compact else 0, column=0 if compact else 1, sticky="w", padx=(0, 8))
        self._btn_recover.grid(row=1 if compact else 0, column=1 if compact else 2, sticky="e")
        heading = tkfont.Font(self, font=ttk.Style(self).lookup("Treeview.Heading", "font") or "TkHeadingFont")
        columns = ("plate", "date", "count", "target", "status")
        minima = [heading.measure(self._tree.heading(key, "text")) + 24 for key in columns]
        spare = max(0, width - 26 - sum(minima))
        for key, minimum, share in zip(columns, minima, (.32, .12, .04, .25, .27)):
            self._tree.column(key, width=minimum + int(spare * share), minwidth=minimum, stretch=False)

    def _invalidate(self):
        self.generation += 1
        self.preview = None
        self._btn_commit.configure(state="disabled")

    def request_preview(self):
        if self._busy:
            return
        self._invalidate()
        self._on_preview(self, self._var_cutoff.get().strip(), dict(self.assignments), tuple(self.exceptions))

    def _closed(self):
        self.closed = True
        self.generation += 1

    def set_busy(self, busy, message="", *, write=False):
        self._busy = busy
        self._write_busy = busy and write
        self._cutoff_entry.configure(state="disabled" if busy else "normal")
        for button in (self._btn_preview, self._btn_recover):
            button.configure(state="disabled" if busy else "normal")
        self._btn_close.configure(state="disabled" if self._write_busy else "normal")
        self._btn_commit.configure(state="normal" if not busy and self.preview and self.selected_groups() else "disabled")
        self._selected()
        if message:
            self._details.configure(text=message)

    def render_preview(self, preview):
        self.preview = preview
        self._sources, self._groups = {}, {}
        self._tree.delete(*self._tree.get_children())
        current = {source.path: source.sha256 for group in preview.groups for source in group.sources if source.kind == "pdf"}
        stale_choices = False
        for path in tuple(self._choice_sha):
            if current.get(path) != self._choice_sha[path]:
                self.assignments.pop(path, None)
                self.exceptions.discard(path)
                self._choice_sha.pop(path)
                stale_choices = True
        for group in preview.groups:
            self._groups[group.group_id] = group
            path_parts = group.target_dir.split("\\") if "\\" in group.target_dir else group.target_dir.split("/")
            target = "/".join(path_parts[-2:])
            self._tree.insert("", "end", iid=group.group_id, open=True,
                values=(group.plate, group.measured_date, len(group.sources), target, "Bereit" if group.eligible else "Gesperrt – Grund im Detail"))
            for number, source in enumerate(group.sources):
                iid = f"{group.group_id}:{number}"
                self._sources[iid] = source
                filename = source.path.rsplit("\\", 1)[-1].rsplit("/", 1)[-1]
                self._tree.insert(group.group_id, "end", iid=iid, values=(filename, "", "", target + ("/res" if source.kind == "res" else ""), source.kind.upper()))
        if stale_choices:
            self._invalidate()
            self._details.configure(text="Eine gewählte PDF wurde geändert. RES-Ausnahme/Zuordnung verworfen; bitte Vorschau neu prüfen.")
        else:
            self._tree.selection_set(tuple(group.group_id for group in preview.groups if group.eligible))
            self._details.configure(text="Vollständige Läufe sind vorausgewählt. Platte/Datei für vollständigen Zielpfad und Prüfgrund auswählen.")
        self.set_busy(False)

    def selected_groups(self):
        return tuple(iid for iid in self._tree.selection() if iid in self._groups and self._groups[iid].eligible)

    def selected_pdf(self):
        selected = self._tree.selection()
        source = self._sources.get(selected[0]) if len(selected) == 1 else None
        return source if source is not None and source.kind == "pdf" else None

    def _selected(self, _event=None):
        source = self.selected_pdf()
        selected = self._tree.selection()
        if len(selected) == 1:
            iid = selected[0]
            group = self._groups.get(iid) or self._groups.get(self._tree.parent(iid))
            if group is not None:
                suffix = "/res" if iid in self._sources and self._sources[iid].kind == "res" else ""
                filename = self._sources[iid].path + "\n" if iid in self._sources else ""
                self._details.configure(text=filename + f"{group.plate} · Ziel: {group.target_dir}{suffix}\n"
                    + ("Alle erwarteten Ergebnisse und Quellen vollständig geprüft." if group.eligible else "; ".join(group.reasons)))
        for button in (self._btn_assign, self._btn_no_res):
            button.configure(state="normal" if source and not self._busy else "disabled")
        self._btn_commit.configure(state="normal" if self.preview and not self._busy and self.selected_groups() else "disabled")

    def _assign_res(self):
        source = self.selected_pdf()
        if source is None:
            return
        path = filedialog.askopenfilename(parent=self, title="RES ausdrücklich zuordnen", filetypes=[("Analyzer RES", "*.res"), ("Alle Dateien", "*.*")])
        if path:
            self.assignments[source.path] = path
            self.exceptions.discard(source.path)
            self._choice_sha[source.path] = source.sha256
            self.request_preview()

    def _without_res(self):
        source = self.selected_pdf()
        if source and messagebox.askyesno("Einzelne PDF ohne RES", f"Nur diese PDF ohne zugehörige RES archivieren?\n\n{source.path}\n\nDie Ausnahme gilt nicht für spätere Dateien; Initialen und Zeitpunkt werden festgehalten.", parent=self):
            self.exceptions.add(source.path)
            self.assignments.pop(source.path, None)
            self._choice_sha[source.path] = source.sha256
            self.request_preview()

    def _commit(self):
        if self.preview is None or not self.selected_groups():
            return
        if (self.exceptions or self.assignments) and not self._var_initials.get().strip():
            messagebox.showinfo("Initialen", "Für RES-Zuordnung oder Ausnahme bitte Initialen eingeben.", parent=self)
            return
        if messagebox.askyesno("Archivieren bestätigen", "Alle Zieldateien werden zuerst vollständig kopiert und geprüft. Erst danach werden die ausgewählten Originale aus dem Eingang entfernt. Jetzt fortfahren?", parent=self):
            self._on_commit(self, self.preview, self.selected_groups(), dict(self.assignments), tuple(self.exceptions), self._var_initials.get().strip())
