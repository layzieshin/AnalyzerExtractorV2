from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from src.dbwriter.api import discard_duplicate_candidate, get_duplicate_candidate, list_duplicate_candidates
from src.jobcontroller.api import submit
from src.jobqueue.api import list_jobs
from src.ruleresolver.api import validate_rules_integrity
from src.runtime.api import list_devices, load_runtime_config, resolve_app_root
from src.testui.api import (
    classify_job_outcome,
    format_device_choice,
    format_duplicate_candidate_detail,
    format_duplicate_candidate_summary,
    format_duplicate_field_comparison,
    format_job_result_summary,
    format_queue_job_row,
    format_runtime_options_summary,
    format_validation_status,
    format_watch_file_row,
)

SECTION_KEYS = ("EXTRACTOR", "OPTIONS", "RULE SUITE", "LOGS", "DUPLIKATE", "ADMIN")


class TestApp(tk.Tk):
    """Production-shaped test shell; long-running process control is out of scope."""

    __test__ = False

    def __init__(self, project_root: str | Path | None = None) -> None:
        super().__init__()
        root = Path(project_root) if project_root is not None else resolve_app_root(__file__)
        self.project_root = root.resolve()
        self.title("AREV2 Test-App")
        self.geometry("1240x820")

        cfg = load_runtime_config(self.project_root)
        self.var_output_mode = tk.StringVar(value=cfg.output_mode)
        self.var_sqlite_path = tk.StringVar(value=cfg.sqlite_path or "")
        self.var_watch_dir = tk.StringVar(value=cfg.watch_dir or str(self.project_root / "input" / "watch"))
        self.var_watch_mode = tk.StringVar(value="Ueberwachter Ordner")
        self.var_device_choice = tk.StringVar(value="")
        self.var_duplicate_status = tk.StringVar(value="pending")
        self.var_status = tk.StringVar(value="Bereit.")
        self.var_technical_status = tk.StringVar(value="idle")
        self._device_choice_to_id: dict[str, str] = {}
        self._watch_rows: dict[str, dict[str, str]] = {}
        self._duplicate_details: dict[int, dict[str, object]] = {}

        self._build_ui()
        self._refresh_devices()
        self._refresh_options_summary()
        self.refresh_queue()

    def _build_ui(self) -> None:
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)

        self._tabs: dict[str, tk.Frame] = {}
        for key in SECTION_KEYS:
            frame = tk.Frame(self.notebook)
            self._tabs[key] = frame
            self.notebook.add(frame, text=key)

        self._build_extractor_tab(self._tabs["EXTRACTOR"])
        self._build_options_tab(self._tabs["OPTIONS"])
        self._build_rule_suite_tab(self._tabs["RULE SUITE"])
        self._build_logs_tab(self._tabs["LOGS"])
        self._build_duplicates_tab(self._tabs["DUPLIKATE"])
        self._build_admin_tab(self._tabs["ADMIN"])

        status = tk.Frame(self)
        status.pack(fill="x", padx=10, pady=(0, 10))
        tk.Label(status, textvariable=self.var_status, anchor="w").pack(side="left", fill="x", expand=True)
        self.progress = ttk.Progressbar(status, mode="determinate", length=180)
        self.progress.pack(side="left", padx=(8, 12))
        tk.Label(status, textvariable=self.var_technical_status, anchor="e", width=28).pack(side="right")

    def _build_extractor_tab(self, parent: tk.Frame) -> None:
        controls = tk.Frame(parent)
        controls.pack(fill="x", padx=8, pady=8)
        tk.Button(controls, text="Suchen", command=self.scan_watch_dir).pack(side="left")
        tk.Button(controls, text="Dateien auswaehlen", command=self.pick_manual_files).pack(side="left", padx=(6, 0))
        tk.Button(controls, text="Starten", command=self.start_selected_files).pack(side="left", padx=(6, 0))
        tk.Button(controls, text="Liste aktualisieren", command=self.refresh_queue).pack(side="left", padx=(6, 0))

        self.tree_files = ttk.Treeview(
            parent,
            columns=("file", "source", "queue_status", "job_id", "device_id", "last_error", "action", "path"),
            show="headings",
            height=16,
        )
        for col, title, width in (
            ("file", "Datei", 190),
            ("source", "Quelle", 80),
            ("queue_status", "Queue", 90),
            ("job_id", "Job-ID", 140),
            ("device_id", "Geraet", 120),
            ("last_error", "Letzter Fehler", 200),
            ("action", "Aktion/Status", 150),
            ("path", "Pfad", 360),
        ):
            self.tree_files.heading(col, text=title)
            self.tree_files.column(col, width=width, anchor="w")
        self.tree_files.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    def _build_options_tab(self, parent: tk.Frame) -> None:
        form = tk.LabelFrame(parent, text="Testkonfiguration")
        form.pack(fill="x", padx=8, pady=8)
        form.columnconfigure(1, weight=1)

        tk.Label(form, text="Output-Modus").grid(row=0, column=0, sticky="w", padx=6, pady=(8, 4))
        ttk.Combobox(
            form,
            textvariable=self.var_output_mode,
            values=("excel", "sqlite", "both"),
            state="readonly",
            width=12,
        ).grid(row=0, column=1, sticky="w", padx=6, pady=(8, 4))

        tk.Label(form, text="SQLite-Pfad").grid(row=1, column=0, sticky="w", padx=6, pady=4)
        tk.Entry(form, textvariable=self.var_sqlite_path).grid(row=1, column=1, sticky="we", padx=6, pady=4)

        tk.Label(form, text="Watch-Ordner").grid(row=2, column=0, sticky="w", padx=6, pady=4)
        tk.Entry(form, textvariable=self.var_watch_dir).grid(row=2, column=1, sticky="we", padx=6, pady=4)
        tk.Button(form, text="Ordner", command=self.pick_watch_dir).grid(row=2, column=2, sticky="w", padx=6, pady=4)

        tk.Label(form, text="Geraet").grid(row=3, column=0, sticky="w", padx=6, pady=4)
        self.cmb_devices = ttk.Combobox(form, textvariable=self.var_device_choice, state="readonly", width=34)
        self.cmb_devices.grid(row=3, column=1, sticky="w", padx=6, pady=4)
        tk.Button(form, text="Neu laden", command=self._refresh_devices).grid(row=3, column=2, sticky="w", padx=6, pady=4)

        tk.Label(form, text="Watch-Modus").grid(row=4, column=0, sticky="w", padx=6, pady=(4, 8))
        ttk.Combobox(
            form,
            textvariable=self.var_watch_mode,
            values=("Manuell", "Ueberwachter Ordner", "Automatikbetrieb (Folgepaket)"),
            state="readonly",
            width=30,
        ).grid(row=4, column=1, sticky="w", padx=6, pady=(4, 8))
        tk.Button(form, text="Anzeigen", command=self._refresh_options_summary).grid(row=4, column=2, sticky="w", padx=6, pady=(4, 8))

        self.txt_options = tk.Text(parent, height=9, wrap="word")
        self.txt_options.pack(fill="x", padx=8, pady=(0, 8))
        self.txt_options.configure(state="disabled")

    def _build_rule_suite_tab(self, parent: tk.Frame) -> None:
        controls = tk.Frame(parent)
        controls.pack(fill="x", padx=8, pady=8)
        tk.Button(controls, text="Rule Editor oeffnen", command=self.open_rule_editor).pack(side="left")
        tk.Button(controls, text="Rules validieren", command=self.validate_rules).pack(side="left", padx=(6, 0))
        self.lbl_validation = tk.Label(parent, text="Noch keine Validierung.", anchor="w")
        self.lbl_validation.pack(fill="x", padx=8, pady=(0, 8))

    def _build_logs_tab(self, parent: tk.Frame) -> None:
        self.txt_logs = tk.Text(parent, height=20, wrap="word")
        self.txt_logs.pack(fill="both", expand=True, padx=8, pady=8)

    def _build_duplicates_tab(self, parent: tk.Frame) -> None:
        controls = tk.Frame(parent)
        controls.pack(fill="x", padx=8, pady=8)
        tk.Label(controls, text="Status").pack(side="left")
        ttk.Combobox(
            controls,
            textvariable=self.var_duplicate_status,
            values=("pending", "deleted"),
            state="readonly",
            width=12,
        ).pack(side="left", padx=(4, 8))
        tk.Button(controls, text="Aktualisieren", command=self.refresh_duplicates).pack(side="left")
        tk.Button(controls, text="Kandidat verwerfen", command=self.discard_selected_duplicate).pack(side="left", padx=(6, 0))

        self.tree_duplicates = ttk.Treeview(
            parent,
            columns=("id", "status", "assay", "device", "detected", "existing", "dedupe"),
            show="headings",
            height=7,
        )
        for col, title, width in (
            ("id", "ID", 70),
            ("status", "Status", 150),
            ("assay", "Assay", 110),
            ("device", "Geraet", 120),
            ("detected", "Erkannt am", 190),
            ("existing", "Existing Run", 100),
            ("dedupe", "Dedupe-Key", 360),
        ):
            self.tree_duplicates.heading(col, text=title)
            self.tree_duplicates.column(col, width=width, anchor="w")
        self.tree_duplicates.pack(fill="x", padx=8, pady=(0, 8))
        self.tree_duplicates.bind("<<TreeviewSelect>>", self.on_duplicate_selected)

        self.txt_duplicate_detail = tk.Text(parent, height=8, wrap="word")
        self.txt_duplicate_detail.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.tree_duplicate_fields = ttk.Treeview(
            parent,
            columns=("field", "existing", "candidate", "same"),
            show="headings",
            height=6,
        )
        for col, title, width in (
            ("field", "Feld", 180),
            ("existing", "Bestehend", 300),
            ("candidate", "Kandidat", 300),
            ("same", "Gleich", 70),
        ):
            self.tree_duplicate_fields.heading(col, text=title)
            self.tree_duplicate_fields.column(col, width=width, anchor="w")
        self.tree_duplicate_fields.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    def _build_admin_tab(self, parent: tk.Frame) -> None:
        controls = tk.Frame(parent)
        controls.pack(fill="x", padx=8, pady=8)
        tk.Button(controls, text="Queue aktualisieren", command=self.refresh_queue).pack(side="left")
        self.tree_queue = ttk.Treeview(
            parent,
            columns=("job_id", "file", "status", "source", "attempts", "last_error", "updated_at", "path"),
            show="headings",
            height=12,
        )
        for col, title, width in (
            ("job_id", "Job-ID", 140),
            ("file", "Datei", 180),
            ("status", "Status", 100),
            ("source", "Quelle", 100),
            ("attempts", "Versuche", 70),
            ("last_error", "Letzter Fehler", 220),
            ("updated_at", "Aktualisiert", 170),
            ("path", "Pfad", 360),
        ):
            self.tree_queue.heading(col, text=title)
            self.tree_queue.column(col, width=width, anchor="w")
        self.tree_queue.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    def _selected_device_id(self) -> str | None:
        return self._device_choice_to_id.get(self.var_device_choice.get())

    def _sqlite_path(self) -> Path:
        value = self.var_sqlite_path.get().strip()
        return Path(value) if value else self.project_root / "output" / "final" / "results.sqlite3"

    def _refresh_devices(self) -> None:
        choices: list[str] = []
        self._device_choice_to_id = {}
        for device in list_devices(self.project_root):
            row = format_device_choice(device)
            label = row["label"]
            if not label:
                continue
            choices.append(label)
            self._device_choice_to_id[label] = row["device_id"]
        self.cmb_devices.configure(values=choices)
        if choices and self.var_device_choice.get() not in choices:
            self.var_device_choice.set(choices[0])
        self._refresh_options_summary()

    def _refresh_options_summary(self) -> None:
        lines = format_runtime_options_summary(
            {
                "output_mode": self.var_output_mode.get(),
                "sqlite_path": self.var_sqlite_path.get(),
                "watch_dir": self.var_watch_dir.get(),
                "device_id": self._selected_device_id(),
                "watch_mode": self.var_watch_mode.get(),
            }
        )
        self._set_text(self.txt_options, "\n".join(lines))

    def _log(self, message: str) -> None:
        self.txt_logs.insert(tk.END, message + "\n")
        self.txt_logs.see(tk.END)
        self.var_status.set(message)

    def _set_text(self, widget: tk.Text, text: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", tk.END)
        widget.insert(tk.END, text)
        widget.configure(state="disabled")

    def pick_watch_dir(self) -> None:
        selected = filedialog.askdirectory(title="Watch-Ordner waehlen")
        if selected:
            self.var_watch_dir.set(selected)
            self._refresh_options_summary()

    def scan_watch_dir(self) -> None:
        watch = Path(self.var_watch_dir.get().strip())
        rows = []
        if watch.exists():
            rows = [format_watch_file_row(path, source="watch") for path in sorted(watch.glob("*.pdf"))]
        self._replace_file_rows(rows)
        self.refresh_queue()
        self._log(f"Watch-Ordner gescannt: {len(rows)} PDF(s)")

    def pick_manual_files(self) -> None:
        files = filedialog.askopenfilenames(title="PDFs waehlen", filetypes=[("PDF Dateien", "*.pdf")])
        rows = [format_watch_file_row(path, source="manual") for path in files]
        self._replace_file_rows(rows, append=True)
        self._log(f"Manuelle PDFs hinzugefuegt: {len(rows)}")

    def _replace_file_rows(self, rows: list[dict[str, str]], *, append: bool = False) -> None:
        if not append:
            self._watch_rows = {}
            for item in self.tree_files.get_children():
                self.tree_files.delete(item)
        for row in rows:
            path = row["path"]
            self._watch_rows[path] = row
            if self.tree_files.exists(path):
                self.tree_files.delete(path)
            self.tree_files.insert(
                "",
                tk.END,
                iid=path,
                values=(
                    row["file"],
                    row["source"],
                    row["queue_status"],
                    row["job_id"],
                    row["device_id"],
                    row["last_error"],
                    row["action"],
                    row["path"],
                ),
            )

    def start_selected_files(self) -> None:
        selection = list(self.tree_files.selection()) or list(self._watch_rows)
        if not selection:
            messagebox.showinfo("Extractor", "Bitte zuerst PDFs suchen oder auswaehlen.")
            return
        threading.Thread(target=self._submit_files_thread, args=(selection,), daemon=True).start()

    def _submit_files_thread(self, paths: list[str]) -> None:
        self.after(0, lambda: self.var_technical_status.set("running"))
        for path in paths:
            try:
                res = submit(
                    path,
                    str(self.project_root),
                    output_mode=self.var_output_mode.get(),
                    sqlite_path=self.var_sqlite_path.get().strip() or None,
                    device_id=self._selected_device_id(),
                )
                outcome = classify_job_outcome(res.status, res.details)
                summary = format_job_result_summary(
                    pdf_path=res.pdf_path,
                    job_id=res.job_id,
                    status=res.status,
                    details=res.details,
                    outcome=outcome,
                )
                self.after(0, lambda msg=summary: self._log(msg))
                if path in self._watch_rows:
                    self._watch_rows[path]["action"] = outcome
                    self._watch_rows[path]["job_id"] = res.job_id
                    self._watch_rows[path]["device_id"] = self._selected_device_id() or ""
            except Exception as e:
                self.after(0, lambda msg=f"Fehler bei {Path(path).name}: {e}": self._log(msg))
        self.after(0, self._finish_submit_thread)

    def _finish_submit_thread(self) -> None:
        self.var_technical_status.set("idle")
        self.refresh_queue()

    def refresh_queue(self) -> None:
        rows = [format_queue_job_row(job) for job in list_jobs(str(self.project_root))]
        for item in self.tree_queue.get_children():
            self.tree_queue.delete(item)
        for row in rows:
            iid = row["job_id"] or row["path"]
            self.tree_queue.insert(
                "",
                tk.END,
                iid=iid,
                values=(
                    row["job_id"],
                    row["file"],
                    row["status"],
                    row["source"],
                    row["attempts"],
                    row["last_error"],
                    row["updated_at"],
                    row["path"],
                ),
            )
        for path, file_row in list(self._watch_rows.items()):
            match = next((row for row in rows if row["path"] == path), None)
            if match:
                file_row["queue_status"] = match["status"]
                file_row["job_id"] = match["job_id"]
                file_row["last_error"] = match["last_error"]
        if self._watch_rows:
            self._replace_file_rows(list(self._watch_rows.values()))

    def validate_rules(self) -> None:
        report = validate_rules_integrity(
            str(self.project_root / "rules"),
            str(self.project_root / "rules" / "index.json"),
        )
        status = format_validation_status(report)
        self.lbl_validation.configure(text=f"{status['status']} | {status['summary']}")
        self._log(f"Rules validiert: {status['summary']}")

    def open_rule_editor(self) -> None:
        script = self.project_root / "rule_editor_main.py"
        if not script.exists():
            messagebox.showerror("Rule Editor", f"Nicht gefunden:\n{script}")
            return
        subprocess.Popen([sys.executable, str(script)], cwd=str(self.project_root))
        self._log("Rule Editor gestartet.")

    def refresh_duplicates(self) -> None:
        for item in self.tree_duplicates.get_children():
            self.tree_duplicates.delete(item)
        for item in self.tree_duplicate_fields.get_children():
            self.tree_duplicate_fields.delete(item)
        self._set_text(self.txt_duplicate_detail, "")
        sqlite_path = self._sqlite_path()
        if not sqlite_path.exists():
            self._log(f"SQLite nicht gefunden: {sqlite_path}")
            return
        rows = list_duplicate_candidates(str(sqlite_path), status=self.var_duplicate_status.get())
        for row in rows:
            summary = format_duplicate_candidate_summary(row)
            candidate_id = summary["candidate_id"]
            self.tree_duplicates.insert(
                "",
                tk.END,
                iid=candidate_id,
                values=(
                    summary["candidate_id"],
                    summary["status"],
                    summary["assay_key"],
                    summary["device_id"],
                    summary["detected_at"],
                    summary["existing_run_id"],
                    summary["dedupe_key"],
                ),
            )
        self._log(f"Duplikate geladen: {len(rows)}")

    def on_duplicate_selected(self, _event: object = None) -> None:
        sel = self.tree_duplicates.selection()
        if not sel:
            return
        candidate_id = int(str(sel[0]))
        detail = get_duplicate_candidate(str(self._sqlite_path()), candidate_id)
        if not detail:
            return
        self._duplicate_details[candidate_id] = detail
        self._set_text(self.txt_duplicate_detail, format_duplicate_candidate_detail(detail))
        for item in self.tree_duplicate_fields.get_children():
            self.tree_duplicate_fields.delete(item)
        for idx, row in enumerate(format_duplicate_field_comparison(detail)):
            self.tree_duplicate_fields.insert(
                "",
                tk.END,
                iid=f"{candidate_id}:{idx}",
                values=(row["field"], row["existing"], row["candidate"], row["same"]),
            )

    def discard_selected_duplicate(self) -> None:
        sel = self.tree_duplicates.selection()
        if not sel:
            messagebox.showinfo("Duplikate", "Bitte zuerst einen Kandidaten auswaehlen.")
            return
        candidate_id = int(str(sel[0]))
        detail = self._duplicate_details.get(candidate_id)
        candidate = detail.get("candidate") if isinstance(detail, dict) else None
        if isinstance(candidate, dict) and candidate.get("status") != "pending":
            messagebox.showinfo("Duplikate", "Nur pending Kandidaten koennen verworfen werden.")
            return
        discard_duplicate_candidate(str(self._sqlite_path()), candidate_id, decided_by="test-app")
        self._log(f"Duplicate-Kandidat verworfen: {candidate_id}")
        self.refresh_duplicates()


def main() -> None:
    app = TestApp()
    app.mainloop()
