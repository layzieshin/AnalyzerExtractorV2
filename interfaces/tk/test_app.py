from __future__ import annotations

import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any

from src.dbwriter.api import discard_duplicate_candidate, get_duplicate_candidate, list_duplicate_candidates
from src.jobcontroller.api import submit
from src.jobqueue.api import enqueue_pdf_job, list_jobs
from src.ruleresolver.api import validate_rules_integrity
from src.runtime.api import list_devices, load_runtime_config, resolve_app_root
from src.testui.api import (
    format_device_choice,
    format_duplicate_candidate_detail,
    format_duplicate_candidate_summary,
    format_duplicate_field_comparison,
    format_enqueue_result,
    format_job_result_summary,
    format_submit_row_update,
    format_queue_job_row,
    format_runtime_options_summary,
    format_validation_status,
    format_watch_file_row,
    merge_file_rows_with_queue,
    normalize_file_row_key,
)

from .watch_scan import InAppWatchScanner, list_watch_pdf_paths

SECTION_KEYS = ("EXTRACTOR", "OPTIONS", "RULE SUITE", "LOGS", "DUPLIKATE", "ADMIN")


class TestApp(tk.Tk):
    """Production-shaped test shell; long-running process control is out of scope."""

    __test__ = False

    def __init__(self, project_root: str | Path | None = None) -> None:
        super().__init__()
        root = Path(project_root) if project_root is not None else resolve_app_root()
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
        self.var_auto_watch_status = tk.StringVar(value="Auto-Suche: inaktiv")
        self.var_auto_watch_last_scan = tk.StringVar(value="Letzter Scan: -")
        self.var_auto_watch_found = tk.StringVar(value="Neue PDFs: -")
        self.var_watch_recursive = tk.BooleanVar(value=False)
        self.var_status = tk.StringVar(value="Bereit.")
        self.var_technical_status = tk.StringVar(value="idle")
        self._auto_watch_interval_s = max(0.5, float(cfg.scan_interval_s or 3.0))
        self._auto_watch_stable_window_s = float(cfg.watch_stable_window_s)
        self._auto_watch_active = False
        self._auto_watch_after_id: str | None = None
        self._auto_watch_scanner = InAppWatchScanner()
        self._auto_watch_last_warning = ""
        self._auto_watch_suppressed_paths: set[str] = set()
        self._device_choice_to_id: dict[str, str] = {}
        self._watch_rows: dict[str, dict[str, str]] = {}
        self._duplicate_details: dict[int, dict[str, object]] = {}
        self._busy = False
        self._action_buttons: list[tk.Button] = []

        self._build_ui()
        self._refresh_devices()
        self._refresh_options_summary()
        self.refresh_queue()
        self.protocol("WM_DELETE_WINDOW", self.close_app)

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
        self.btn_scan_watch = tk.Button(controls, text="Watch-Ordner scannen", command=self.scan_watch_dir)
        self.btn_scan_watch.pack(side="left")
        self.btn_pick_files = tk.Button(controls, text="Dateien auswaehlen", command=self.pick_manual_files)
        self.btn_pick_files.pack(side="left", padx=(6, 0))
        self.btn_direct_submit = tk.Button(controls, text="Direkt verarbeiten", command=self.start_selected_files)
        self.btn_direct_submit.pack(side="left", padx=(6, 0))
        self.btn_enqueue = tk.Button(controls, text="In Queue stellen", command=self.enqueue_selected_files)
        self.btn_enqueue.pack(side="left", padx=(6, 0))
        self.btn_refresh_queue = tk.Button(controls, text="Liste aktualisieren", command=self.refresh_queue)
        self.btn_refresh_queue.pack(side="left", padx=(6, 0))
        self.btn_auto_watch_start = tk.Button(controls, text="Auto-Suche starten", command=self.start_auto_watch)
        self.btn_auto_watch_start.pack(side="left", padx=(18, 0))
        self.btn_auto_watch_stop = tk.Button(controls, text="Auto-Suche stoppen", command=self.stop_auto_watch)
        self.btn_auto_watch_stop.pack(side="left", padx=(6, 0))
        tk.Checkbutton(controls, text="Unterordner einbeziehen", variable=self.var_watch_recursive).pack(
            side="left", padx=(12, 0)
        )
        self._action_buttons.extend(
            [
                self.btn_scan_watch,
                self.btn_pick_files,
                self.btn_direct_submit,
                self.btn_enqueue,
                self.btn_refresh_queue,
            ]
        )

        auto_status = tk.Frame(parent)
        auto_status.pack(fill="x", padx=8, pady=(0, 6))
        tk.Label(auto_status, textvariable=self.var_auto_watch_status, anchor="w", width=26).pack(side="left")
        tk.Label(auto_status, textvariable=self.var_auto_watch_last_scan, anchor="w", width=26).pack(side="left")
        tk.Label(auto_status, textvariable=self.var_auto_watch_found, anchor="w").pack(side="left", fill="x", expand=True)

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

    def start_auto_watch(self) -> None:
        if self._auto_watch_active:
            return
        self._auto_watch_active = True
        self._auto_watch_last_warning = ""
        self.var_auto_watch_status.set("Auto-Suche: aktiv")
        self._log("Auto-Suche gestartet.")
        self._schedule_auto_watch(delay_ms=0)

    def stop_auto_watch(self, *, log: bool = True) -> None:
        was_active = self._auto_watch_active
        self._auto_watch_active = False
        if self._auto_watch_after_id is not None:
            try:
                self.after_cancel(self._auto_watch_after_id)
            except tk.TclError:
                pass
            self._auto_watch_after_id = None
        self.var_auto_watch_status.set("Auto-Suche: inaktiv")
        if log and was_active:
            self._log("Auto-Suche gestoppt.")

    def _schedule_auto_watch(self, *, delay_ms: int | None = None) -> None:
        if not self._auto_watch_active:
            return
        delay = int(self._auto_watch_interval_s * 1000) if delay_ms is None else max(0, delay_ms)
        self._auto_watch_after_id = self.after(delay, self._run_auto_watch_scan)

    def _build_known_paths_for_scanner(self) -> set[str]:
        known = {row.get("path", "") for row in self._watch_rows.values() if row.get("path")}
        for job in list_jobs(str(self.project_root)):
            queue_row = format_queue_job_row(job)
            if queue_row.get("path"):
                known.add(queue_row["path"])
        known.update(self._auto_watch_suppressed_paths)
        return known

    def _row_is_queued(self, row: dict[str, str]) -> bool:
        return bool(row.get("job_id") or row.get("queue_status"))

    def _run_auto_watch_scan(self) -> None:
        self._auto_watch_after_id = None
        if not self._auto_watch_active:
            return
        try:
            if self._busy:
                self.var_auto_watch_status.set("Auto-Suche: aktiv")
                return

            known_paths = self._build_known_paths_for_scanner()
            result = self._auto_watch_scanner.scan(
                self.var_watch_dir.get().strip(),
                known_paths,
                self._auto_watch_stable_window_s,
                recursive=self.var_watch_recursive.get(),
            )
            self.var_auto_watch_last_scan.set(f"Letzter Scan: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            self.var_auto_watch_found.set(
                f"Neue PDFs: {len(result.stable_new_paths)} | Beobachtet: {result.observed_count}"
            )

            if result.warning:
                self.var_auto_watch_status.set("Auto-Suche: Warnung")
                if result.warning != self._auto_watch_last_warning:
                    self._log(f"Auto-Suche Warnung: {result.warning}")
                self._auto_watch_last_warning = result.warning
                return

            self.var_auto_watch_status.set("Auto-Suche: aktiv")
            if self._auto_watch_last_warning:
                self._log("Auto-Suche wieder OK.")
                self._auto_watch_last_warning = ""

            if result.stable_new_paths:
                queued_count = 0
                for path in result.stable_new_paths:
                    try:
                        enqueue_pdf_job(
                            str(self.project_root),
                            path,
                            source="test-app-auto-watch",
                        )
                        self._auto_watch_suppressed_paths.add(path)
                        queued_count += 1
                    except Exception as e:
                        self._log(f"Auto-Suche Queue-Fehler bei {Path(path).name}: {e}")
                if queued_count:
                    self.refresh_queue()
                    self._log(f"Auto-Suche: {queued_count} PDF(s) in Queue gestellt.")
        except Exception as e:
            warning = f"auto_watch_error: {e}"
            self.var_auto_watch_status.set("Auto-Suche: Warnung")
            if warning != self._auto_watch_last_warning:
                self._log(f"Auto-Suche Warnung: {warning}")
            self._auto_watch_last_warning = warning
        finally:
            if self._auto_watch_active:
                self._schedule_auto_watch()

    def scan_watch_dir(self) -> None:
        recursive = self.var_watch_recursive.get()
        paths = list_watch_pdf_paths(self.var_watch_dir.get().strip(), recursive=recursive)
        rows = [format_watch_file_row(path, source="watch") for path in paths]
        self._upsert_file_rows(rows, replace_source="watch")
        self.refresh_queue()
        recursive_label = "ja" if recursive else "nein"
        self._log(f"Watch-Ordner gescannt: {len(rows)} PDF(s), rekursiv={recursive_label}")

    def pick_manual_files(self) -> None:
        files = filedialog.askopenfilenames(title="PDFs waehlen", filetypes=[("PDF Dateien", "*.pdf")])
        rows = [format_watch_file_row(path, source="manual") for path in files]
        self._upsert_file_rows(rows)
        self.refresh_queue()
        self._log(f"Manuelle PDFs hinzugefuegt: {len(rows)}")

    def _upsert_file_rows(self, rows: list[dict[str, str]], *, replace_source: str | None = None) -> None:
        if replace_source is not None:
            self._watch_rows = {
                key: row
                for key, row in self._watch_rows.items()
                if row.get("source") != replace_source
            }
        for row in rows:
            key = normalize_file_row_key(row.get("path", ""))
            if not key:
                continue
            current = dict(self._watch_rows.get(key, {}))
            current.update(row)
            self._watch_rows[key] = current
        self._render_file_rows()

    def _render_file_rows(self) -> None:
        for item in self.tree_files.get_children():
            self.tree_files.delete(item)
        for key, row in self._watch_rows.items():
            self.tree_files.insert(
                "",
                tk.END,
                iid=key,
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
        snapshot = self._build_action_snapshot()
        if not snapshot["rows"]:
            messagebox.showinfo("Extractor", "Bitte zuerst PDFs suchen oder auswaehlen.")
            return
        if any(self._row_is_queued(row) for row in snapshot["rows"]):
            message = (
                "Auswahl enthält Queue-Jobs. Bitte Queue-Verarbeitung nutzen "
                "oder nur nicht-gequeuete Dateien auswählen."
            )
            messagebox.showinfo("Extractor", message)
            self._log(message)
            return
        if not self._start_background_action("Direkte Verarbeitung laeuft..."):
            return
        threading.Thread(target=self._submit_files_thread, args=(snapshot,), daemon=True).start()

    def enqueue_selected_files(self) -> None:
        snapshot = self._build_action_snapshot()
        if not snapshot["rows"]:
            messagebox.showinfo("Queue", "Bitte zuerst PDFs suchen oder auswaehlen.")
            return
        if not self._start_background_action("Queue-Einreihung laeuft..."):
            return
        threading.Thread(target=self._enqueue_files_thread, args=(snapshot,), daemon=True).start()

    def _build_action_snapshot(self) -> dict[str, Any]:
        keys = list(self.tree_files.selection()) or list(self._watch_rows)
        rows = [dict(self._watch_rows[key]) for key in keys if key in self._watch_rows]
        return {
            "project_root": str(self.project_root),
            "output_mode": self.var_output_mode.get(),
            "sqlite_path": self.var_sqlite_path.get().strip() or None,
            "device_id": self._selected_device_id(),
            "rows": rows,
        }

    def _start_background_action(self, message: str) -> bool:
        if self._busy:
            self._log("Aktion laeuft bereits.")
            return False
        self._busy = True
        self.var_technical_status.set("running")
        self.var_status.set(message)
        self.progress.configure(mode="indeterminate")
        self.progress.start(10)
        self._set_action_buttons_state(tk.DISABLED)
        return True

    def _set_action_buttons_state(self, state: str) -> None:
        for button in self._action_buttons:
            button.configure(state=state)

    def _submit_files_thread(self, snapshot: dict[str, Any]) -> None:
        events: list[dict[str, object]] = []
        for row in snapshot["rows"]:
            path = str(row.get("path", ""))
            try:
                res = submit(
                    path,
                    str(snapshot["project_root"]),
                    output_mode=str(snapshot["output_mode"]),
                    sqlite_path=snapshot["sqlite_path"],
                    device_id=snapshot["device_id"],
                )
                summary = format_job_result_summary(
                    pdf_path=res.pdf_path,
                    job_id=res.job_id,
                    status=res.status,
                    details=res.details,
                )
                update = format_submit_row_update(res, snapshot["device_id"])
                events.append({"path": path, "log": summary, "update": update})
            except Exception as e:
                events.append(
                    {
                        "path": path,
                        "log": f"Fehler bei {Path(path).name}: {e}",
                        "update": {"action": "FAIL", "last_error": str(e)},
                    }
                )
        self.after(0, lambda: self._finish_background_action(events))

    def _enqueue_files_thread(self, snapshot: dict[str, Any]) -> None:
        events: list[dict[str, object]] = []
        for row in snapshot["rows"]:
            path = str(row.get("path", ""))
            row_source = str(row.get("source", "manual"))
            source = "test-app-watch" if row_source == "watch" else "test-app-manual"
            try:
                job = enqueue_pdf_job(str(snapshot["project_root"]), path, source=source)
                queue_row = format_queue_job_row(job)
                events.append(
                    {
                        "path": path,
                        "log": format_enqueue_result(job),
                        "update": {
                            "queue_status": queue_row["status"],
                            "job_id": queue_row["job_id"],
                            "last_error": queue_row["last_error"],
                            "action": "queued",
                        },
                    }
                )
            except Exception as e:
                events.append(
                    {
                        "path": path,
                        "log": f"Queue-Fehler bei {Path(path).name}: {e}",
                        "update": {"action": "FAIL", "last_error": str(e)},
                    }
                )
        self.after(0, lambda: self._finish_background_action(events))

    def _finish_background_action(self, events: list[dict[str, object]]) -> None:
        try:
            for event in events:
                path = str(event.get("path", ""))
                key = normalize_file_row_key(path)
                update = event.get("update")
                if key in self._watch_rows and isinstance(update, dict):
                    self._watch_rows[key].update({str(k): str(v) for k, v in update.items()})
                log = event.get("log")
                if log:
                    self._log(str(log))
            self._render_file_rows()
            self.refresh_queue()
        finally:
            self._busy = False
            self.progress.stop()
            self.progress.configure(mode="determinate", value=0)
            self.var_technical_status.set("idle")
            self._set_action_buttons_state(tk.NORMAL)

    def refresh_queue(self) -> None:
        jobs = list_jobs(str(self.project_root))
        rows = [format_queue_job_row(job) for job in jobs]
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
        merged_rows = merge_file_rows_with_queue(
            list(self._watch_rows.values()),
            jobs,
            include_queue_only=True,
        )
        self._watch_rows = {
            normalize_file_row_key(row.get("path", "")): row
            for row in merged_rows
            if normalize_file_row_key(row.get("path", ""))
        }
        self._render_file_rows()

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

    def close_app(self) -> None:
        self.stop_auto_watch(log=False)
        self.destroy()

    def destroy(self) -> None:
        if getattr(self, "_auto_watch_active", False) or getattr(self, "_auto_watch_after_id", None):
            self.stop_auto_watch(log=False)
        super().destroy()


def main(project_root: str | Path | None = None) -> None:
    app = TestApp(project_root=project_root)
    app.mainloop()
