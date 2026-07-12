from __future__ import annotations

import json
import os
import shutil
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from src.dbwriter.api import discard_duplicate_candidate, get_duplicate_candidate, list_duplicate_candidates
from src.jobcontroller.api import submit
from src.ruleresolver.api import validate_rules_integrity
from src.rulesuite.api import activate_draft, create_draft, list_fields, preview_extract, set_field_regex
from src.runtime.api import (
    get_default_device_id,
    get_device_config_status,
    list_devices,
    load_runtime_config,
    resolve_app_root,
)
from src.testui.api import (
    classify_job_outcome,
    format_assay_data_detail,
    format_assay_overview_rows,
    format_duplicate_candidate_detail,
    format_duplicate_candidate_summary,
    format_duplicate_field_comparison,
    format_job_result_summary,
    format_partial_writes_note,
    format_rules_report,
    format_write_outputs,
    format_write_status_lines,
    humanize_job_error,
    load_job_state,
)


class MinimalBatchGUI(tk.Tk):
    """Test UI for real API flows (without watchdog/queue)."""

    def __init__(self) -> None:
        super().__init__()
        self.title("AnalyzerExtractorV2 - Test UI (Direct Mode)")
        self.geometry("1200x820")

        base_dir = resolve_app_root(__file__)
        self.project_root = str(base_dir)
        self.selected_files: list[str] = []
        self._is_running = False
        self.last_job_id: str | None = None
        self._result_jobs: list[dict] = []
        self._result_writes: dict[str, list[dict]] = {}

        cfg = load_runtime_config(self.project_root)
        self.var_project_root = tk.StringVar(value=self.project_root)
        self.var_output_mode = tk.StringVar(value=cfg.output_mode)
        self.var_sqlite_path = tk.StringVar(value=cfg.sqlite_path or "")
        self.var_lock_ttl = tk.StringVar(value=str(cfg.pipeline_lock_ttl_s))
        self.var_sqlite_busy_timeout = tk.StringVar(value=str(cfg.sqlite_busy_timeout_ms))
        self.var_sqlite_retry_count = tk.StringVar(value=str(cfg.sqlite_retry_count))
        self.var_sqlite_retry_sleep = tk.StringVar(value=str(cfg.sqlite_retry_sleep_s))
        self.var_reject_invalid = tk.BooleanVar(value=True)
        self.var_device_choice = tk.StringVar(value="")
        self._device_choice_to_id: dict[str, str] = {}

        self.var_assay_key = tk.StringVar(value="")
        self.var_draft_path = tk.StringVar(value="")
        self.var_field_key = tk.StringVar(value="")
        self.var_field_regex = tk.StringVar(value="")
        self.var_preview_pdf = tk.StringVar(value="")
        self.var_duplicate_status = tk.StringVar(value="pending")
        self._duplicate_details: dict[int, dict[str, object]] = {}

        self._action_buttons: list[tk.Widget] = []
        self._build_ui()

    def _build_ui(self) -> None:
        top = tk.Frame(self)
        top.pack(fill="x", padx=10, pady=8)

        tk.Label(top, text="project_root:").pack(side="left")
        ent_root = tk.Entry(top, textvariable=self.var_project_root)
        ent_root.pack(side="left", fill="x", expand=True, padx=(6, 6))
        self._register_action(ent_root)

        btn_root = tk.Button(top, text="Ordner waehlen...", command=self.on_pick_root)
        btn_root.pack(side="left")
        self._register_action(btn_root)

        self.lbl_status = tk.Label(top, text="Bereit (Direktmodus ohne Watchdog).")
        self.lbl_status.pack(side="right")

        cfg_frame = tk.LabelFrame(self, text="Submit Konfiguration (echte API)")
        cfg_frame.pack(fill="x", padx=10, pady=(0, 8))
        row = tk.Frame(cfg_frame)
        row.pack(fill="x", padx=8, pady=6)

        tk.Label(row, text="output_mode").pack(side="left")
        dd_mode = tk.OptionMenu(row, self.var_output_mode, "both", "excel", "sqlite")
        dd_mode.pack(side="left", padx=(4, 8))
        self._register_action(dd_mode)

        tk.Label(row, text="sqlite_path").pack(side="left")
        ent_sql = tk.Entry(row, textvariable=self.var_sqlite_path, width=36)
        ent_sql.pack(side="left", padx=(4, 8))
        self._register_action(ent_sql)

        tk.Label(row, text="lock_ttl_s").pack(side="left")
        ent_lock = tk.Entry(row, textvariable=self.var_lock_ttl, width=8)
        ent_lock.pack(side="left", padx=(4, 8))
        self._register_action(ent_lock)

        tk.Label(row, text="sqlite_busy_timeout_ms").pack(side="left")
        ent_busy = tk.Entry(row, textvariable=self.var_sqlite_busy_timeout, width=8)
        ent_busy.pack(side="left", padx=(4, 8))
        self._register_action(ent_busy)

        tk.Label(row, text="retry_count").pack(side="left")
        ent_retry_count = tk.Entry(row, textvariable=self.var_sqlite_retry_count, width=5)
        ent_retry_count.pack(side="left", padx=(4, 8))
        self._register_action(ent_retry_count)

        tk.Label(row, text="retry_sleep_s").pack(side="left")
        ent_retry_sleep = tk.Entry(row, textvariable=self.var_sqlite_retry_sleep, width=6)
        ent_retry_sleep.pack(side="left", padx=(4, 8))
        self._register_action(ent_retry_sleep)

        cb_invalid = tk.Checkbutton(row, text="reject_invalid_runs", variable=self.var_reject_invalid)
        cb_invalid.pack(side="left")
        self._register_action(cb_invalid)

        device_row = tk.Frame(cfg_frame)
        device_row.pack(fill="x", padx=8, pady=(0, 6))
        tk.Label(device_row, text="Gerät").pack(side="left")
        self.device_menu = tk.OptionMenu(device_row, self.var_device_choice, "")
        self.device_menu.pack(side="left", padx=(4, 8))
        self._register_action(self.device_menu)
        btn_devices = tk.Button(device_row, text="Geräte neu laden", command=self.on_reload_devices)
        btn_devices.pack(side="left", padx=(0, 8))
        self._register_action(btn_devices)
        self.lbl_device_status = tk.Label(device_row, text="", anchor="w", fg="#8a6d00")
        self.lbl_device_status.pack(side="left", fill="x", expand=True)
        self._refresh_device_choices(log=False)

        note = tk.Label(
            self,
            text="Hinweis: Diese Test-UI nutzt nur Direktaufrufe (submit/rulesuite/validator). "
            "Watchdog, Worker und jobs/queue sind absichtlich ausgeklammert.",
            anchor="w",
        )
        note.pack(fill="x", padx=10, pady=(0, 6))
        known_issues = tk.Label(
            self,
            text="Testbetrieb: SKIPPED/already_done prueft nicht, ob Output-Dateien noch vorhanden sind. "
            "Admin-Aktionen sind Diagnosewerkzeuge; Details siehe docs/KNOWN_ISSUES.md.",
            anchor="w",
            fg="#8a6d00",
        )
        known_issues.pack(fill="x", padx=10, pady=(0, 6))

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        tab_single = tk.Frame(nb)
        tab_batch = tk.Frame(nb)
        tab_preview = tk.Frame(nb)
        tab_rules = tk.Frame(nb)
        tab_duplicates = tk.Frame(nb)
        nb.add(tab_single, text="Single PDF")
        nb.add(tab_batch, text="Batch")
        nb.add(tab_preview, text="Rule Preview")
        nb.add(tab_rules, text="Rules Check")
        nb.add(tab_duplicates, text="Duplikate")

        self._build_single_tab(tab_single)
        self._build_batch_tab(tab_batch)
        self._build_preview_tab(tab_preview)
        self._build_rules_tab(tab_rules)
        self._build_duplicates_tab(tab_duplicates)

        result_frame = tk.LabelFrame(self, text="Ergebnis")
        result_frame.pack(fill="both", expand=False, padx=10, pady=(0, 6))
        self.lbl_result_summary = tk.Label(result_frame, text="Noch kein Lauf.", anchor="w")
        self.lbl_result_summary.pack(fill="x", padx=6, pady=(6, 2))
        self.lbl_result_status = tk.Label(result_frame, text="", anchor="w", fg="#444")
        self.lbl_result_status.pack(fill="x", padx=6, pady=(0, 4))

        trees = tk.Frame(result_frame)
        trees.pack(fill="both", expand=True, padx=6, pady=(0, 4))
        left = tk.Frame(trees)
        left.pack(side="left", fill="both", expand=True, padx=(0, 4))
        right = tk.Frame(trees)
        right.pack(side="left", fill="both", expand=True)

        tk.Label(left, text="Laeufe").pack(anchor="w")
        self.tree_result_jobs = ttk.Treeview(
            left, columns=("pdf", "status", "outcome"), show="headings", height=4
        )
        for col, title, width in (
            ("pdf", "PDF", 280),
            ("status", "Status", 90),
            ("outcome", "Outcome", 70),
        ):
            self.tree_result_jobs.heading(col, text=title)
            self.tree_result_jobs.column(col, width=width, anchor="w")
        self.tree_result_jobs.pack(fill="both", expand=True)
        self.tree_result_jobs.bind("<<TreeviewSelect>>", self.on_result_job_selected)

        tk.Label(right, text="Assays").pack(anchor="w")
        self.tree_result_assays = ttk.Treeview(
            right,
            columns=("assay_key", "lot_id", "ruleset", "missing", "write_status"),
            show="headings",
            height=4,
        )
        for col, title, width in (
            ("assay_key", "Assay", 110),
            ("lot_id", "Lot", 80),
            ("ruleset", "Ruleset", 140),
            ("missing", "Missing", 90),
            ("write_status", "Schreibstatus", 220),
        ):
            self.tree_result_assays.heading(col, text=title)
            self.tree_result_assays.column(col, width=width, anchor="w")
        self.tree_result_assays.pack(fill="both", expand=True)
        self.tree_result_assays.bind("<<TreeviewSelect>>", self.on_result_assay_selected)

        detail_frame = tk.LabelFrame(result_frame, text="Feldwerte (Auswahl)")
        detail_frame.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        self.txt_result_detail = tk.Text(detail_frame, height=8, wrap="word")
        self.txt_result_detail.pack(fill="both", expand=True, padx=4, pady=4)

        log_frame = tk.LabelFrame(self, text="Ausgabe / Testprotokoll")
        log_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.txt_log = tk.Text(log_frame, height=10, wrap="word")
        self.txt_log.pack(fill="both", expand=True, padx=6, pady=6)

    def _build_single_tab(self, parent: tk.Frame) -> None:
        row = tk.Frame(parent)
        row.pack(fill="x", padx=8, pady=8)

        btn_pick = tk.Button(row, text="PDFs auswaehlen...", command=self.on_pick_pdfs)
        btn_pick.pack(side="left")
        self._register_action(btn_pick)

        btn_clear = tk.Button(row, text="Liste leeren", command=self.on_clear_list)
        btn_clear.pack(side="left", padx=(6, 0))
        self._register_action(btn_clear)

        btn_run = tk.Button(row, text="Single E2E starten", command=self.on_run_single)
        btn_run.pack(side="left", padx=(12, 0))
        self._register_action(btn_run)

        btn_rerun = tk.Button(row, text="Force rerun (selektierte PDF)", command=self.on_force_rerun_selected)
        btn_rerun.pack(side="left", padx=(6, 0))
        self._register_action(btn_rerun)

        self.listbox = tk.Listbox(parent, height=10)
        self.listbox.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    def _build_batch_tab(self, parent: tk.Frame) -> None:
        run_frame = tk.LabelFrame(parent, text="Fachlicher Batch-Lauf")
        run_frame.pack(fill="x", padx=8, pady=(8, 4))
        row = tk.Frame(run_frame)
        row.pack(fill="x", padx=8, pady=8)

        btn_run_batch = tk.Button(row, text="Batch E2E starten", command=self.on_run_batch)
        btn_run_batch.pack(side="left")
        self._register_action(btn_run_batch)

        tk.Label(run_frame, text="Batch nutzt die gleiche PDF-Liste wie Single-PDF.").pack(
            anchor="w", padx=8, pady=(0, 8)
        )

        admin_frame = tk.LabelFrame(parent, text="Diagnose / Admin")
        admin_frame.pack(fill="x", padx=8, pady=(8, 4))
        admin_note = tk.Label(
            admin_frame,
            text="Diese Aktionen veraendern Laufzeitartefakte. Force rerun entfernt Job/Lock-Artefakte, aber nicht Excel/SQLite.",
            anchor="w",
            fg="#8a6d00",
        )
        admin_note.pack(fill="x", padx=8, pady=(8, 4))
        admin_row = tk.Frame(admin_frame)
        admin_row.pack(fill="x", padx=8, pady=(0, 8))

        btn_clear_jobs = tk.Button(admin_row, text="/jobs leeren", command=self.on_clear_jobs)
        btn_clear_jobs.pack(side="left")
        self._register_action(btn_clear_jobs)

        btn_clear_out = tk.Button(admin_row, text="/output/final leeren", command=self.on_clear_output_final)
        btn_clear_out.pack(side="left", padx=(8, 0))
        self._register_action(btn_clear_out)

    def _build_preview_tab(self, parent: tk.Frame) -> None:
        row1 = tk.Frame(parent)
        row1.pack(fill="x", padx=8, pady=(8, 4))

        tk.Label(row1, text="assay_key").pack(side="left")
        ent_assay = tk.Entry(row1, textvariable=self.var_assay_key, width=14)
        ent_assay.pack(side="left", padx=(4, 8))
        self._register_action(ent_assay)

        btn_fields = tk.Button(row1, text="Felder laden", command=self.on_list_fields)
        btn_fields.pack(side="left")
        self._register_action(btn_fields)

        btn_create = tk.Button(row1, text="Draft erstellen", command=self.on_create_draft)
        btn_create.pack(side="left", padx=(6, 0))
        self._register_action(btn_create)

        row2 = tk.Frame(parent)
        row2.pack(fill="x", padx=8, pady=(4, 4))
        tk.Label(row2, text="draft_path").pack(side="left")
        ent_draft = tk.Entry(row2, textvariable=self.var_draft_path)
        ent_draft.pack(side="left", fill="x", expand=True, padx=(4, 8))
        self._register_action(ent_draft)

        btn_pick_draft = tk.Button(row2, text="Draft waehlen...", command=self.on_pick_draft)
        btn_pick_draft.pack(side="left")
        self._register_action(btn_pick_draft)

        row3 = tk.Frame(parent)
        row3.pack(fill="x", padx=8, pady=(4, 4))
        tk.Label(row3, text="field_key").pack(side="left")
        ent_field = tk.Entry(row3, textvariable=self.var_field_key, width=16)
        ent_field.pack(side="left", padx=(4, 8))
        self._register_action(ent_field)

        tk.Label(row3, text="regex").pack(side="left")
        ent_regex = tk.Entry(row3, textvariable=self.var_field_regex)
        ent_regex.pack(side="left", fill="x", expand=True, padx=(4, 8))
        self._register_action(ent_regex)

        btn_set = tk.Button(row3, text="Regex setzen", command=self.on_set_field_regex)
        btn_set.pack(side="left")
        self._register_action(btn_set)

        row4 = tk.Frame(parent)
        row4.pack(fill="x", padx=8, pady=(4, 8))
        tk.Label(row4, text="preview_pdf").pack(side="left")
        ent_preview_pdf = tk.Entry(row4, textvariable=self.var_preview_pdf)
        ent_preview_pdf.pack(side="left", fill="x", expand=True, padx=(4, 8))
        self._register_action(ent_preview_pdf)

        btn_pick_pdf = tk.Button(row4, text="PDF waehlen...", command=self.on_pick_preview_pdf)
        btn_pick_pdf.pack(side="left")
        self._register_action(btn_pick_pdf)

        btn_preview = tk.Button(row4, text="Preview (ohne Write)", command=self.on_preview_extract)
        btn_preview.pack(side="left", padx=(6, 0))
        self._register_action(btn_preview)

        btn_activate = tk.Button(row4, text="Draft aktivieren", command=self.on_activate_draft)
        btn_activate.pack(side="left", padx=(6, 0))
        self._register_action(btn_activate)

    def _build_rules_tab(self, parent: tk.Frame) -> None:
        row = tk.Frame(parent)
        row.pack(fill="x", padx=8, pady=8)
        btn_rules = tk.Button(row, text="Rules Integritaet pruefen", command=self.on_rules_check)
        btn_rules.pack(side="left")
        self._register_action(btn_rules)

    def _build_duplicates_tab(self, parent: tk.Frame) -> None:
        top = tk.Frame(parent)
        top.pack(fill="x", padx=8, pady=8)

        btn_refresh = tk.Button(top, text="Aktualisieren", command=self.on_refresh_duplicates)
        btn_refresh.pack(side="left")
        self._register_action(btn_refresh)

        tk.Label(top, text="Status").pack(side="left", padx=(12, 4))
        dd_status = tk.OptionMenu(top, self.var_duplicate_status, "pending", "deleted")
        dd_status.pack(side="left")
        self._register_action(dd_status)

        btn_discard = tk.Button(top, text="Kandidat verwerfen", command=self.on_discard_duplicate_candidate)
        btn_discard.pack(side="right")
        self._register_action(btn_discard)

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

        detail_frame = tk.LabelFrame(parent, text="Duplicate-Details")
        detail_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.txt_duplicate_detail = tk.Text(detail_frame, height=8, wrap="word")
        self.txt_duplicate_detail.pack(fill="both", expand=True, padx=4, pady=4)

        compare_frame = tk.LabelFrame(parent, text="Feldvergleich")
        compare_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.tree_duplicate_fields = ttk.Treeview(
            compare_frame,
            columns=("field", "existing", "candidate", "same"),
            show="headings",
            height=8,
        )
        for col, title, width in (
            ("field", "Feld", 180),
            ("existing", "Bestehend", 320),
            ("candidate", "Kandidat", 320),
            ("same", "Gleich", 70),
        ):
            self.tree_duplicate_fields.heading(col, text=title)
            self.tree_duplicate_fields.column(col, width=width, anchor="w")
        self.tree_duplicate_fields.pack(fill="both", expand=True, padx=4, pady=4)

    def _register_action(self, widget: tk.Widget) -> None:
        self._action_buttons.append(widget)

    def _set_running(self, running: bool, status: str) -> None:
        self._is_running = running
        state = "disabled" if running else "normal"
        for w in self._action_buttons:
            try:
                w.configure(state=state)
            except Exception:
                pass
        self._set_status(status)

    def _log(self, msg: str) -> None:
        def _append() -> None:
            self.txt_log.insert(tk.END, msg + "\n")
            self.txt_log.see(tk.END)

        self.after(0, _append)

    def _set_status(self, msg: str) -> None:
        self.after(0, lambda: self.lbl_status.config(text=msg))

    def _root_path(self) -> Path:
        return Path(self.var_project_root.get().strip())

    def _duplicate_sqlite_path(self) -> Path:
        configured = self.var_sqlite_path.get().strip()
        if configured:
            return Path(configured)
        return self._root_path() / "output" / "final" / "results.sqlite3"

    def _clear_duplicate_view(self) -> None:
        for row in self.tree_duplicates.get_children():
            self.tree_duplicates.delete(row)
        for row in self.tree_duplicate_fields.get_children():
            self.tree_duplicate_fields.delete(row)
        self._duplicate_details = {}
        self._set_duplicate_detail("")

    def _set_duplicate_detail(self, text: str) -> None:
        self.txt_duplicate_detail.configure(state="normal")
        self.txt_duplicate_detail.delete("1.0", tk.END)
        if text:
            self.txt_duplicate_detail.insert(tk.END, text)
        self.txt_duplicate_detail.configure(state="disabled")

    def _selected_duplicate_id(self) -> int | None:
        sel = self.tree_duplicates.selection()
        if not sel:
            return None
        try:
            return int(str(sel[0]))
        except ValueError:
            return None

    def on_refresh_duplicates(self) -> None:
        self._clear_duplicate_view()
        sqlite_path = self._duplicate_sqlite_path()
        if not sqlite_path.exists():
            self._log(f"Duplicate DB nicht gefunden: {sqlite_path}")
            return
        status = self.var_duplicate_status.get().strip() or "pending"
        try:
            rows = list_duplicate_candidates(str(sqlite_path), status=status)
        except Exception as e:
            messagebox.showerror("Duplikate", str(e))
            return
        for row in rows:
            summary = format_duplicate_candidate_summary(row)
            candidate_id = summary.get("candidate_id", "")
            if not candidate_id:
                continue
            self.tree_duplicates.insert(
                "",
                tk.END,
                iid=candidate_id,
                values=(
                    summary.get("candidate_id", ""),
                    summary.get("status", ""),
                    summary.get("assay_key", ""),
                    summary.get("device_id", ""),
                    summary.get("detected_at", ""),
                    summary.get("existing_run_id", ""),
                    summary.get("dedupe_key", ""),
                ),
            )
        self._log(f"Duplikate geladen: status={status}, count={len(rows)}")

    def on_duplicate_selected(self, _event: object = None) -> None:
        candidate_id = self._selected_duplicate_id()
        if candidate_id is None:
            return
        sqlite_path = self._duplicate_sqlite_path()
        try:
            detail = get_duplicate_candidate(str(sqlite_path), candidate_id)
        except Exception as e:
            messagebox.showerror("Duplikate", str(e))
            return
        if not detail:
            self._set_duplicate_detail("(kein Kandidat)")
            return
        self._duplicate_details[candidate_id] = detail
        self._set_duplicate_detail(format_duplicate_candidate_detail(detail))
        for row in self.tree_duplicate_fields.get_children():
            self.tree_duplicate_fields.delete(row)
        for idx, cmp_row in enumerate(format_duplicate_field_comparison(detail)):
            self.tree_duplicate_fields.insert(
                "",
                tk.END,
                iid=f"{candidate_id}:{idx}",
                values=(
                    cmp_row.get("field", ""),
                    cmp_row.get("existing", ""),
                    cmp_row.get("candidate", ""),
                    cmp_row.get("same", ""),
                ),
            )

    def on_discard_duplicate_candidate(self) -> None:
        candidate_id = self._selected_duplicate_id()
        if candidate_id is None:
            messagebox.showinfo("Duplikate", "Bitte zuerst einen Kandidaten auswaehlen.")
            return
        detail = self._duplicate_details.get(candidate_id)
        if detail is None:
            detail = get_duplicate_candidate(str(self._duplicate_sqlite_path()), candidate_id)
            if detail:
                self._duplicate_details[candidate_id] = detail
        candidate = detail.get("candidate") if isinstance(detail, dict) else None
        if not isinstance(candidate, dict) or candidate.get("status") != "pending":
            messagebox.showinfo("Duplikate", "Nur pending Kandidaten koennen verworfen werden.")
            return
        if not messagebox.askyesno("Kandidat verwerfen", f"Kandidat {candidate_id} wirklich verwerfen?"):
            return
        note = simpledialog.askstring("Notiz", "Optionale Notiz:", initialvalue="") or ""
        try:
            result = discard_duplicate_candidate(
                str(self._duplicate_sqlite_path()),
                candidate_id,
                decided_by="test-ui",
                note=note,
            )
        except ValueError as e:
            messagebox.showerror("Duplikate", str(e))
            self.on_refresh_duplicates()
            return
        except Exception as e:
            messagebox.showerror("Duplikate", str(e))
            return
        self._log(
            "Duplicate-Kandidat verworfen: "
            f"id={result.get('candidate_id')} by={result.get('decision_by')}"
        )
        self.on_refresh_duplicates()

    def _refresh_device_choices(self, *, log: bool = True) -> None:
        root = self._root_path()
        devices = list_devices(root)
        default_id = get_default_device_id(root)
        status = get_device_config_status(root)
        self._device_choice_to_id = {}
        menu = self.device_menu["menu"]
        menu.delete(0, "end")
        selected_label = ""
        for device in devices:
            device_id = str(device.get("device_id", "")).strip()
            display_name = str(device.get("display_name", device_id)).strip() or device_id
            if not device_id:
                continue
            label = f"{display_name} ({device_id})"
            self._device_choice_to_id[label] = device_id
            menu.add_command(label=label, command=lambda value=label: self.var_device_choice.set(value))
            if device_id == default_id:
                selected_label = label
        if not selected_label and self._device_choice_to_id:
            selected_label = next(iter(self._device_choice_to_id))
        self.var_device_choice.set(selected_label)

        msg = ""
        if bool(status.get("using_fallback")):
            msg = str(status.get("message", "Geräte-Fallback aktiv."))
        self.lbl_device_status.config(text=msg)
        if log and msg:
            self._log(f"Geräte-Konfiguration: {msg}")

    def _selected_device_id(self) -> str | None:
        label = self.var_device_choice.get()
        return self._device_choice_to_id.get(label)

    def on_reload_devices(self) -> None:
        self._refresh_device_choices(log=True)

    def on_pick_root(self) -> None:
        if self._is_running:
            return
        d = filedialog.askdirectory(title="Projekt-Root waehlen")
        if d:
            self.var_project_root.set(d)
            self._refresh_device_choices(log=True)
            self._log(f"project_root gesetzt: {d}")

    def on_pick_pdfs(self) -> None:
        if self._is_running:
            return
        files = filedialog.askopenfilenames(title="PDFs waehlen", filetypes=[("PDF Dateien", "*.pdf")])
        if not files:
            return
        for f in files:
            if f not in self.selected_files:
                self.selected_files.append(f)
        self._refresh_listbox()
        self._log(f"PDFs hinzugefuegt: {len(files)} | Gesamt: {len(self.selected_files)}")

    def on_clear_list(self) -> None:
        if self._is_running:
            return
        self.selected_files = []
        self._refresh_listbox()
        self._log("PDF-Liste geleert.")

    def _refresh_listbox(self) -> None:
        self.listbox.delete(0, tk.END)
        for p in self.selected_files:
            self.listbox.insert(tk.END, p)

    def _selected_pdf(self) -> str | None:
        if not self.selected_files:
            return None
        sel = self.listbox.curselection()
        if sel:
            return self.selected_files[int(sel[0])]
        return self.selected_files[0]

    def _read_submit_config(self) -> dict:
        return {
            "output_mode": self.var_output_mode.get().strip() or "both",
            "sqlite_path": self.var_sqlite_path.get().strip() or None,
            "lock_ttl_s": float(self.var_lock_ttl.get().strip() or "900"),
            "sqlite_busy_timeout_ms": int(self.var_sqlite_busy_timeout.get().strip() or "5000"),
            "sqlite_retry_count": int(self.var_sqlite_retry_count.get().strip() or "3"),
            "sqlite_retry_sleep_s": float(self.var_sqlite_retry_sleep.get().strip() or "0.2"),
            "device_id": self._selected_device_id(),
        }

    def _with_env(self) -> None:
        os.environ["ARE_REJECT_INVALID_RUNS"] = "1" if self.var_reject_invalid.get() else "0"

    def on_run_single(self) -> None:
        if self._is_running:
            return
        root = self._root_path()
        pdf = self._selected_pdf()
        if not root.exists():
            messagebox.showerror("Fehler", f"project_root existiert nicht:\n{root}")
            return
        if not pdf:
            messagebox.showinfo("Info", "Bitte zuerst PDF(s) waehlen.")
            return
        self._set_running(True, "Single-Test laeuft...")
        threading.Thread(target=self._run_single_thread, args=(str(root), pdf), daemon=True).start()

    def _run_single_thread(self, root: str, pdf: str) -> None:
        try:
            self._with_env()
            cfg = self._read_submit_config()
            self._log(f"=== Single E2E: {pdf} ===")
            res = submit(pdf, root, **cfg)
            self.last_job_id = res.job_id
            self._result_jobs = []
            self._result_writes = {}
            self._present_job_result(res, root, clear_jobs=True)
            self._log("=== Ende Single E2E ===\n")
        except Exception as e:
            self._log(f"[ERROR] {e}")
            self._set_status(f"Fehler: {e}")
        finally:
            self._set_running(False, "Bereit.")

    def _present_job_result(self, res, root: str, *, clear_jobs: bool = False) -> None:
        outcome = classify_job_outcome(res.status, res.details)
        summary = format_job_result_summary(
            pdf_path=res.pdf_path,
            job_id=res.job_id,
            status=res.status,
            details=res.details,
            outcome=outcome,
        )
        human = humanize_job_error(
            str(res.details.get("error") or ""),
            str(res.details.get("reason") or "") or None,
        )
        partial_note = format_partial_writes_note(res.details)

        self._log(f"result={outcome} status={res.status} job_id={res.job_id}")
        if res.details.get("reason"):
            self._log(f"reason={res.details.get('reason')}")
            if res.details.get("reason") == "already_done":
                self._log("Hinweis: already_done prueft nicht, ob Excel/SQLite noch existiert.")
        if human:
            self._log(f"info={human}")
        if res.details.get("error"):
            self._log(f"error={res.details.get('error')}")
        if partial_note:
            self._log(partial_note)
        for line in format_write_outputs(res.details):
            self._log(line)
        if res.job_id:
            self._print_job_state(root, res.job_id)

        writes = res.details.get("writes") or res.details.get("partial_writes") or []
        storage_key = res.job_id or f"run:{len(self._result_jobs)}"
        if isinstance(writes, list):
            self._result_writes[storage_key] = [w for w in writes if isinstance(w, dict)]
        else:
            self._result_writes[storage_key] = []

        job_row = {
            "job_id": res.job_id,
            "storage_key": storage_key,
            "pdf_path": res.pdf_path,
            "status": res.status,
            "outcome": outcome,
            "summary": summary,
            "human": human,
            "partial_note": partial_note,
            "details": dict(res.details),
        }
        if clear_jobs:
            self._result_jobs = [job_row]
        else:
            self._result_jobs.append(job_row)

        def _update_ui() -> None:
            self.lbl_result_summary.config(text=summary)
            status_parts = [p for p in (human, partial_note) if p]
            self.lbl_result_status.config(text=" | ".join(status_parts))
            self._refresh_result_jobs_tree(select_job_id=res.job_id or storage_key)
            self._populate_assay_tree(storage_key)
            self._set_status(summary)

        self.after(0, _update_ui)

    def _refresh_result_jobs_tree(self, select_job_id: str | None = None) -> None:
        for row in self.tree_result_jobs.get_children():
            self.tree_result_jobs.delete(row)
        selected = None
        for idx, row in enumerate(self._result_jobs):
            pdf_name = Path(str(row.get("pdf_path", ""))).name
            storage_key = str(row.get("storage_key") or row.get("job_id") or f"run:{idx}")
            item = self.tree_result_jobs.insert(
                "",
                tk.END,
                iid=storage_key,
                values=(pdf_name, row.get("status", ""), row.get("outcome", "")),
            )
            if select_job_id and storage_key == select_job_id:
                selected = item
            elif select_job_id and row.get("job_id") == select_job_id:
                selected = item
        if selected:
            self.tree_result_jobs.selection_set(selected)
            self.tree_result_jobs.focus(selected)

    def _populate_assay_tree(self, storage_key: str) -> None:
        for row in self.tree_result_assays.get_children():
            self.tree_result_assays.delete(row)
        self._clear_result_detail()
        writes = self._result_writes.get(storage_key, [])
        for idx, overview in enumerate(format_assay_overview_rows(writes)):
            self.tree_result_assays.insert(
                "",
                tk.END,
                iid=f"{storage_key}:{idx}",
                values=(
                    overview.get("assay_key", ""),
                    overview.get("lot_id", ""),
                    overview.get("ruleset_file", ""),
                    overview.get("missing_required", ""),
                    overview.get("write_status", ""),
                ),
            )

    def _clear_result_detail(self) -> None:
        self.txt_result_detail.configure(state="normal")
        self.txt_result_detail.delete("1.0", tk.END)
        self.txt_result_detail.configure(state="disabled")

    def on_result_job_selected(self, _event: object = None) -> None:
        sel = self.tree_result_jobs.selection()
        if not sel:
            return
        storage_key = str(sel[0])
        row = next(
            (r for r in self._result_jobs if str(r.get("storage_key") or r.get("job_id")) == storage_key),
            None,
        )
        if row:
            self.lbl_result_summary.config(text=str(row.get("summary", "")))
            status_parts = [p for p in (row.get("human"), row.get("partial_note")) if p]
            self.lbl_result_status.config(text=" | ".join(status_parts))
        self._populate_assay_tree(storage_key)

    def on_result_assay_selected(self, _event: object = None) -> None:
        sel = self.tree_result_assays.selection()
        if not sel:
            return
        iid = str(sel[0])
        if ":" not in iid:
            return
        storage_key, idx_raw = iid.split(":", 1)
        try:
            idx = int(idx_raw)
        except ValueError:
            return
        writes = self._result_writes.get(storage_key, [])
        if idx < 0 or idx >= len(writes):
            return
        write_item = writes[idx]
        detail = format_assay_data_detail(write_item)
        write_lines = format_write_status_lines(write_item.get("outputs"))
        text = detail
        if write_lines:
            text += "\n\n--- Schreibziele ---\n" + "\n".join(write_lines)
        self.txt_result_detail.configure(state="normal")
        self.txt_result_detail.delete("1.0", tk.END)
        self.txt_result_detail.insert(tk.END, text)
        self.txt_result_detail.configure(state="disabled")

    def on_run_batch(self) -> None:
        if self._is_running:
            return
        root = self._root_path()
        if not root.exists():
            messagebox.showerror("Fehler", f"project_root existiert nicht:\n{root}")
            return
        if not self.selected_files:
            messagebox.showinfo("Info", "Bitte zuerst PDF(s) waehlen.")
            return
        self._set_running(True, "Batch-Test laeuft...")
        threading.Thread(target=self._run_batch_thread, args=(str(root),), daemon=True).start()

    def _run_batch_thread(self, root: str) -> None:
        total = len(self.selected_files)
        passed = 0
        warned = 0
        failed = 0
        cfg = self._read_submit_config()
        try:
            self._with_env()
            self._log(f"=== Batch E2E gestartet | total={total} ===")
            self._result_jobs = []
            self._result_writes = {}
            for i, pdf in enumerate(self.selected_files, start=1):
                self._set_status(f"Batch {i}/{total}")
                res = submit(pdf, root, **cfg)
                outcome = classify_job_outcome(res.status, res.details)
                if outcome == "PASS":
                    passed += 1
                elif outcome == "WARN":
                    warned += 1
                else:
                    failed += 1
                self._present_job_result(res, root, clear_jobs=False)
                self._log(f"[{i}/{total}] {Path(pdf).name}: {outcome} ({res.status}) job_id={res.job_id}")
            self._log(f"=== Batch Ende | PASS={passed} WARN={warned} FAIL={failed} ===\n")
        except Exception as e:
            self._log(f"[ERROR] Batch exception: {e}")
        finally:
            self._set_running(False, "Bereit.")

    def on_clear_jobs(self) -> None:
        if self._is_running:
            return
        jobs_dir = self._root_path() / "jobs"
        if not jobs_dir.exists():
            messagebox.showinfo("Info", f"Ordner existiert nicht:\n{jobs_dir}")
            return
        if not messagebox.askyesno("Bestaetigung", f"Wirklich alles in /jobs loeschen?\n{jobs_dir}"):
            return
        deleted = self._clear_directory_contents(jobs_dir)
        self._log(f"/jobs geleert ({deleted} Eintraege).")

    def on_clear_output_final(self) -> None:
        if self._is_running:
            return
        out_dir = self._root_path() / "output" / "final"
        if not out_dir.exists():
            messagebox.showinfo("Info", f"Ordner existiert nicht:\n{out_dir}")
            return
        if not messagebox.askyesno("Bestaetigung", f"Wirklich alles in /output/final loeschen?\n{out_dir}"):
            return
        deleted = self._clear_directory_contents(out_dir)
        self._log(f"/output/final geleert ({deleted} Eintraege).")

    def on_force_rerun_selected(self) -> None:
        if self._is_running:
            return
        root = self._root_path()
        pdf = self._selected_pdf()
        if not pdf:
            messagebox.showinfo("Info", "Bitte eine PDF auswaehlen.")
            return
        if not messagebox.askyesno(
            "Force rerun",
            "Job-Artefakte fuer diese PDF entfernen?\n\n"
            f"{pdf}\n\n"
            "Hinweis: Excel- und SQLite-Ausgaben werden dadurch nicht geloescht.",
        ):
            return
        try:
            job_id = self._compute_job_id(Path(pdf))
            jobs_dir = root / "jobs"
            locks_dir = root / "locks"
            removed = 0
            for p in jobs_dir.glob(f"{job_id}*"):
                if p.is_file():
                    p.unlink(missing_ok=True)
                    removed += 1
            lock = locks_dir / f"{job_id}.lock"
            if lock.exists():
                lock.unlink(missing_ok=True)
                removed += 1
            self._log(f"Force rerun vorbereitet: job_id={job_id}, geloeschte Artefakte={removed}")
        except Exception as e:
            messagebox.showerror("Fehler", str(e))

    def on_pick_draft(self) -> None:
        if self._is_running:
            return
        p = filedialog.askopenfilename(title="Draft waehlen", filetypes=[("JSON", "*.json")])
        if p:
            self.var_draft_path.set(p)

    def on_pick_preview_pdf(self) -> None:
        if self._is_running:
            return
        p = filedialog.askopenfilename(title="Preview PDF waehlen", filetypes=[("PDF", "*.pdf")])
        if p:
            self.var_preview_pdf.set(p)

    def on_list_fields(self) -> None:
        if self._is_running:
            return
        root = str(self._root_path())
        assay = self.var_assay_key.get().strip()
        if not assay:
            messagebox.showinfo("Info", "Bitte assay_key angeben.")
            return
        try:
            fields = list_fields(root, assay)
            self._log(f"RuleSuite fields ({assay}): {fields}")
        except Exception as e:
            self._log(f"[ERROR] list_fields: {e}")

    def on_create_draft(self) -> None:
        if self._is_running:
            return
        root = str(self._root_path())
        assay = self.var_assay_key.get().strip()
        if not assay:
            messagebox.showinfo("Info", "Bitte assay_key angeben.")
            return
        try:
            path = create_draft(root, assay)
            self.var_draft_path.set(path)
            self._log(f"Draft erstellt: {path}")
        except Exception as e:
            self._log(f"[ERROR] create_draft: {e}")

    def on_set_field_regex(self) -> None:
        if self._is_running:
            return
        draft = self.var_draft_path.get().strip()
        field_key = self.var_field_key.get().strip()
        regex = self.var_field_regex.get().strip()
        if not draft or not field_key or not regex:
            messagebox.showinfo("Info", "draft_path, field_key und regex sind erforderlich.")
            return
        try:
            out = set_field_regex(draft, field_key, regex)
            self._log(f"Regex gesetzt: {out} | {field_key}")
        except Exception as e:
            self._log(f"[ERROR] set_field_regex: {e}")

    def on_preview_extract(self) -> None:
        if self._is_running:
            return
        root = str(self._root_path())
        assay = self.var_assay_key.get().strip()
        pdf = self.var_preview_pdf.get().strip()
        draft = self.var_draft_path.get().strip() or None
        if not assay or not pdf:
            messagebox.showinfo("Info", "assay_key und preview_pdf sind erforderlich.")
            return
        self._set_running(True, "Rule Preview laeuft...")
        threading.Thread(target=self._preview_thread, args=(root, pdf, assay, draft), daemon=True).start()

    def _preview_thread(self, root: str, pdf: str, assay: str, draft: str | None) -> None:
        try:
            out = preview_extract(root, pdf, assay, draft_path=draft)
            self._log("=== Rule Preview ===")
            self._log(json.dumps(out, ensure_ascii=False, indent=2))
            self._log("=== Ende Rule Preview ===\n")
        except Exception as e:
            self._log(f"[ERROR] preview_extract: {e}")
        finally:
            self._set_running(False, "Bereit.")

    def on_activate_draft(self) -> None:
        if self._is_running:
            return
        root = str(self._root_path())
        assay = self.var_assay_key.get().strip()
        draft = self.var_draft_path.get().strip()
        if not assay or not draft:
            messagebox.showinfo("Info", "assay_key und draft_path sind erforderlich.")
            return
        if not messagebox.askyesno("Bestaetigung", f"Draft wirklich aktivieren?\n{draft}"):
            return
        try:
            path = activate_draft(root, assay, draft)
            self._log(f"Draft aktiviert -> {path}")
        except Exception as e:
            self._log(f"[ERROR] activate_draft: {e}")

    def on_rules_check(self) -> None:
        if self._is_running:
            return
        root = self._root_path()
        try:
            report = validate_rules_integrity(str(root / "rules"), str(root / "rules" / "index.json"))
            self._log("=== Rules Integritaet ===")
            for ln in format_rules_report(report):
                self._log(ln)
            self._log(json.dumps(report, ensure_ascii=False, indent=2))
            has_issues = any(bool(v) for v in report.values())
            self._log("RESULT: " + ("FAIL" if has_issues else "PASS"))
            self._log("=== Ende Rules Integritaet ===\n")
        except Exception as e:
            self._log(f"[ERROR] rules_check: {e}")

    def _print_job_state(self, root: str, job_id: str) -> None:
        if not job_id:
            return
        state_path = Path(root) / "jobs" / f"{job_id}.json"
        if not state_path.exists():
            self._log(f"state_not_found: {state_path}")
            return
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except Exception as e:
            self._log(f"state_read_error: {e}")
            return

        self._log(f"state_status={state.get('status')}")
        if state.get("error"):
            self._log(f"state_error={state.get('error')}")
        for step in state.get("steps", []):
            if not isinstance(step, dict):
                continue
            step_name = step.get("step", "unknown")
            self._log(f"[{step_name}]")
            for k, v in step.items():
                if k == "step":
                    continue
                self._log(f"  {k}: {v}")

    def _clear_directory_contents(self, dir_path: Path) -> int:
        count = 0
        for item in dir_path.iterdir():
            try:
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
                count += 1
            except Exception as e:
                self._log(f"[WARN] delete failed: {item} -> {e}")
        return count

    def _compute_job_id(self, path: Path) -> str:
        import hashlib

        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()[:16]


def run_startup_smoke_check(project_root: str | Path | None = None) -> None:
    root = Path(project_root) if project_root is not None else resolve_app_root(__file__)
    rules_dir = root / "rules"
    index_path = rules_dir / "index.json"
    report = validate_rules_integrity(str(rules_dir), str(index_path))
    has_issues = any(bool(v) for v in report.values())
    if has_issues:
        raise RuntimeError(f"rules_integrity_failed: {json.dumps(report, ensure_ascii=False)}")
    _ = load_runtime_config(root)


if __name__ == "__main__":
    if os.getenv("ARE_SMOKE_EXIT", "").strip() == "1":
        run_startup_smoke_check()
    else:
        app = MinimalBatchGUI()
        app.mainloop()
