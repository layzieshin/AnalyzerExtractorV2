from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from interfaces.common.queue_worker import QueueWorkerConfig, process_next_pending
from src.assaycandidate.api import (
    annotate_assay_candidates,
    find_assay_candidates,
    load_known_assay_keys,
)
from src.dbwriter.api import discard_duplicate_candidate, get_duplicate_candidate, list_duplicate_candidates
from src.jobqueue.api import enqueue_pdf_job, list_jobs, retry_failed_job
from src.ruleresolver.api import resolve_ruleset, validate_rules_integrity
from src.rulesuite.api import create_draft_from_template_if_missing, list_rulesets
from src.runtime.api import list_devices, load_runtime_config, resolve_app_root
from src.resultstore.api import (
    get_result_store_status,
    list_result_assays,
    list_result_charges,
    list_result_runs,
)
from src.testui.api import (
    REWORK_FILTER_LABELS,
    build_assay_filter_choices,
    build_rework_items,
    build_result_column_catalog,
    build_result_display_context,
    default_result_columns,
    filter_rework_items,
    format_device_choice,
    format_duplicate_candidate_detail,
    format_duplicate_candidate_summary,
    format_duplicate_field_comparison,
    format_extractor_file_row,
    format_queue_job_row,
    format_result_run_detail,
    format_result_run_row,
    format_rework_context_text,
    format_rework_item_detail,
    format_rework_item_summary,
    format_runtime_options_summary,
    format_validation_status,
    merge_file_rows_with_queue,
    normalize_file_row_key,
    normalize_visible_result_columns,
    preferred_rework_dump_path,
    resolve_rework_context_source,
)

from .scroll_helpers import TreeviewSorter, create_scrollable_treeview
from .watch_scan import InAppWatchScanner, list_watch_pdf_paths

BASE_SECTION_KEYS = ("EXTRACTOR", "OPTIONS", "RULE SUITE", "LOGS", "DUPLIKATE", "DATENBANK")
ADMIN_SECTION_KEY = "ADMIN"
SECTION_KEYS = BASE_SECTION_KEYS + (ADMIN_SECTION_KEY,)


def _env_flag_enabled(name: str) -> bool:
    flag = os.environ.get(name, "").strip().lower()
    return flag in {"1", "true", "yes"}


def resolve_visible_section_keys() -> tuple[str, ...]:
    if _env_flag_enabled("ARE_SHOW_ADMIN"):
        return BASE_SECTION_KEYS + (ADMIN_SECTION_KEY,)
    return BASE_SECTION_KEYS


def legacy_ui_enabled() -> bool:
    return _env_flag_enabled("ARE_LEGACY_UI")


REWORK_CANDIDATE_STATUS_LABELS = {
    "known": "bekannt",
    "unknown": "unbekannt",
    "unchecked": "ungeprüft",
}

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
        self._queue_processing_ttl_s = float(cfg.queue_processing_ttl_s)
        self._queue_claim_lock_ttl_s = float(cfg.queue_claim_lock_ttl_s)
        self._queue_max_attempts = int(cfg.queue_max_attempts)
        self._pipeline_lock_ttl_s = float(cfg.pipeline_lock_ttl_s)
        self._sqlite_busy_timeout_ms = int(cfg.sqlite_busy_timeout_ms)
        self._sqlite_retry_count = int(cfg.sqlite_retry_count)
        self._sqlite_retry_sleep_s = float(cfg.sqlite_retry_sleep_s)
        self._auto_watch_active = False
        self._auto_watch_after_id: str | None = None
        self._auto_watch_scanner = InAppWatchScanner()
        self._auto_watch_last_warning = ""
        self._auto_watch_suppressed_paths: set[str] = set()
        self._device_choice_to_id: dict[str, str] = {}
        self._watch_rows: dict[str, dict[str, str]] = {}
        self._duplicate_details: dict[int, dict[str, object]] = {}
        self._rework_items: dict[str, dict[str, object]] = {}
        self._rework_items_all: list[dict[str, object]] = []
        self._rework_candidates_by_id: dict[str, dict[str, str]] = {}
        self.var_rework_filter = tk.StringVar(value="Alle")
        self.var_db_assay = tk.StringVar(value="")
        self.var_db_charge = tk.StringVar(value="")
        self.var_db_status = tk.StringVar(value="Datenbank noch nicht geladen.")
        self._db_runs: list[dict[str, object]] = []
        self._db_runs_by_id: dict[str, dict[str, object]] = {}
        self._db_visible_columns: list[str] = default_result_columns()
        self._db_column_catalog: dict[str, str] = {}
        self._db_assay_choice_to_key: dict[str, str] = {}
        self._db_display_context: dict[str, object] = {"assay_labels": {}, "payload_labels": {}}
        self._db_rulesets: list[dict[str, object]] = []
        self._tree_db_sorter: TreeviewSorter | None = None
        self._admin_enabled = os.environ.get("ARE_SHOW_ADMIN", "").strip().lower() in {"1", "true", "yes"}
        self._busy = False
        self._extraction_running = False
        self._stop_extraction_event = threading.Event()
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
        for key in resolve_visible_section_keys():
            frame = tk.Frame(self.notebook)
            self._tabs[key] = frame
            self.notebook.add(frame, text=key)

        self._build_extractor_tab(self._tabs["EXTRACTOR"])
        self._build_options_tab(self._tabs["OPTIONS"])
        self._build_rule_suite_tab(self._tabs["RULE SUITE"])
        self._build_logs_tab(self._tabs["LOGS"])
        self._build_duplicates_tab(self._tabs["DUPLIKATE"])
        self._build_database_tab(self._tabs["DATENBANK"])
        if self._admin_enabled:
            self._build_admin_tab(self._tabs[ADMIN_SECTION_KEY])

        status = tk.Frame(self)
        status.pack(fill="x", padx=10, pady=(0, 10))
        tk.Label(status, textvariable=self.var_status, anchor="w").pack(side="left", fill="x", expand=True)
        self.progress = ttk.Progressbar(status, mode="determinate", length=180)
        self.progress.pack(side="left", padx=(8, 12))
        tk.Label(status, textvariable=self.var_technical_status, anchor="e", width=28).pack(side="right")

    def _build_extractor_tab(self, parent: tk.Frame) -> None:
        controls = tk.Frame(parent)
        controls.pack(fill="x", padx=8, pady=8)
        self.btn_scan_watch = tk.Button(controls, text="Ergebnisse suchen", command=self.scan_watch_dir)
        self.btn_scan_watch.pack(side="left")
        self.btn_pick_files = tk.Button(controls, text="Dateien hinzufügen", command=self.pick_manual_files)
        self.btn_pick_files.pack(side="left", padx=(6, 0))
        self.btn_start_extraction = tk.Button(controls, text="Extraktion starten", command=self.start_extraction)
        self.btn_start_extraction.pack(side="left", padx=(6, 0))
        self.btn_stop_extraction = tk.Button(
            controls,
            text="Extraktion stoppen",
            command=self.stop_extraction,
            state=tk.DISABLED,
        )
        self.btn_stop_extraction.pack(side="left", padx=(6, 0))
        self.btn_retry_failed = tk.Button(
            controls,
            text="Fehler erneut verarbeiten",
            command=self.retry_selected_failed_jobs,
        )
        self.btn_retry_failed.pack(side="left", padx=(6, 0))
        self.btn_refresh_queue = tk.Button(controls, text="Aktualisieren", command=self.refresh_queue)
        self.btn_refresh_queue.pack(side="left", padx=(6, 0))
        self.btn_auto_watch_start = tk.Button(controls, text="Automatische Suche starten", command=self.start_auto_watch)
        self.btn_auto_watch_start.pack(side="left", padx=(18, 0))
        self.btn_auto_watch_stop = tk.Button(controls, text="Automatische Suche stoppen", command=self.stop_auto_watch)
        self.btn_auto_watch_stop.pack(side="left", padx=(6, 0))
        tk.Checkbutton(controls, text="Unterordner einbeziehen", variable=self.var_watch_recursive).pack(
            side="left", padx=(12, 0)
        )
        self._action_buttons.extend(
            [
                self.btn_scan_watch,
                self.btn_pick_files,
                self.btn_start_extraction,
                self.btn_retry_failed,
                self.btn_refresh_queue,
            ]
        )

        auto_status = tk.Frame(parent)
        auto_status.pack(fill="x", padx=8, pady=(0, 6))
        tk.Label(auto_status, textvariable=self.var_auto_watch_status, anchor="w", width=26).pack(side="left")
        tk.Label(auto_status, textvariable=self.var_auto_watch_last_scan, anchor="w", width=26).pack(side="left")
        tk.Label(auto_status, textvariable=self.var_auto_watch_found, anchor="w").pack(side="left", fill="x", expand=True)

        self.tree_files, files_frame = create_scrollable_treeview(
            parent,
            columns=("file", "source", "queue_status", "device_id", "last_error", "action", "path", "job_id"),
            show="headings",
            height=16,
        )
        file_headings = {
            "file": "Datei",
            "source": "Herkunft",
            "queue_status": "Status",
            "device_id": "Geraet",
            "last_error": "Letzter Fehler",
            "action": "Verarbeitung",
            "path": "Pfad",
            "job_id": "Job-ID",
        }
        for col, title, width in (
            ("file", "Datei", 190),
            ("source", "Herkunft", 150),
            ("queue_status", "Status", 110),
            ("device_id", "Geraet", 120),
            ("last_error", "Letzter Fehler", 200),
            ("action", "Verarbeitung", 170),
            ("path", "Pfad", 360),
            ("job_id", "Job-ID", 140),
        ):
            self.tree_files.column(col, width=width, anchor="w")
        self._tree_files_sorter = TreeviewSorter(self.tree_files)
        self._tree_files_sorter.attach(file_headings)
        files_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))

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

        tk.Button(form, text="Anzeigen", command=self._refresh_options_summary).grid(
            row=4, column=1, sticky="w", padx=6, pady=(4, 8)
        )

        self.txt_options = tk.Text(parent, height=8, wrap="word")
        self.txt_options.pack(fill="x", padx=8, pady=(0, 8))
        self.txt_options.configure(state="disabled")

    def _build_rule_suite_tab(self, parent: tk.Frame) -> None:
        controls = tk.Frame(parent)
        controls.pack(fill="x", padx=8, pady=8)
        tk.Button(controls, text="Nacharbeit aktualisieren", command=self.refresh_rework_items).pack(side="left")
        tk.Button(controls, text="Kontext anzeigen", command=self.show_rework_context).pack(side="left", padx=(6, 0))
        tk.Button(controls, text="Rule Editor oeffnen", command=self.open_rule_editor_from_rework).pack(side="left", padx=(6, 0))
        tk.Button(controls, text="Nacharbeit wiederholen", command=self.retry_selected_rework_items).pack(
            side="left", padx=(6, 0)
        )
        tk.Button(controls, text="Rules validieren", command=self.validate_rules).pack(side="left", padx=(6, 0))
        tk.Button(controls, text="Assay-Kandidaten prüfen", command=self.preview_assay_candidates).pack(
            side="left", padx=(6, 0)
        )
        tk.Label(controls, text="Filter").pack(side="left", padx=(12, 4))
        self.cmb_rework_filter = ttk.Combobox(
            controls,
            textvariable=self.var_rework_filter,
            values=list(REWORK_FILTER_LABELS),
            state="readonly",
            width=24,
        )
        self.cmb_rework_filter.pack(side="left")
        self.cmb_rework_filter.bind("<<ComboboxSelected>>", self._on_rework_filter_changed)
        self.lbl_validation = tk.Label(parent, text="Noch keine Validierung.", anchor="w")
        self.lbl_validation.pack(fill="x", padx=8, pady=(0, 8))

        rework_frame = tk.LabelFrame(parent, text="Nacharbeit aus fehlgeschlagenen Arbeitslisten-Jobs")
        rework_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.tree_rework, rework_tree_frame = create_scrollable_treeview(
            rework_frame,
            columns=("file", "error_label", "queue_status", "job_id", "context_label"),
            show="headings",
            height=8,
        )
        rework_headings = {
            "file": "Datei",
            "error_label": "Fehler",
            "queue_status": "Status",
            "job_id": "Job-ID",
            "context_label": "Kontext",
        }
        for col, title, width in (
            ("file", "Datei", 190),
            ("error_label", "Fehler", 180),
            ("queue_status", "Status", 110),
            ("job_id", "Job-ID", 140),
            ("context_label", "Kontext", 180),
        ):
            self.tree_rework.column(col, width=width, anchor="w")
        self._tree_rework_sorter = TreeviewSorter(self.tree_rework)
        self._tree_rework_sorter.attach(rework_headings)
        rework_tree_frame.pack(fill="both", expand=True, padx=8, pady=8)
        self.tree_rework.bind("<<TreeviewSelect>>", self.on_rework_selected)

        candidate_frame = tk.LabelFrame(rework_frame, text="Assay-Kandidaten")
        candidate_frame.pack(fill="x", padx=8, pady=(0, 8))
        self.lbl_rework_candidates = tk.Label(
            candidate_frame,
            text="Noch keine Kandidaten geprüft.",
            anchor="w",
        )
        self.lbl_rework_candidates.pack(fill="x", padx=8, pady=(8, 4))
        self.tree_rework_candidates, candidates_frame = create_scrollable_treeview(
            candidate_frame,
            columns=("assay_key", "name", "file", "line_no", "status", "confidence", "reason"),
            show="headings",
            height=4,
        )
        for col, title, width in (
            ("assay_key", "Assay-Key", 90),
            ("name", "Name", 150),
            ("file", "Datei", 170),
            ("line_no", "Zeile", 55),
            ("status", "Status", 95),
            ("confidence", "Confidence", 85),
            ("reason", "Grund", 120),
        ):
            self.tree_rework_candidates.heading(col, text=title)
            self.tree_rework_candidates.column(col, width=width, anchor="w")
        candidates_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        tk.Button(
            candidate_frame,
            text="Draft aus Kandidat erstellen",
            command=self.create_draft_from_rework_candidate,
        ).pack(anchor="w", padx=8, pady=(0, 8))

        self.txt_rework_detail = tk.Text(rework_frame, height=10, wrap="word")
        self.txt_rework_detail.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.txt_rework_detail.configure(state="disabled")

    def _build_logs_tab(self, parent: tk.Frame) -> None:
        self.txt_logs = tk.Text(parent, height=20, wrap="word")
        self.txt_logs.pack(fill="both", expand=True, padx=8, pady=8)
        self.txt_logs.configure(state="disabled")

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

        self.tree_duplicates, duplicates_frame = create_scrollable_treeview(
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
        duplicates_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.tree_duplicates.bind("<<TreeviewSelect>>", self.on_duplicate_selected)

        self.txt_duplicate_detail = tk.Text(parent, height=8, wrap="word")
        self.txt_duplicate_detail.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.tree_duplicate_fields, duplicate_fields_frame = create_scrollable_treeview(
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
        duplicate_fields_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    def _build_database_tab(self, parent: tk.Frame) -> None:
        controls = tk.Frame(parent)
        controls.pack(fill="x", padx=8, pady=8)
        tk.Button(controls, text="Datenbank laden", command=self.refresh_database).pack(side="left")
        tk.Label(controls, text="Assay").pack(side="left", padx=(12, 4))
        self.cmb_db_assay = ttk.Combobox(controls, textvariable=self.var_db_assay, state="readonly", width=34)
        self.cmb_db_assay.pack(side="left")
        self.cmb_db_assay.bind("<<ComboboxSelected>>", self.on_db_assay_selected)
        tk.Label(controls, text="CHARGE").pack(side="left", padx=(12, 4))
        self.cmb_db_charge = ttk.Combobox(controls, textvariable=self.var_db_charge, state="readonly", width=18)
        self.cmb_db_charge.pack(side="left")
        tk.Button(controls, text="Einträge anzeigen", command=self.show_database_runs).pack(side="left", padx=(12, 0))
        tk.Button(controls, text="Spalten ein-/ausblenden...", command=self.configure_database_columns).pack(
            side="left", padx=(6, 0)
        )

        status = tk.Frame(parent)
        status.pack(fill="x", padx=8, pady=(0, 6))
        tk.Label(status, textvariable=self.var_db_status, anchor="w").pack(side="left", fill="x", expand=True)

        self.tree_db_runs, db_runs_frame = create_scrollable_treeview(
            parent,
            columns=tuple(self._db_visible_columns),
            show="headings",
            height=14,
            horizontal=True,
        )
        self._apply_result_columns(self._db_visible_columns, self._db_runs)
        db_runs_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.tree_db_runs.bind("<<TreeviewSelect>>", self.on_database_run_selected)

        self.txt_db_detail = tk.Text(parent, height=10, wrap="word")
        self.txt_db_detail.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self._set_text(self.txt_db_detail, "")

    def _database_store_spec(self) -> dict[str, str]:
        return {"driver": "sqlite", "path": str(self._sqlite_path())}

    def _selected_db_assay_key(self) -> str:
        label = self.var_db_assay.get().strip()
        return self._db_assay_choice_to_key.get(label, label)

    def _build_db_display_context(self, assay_key: str) -> dict[str, object]:
        column_mapping: dict[str, str] = {}
        if assay_key:
            try:
                ruleset = resolve_ruleset(
                    assay_key,
                    str(self.project_root / "rules"),
                    str(self.project_root / "rules" / "index.json"),
                )
                excel_rules = ruleset.data.get("excel_rules")
                if isinstance(excel_rules, dict):
                    raw_map = excel_rules.get("column_mapping")
                    if isinstance(raw_map, dict):
                        column_mapping = {str(k): str(v) for k, v in raw_map.items()}
            except Exception:
                column_mapping = {}
        return build_result_display_context(self._db_rulesets, [assay_key], column_mapping)

    def refresh_database(self) -> None:
        status = get_result_store_status(self._database_store_spec())
        self.var_db_status.set(str(status.get("message") or "Unbekannter Status."))
        if not status.get("available"):
            self.cmb_db_assay.configure(values=[])
            self.cmb_db_charge.configure(values=[])
            self.var_db_assay.set("")
            self.var_db_charge.set("")
            self._db_assay_choice_to_key = {}
            self._db_rulesets = []
            self._db_display_context = {"assay_labels": {}, "payload_labels": {}}
            self._db_runs = []
            self._db_runs_by_id = {}
            self._apply_result_columns(self._db_visible_columns, self._db_runs)
            self._set_text(self.txt_db_detail, "")
            self._log(f"Datenbank: {status.get('message', 'nicht verfügbar')}")
            return

        try:
            self._db_rulesets = list(list_rulesets(str(self.project_root)))
        except Exception:
            self._db_rulesets = []

        assay_keys = [row["assay_key"] for row in list_result_assays(self._database_store_spec())]
        choices = build_assay_filter_choices(self._db_rulesets, assay_keys)
        self._db_assay_choice_to_key = {row["label"]: row["assay_key"] for row in choices}
        labels = [row["label"] for row in choices]
        self.cmb_db_assay.configure(values=labels)
        if labels and self.var_db_assay.get() not in labels:
            self.var_db_assay.set(labels[0])
        elif not labels:
            self.var_db_assay.set("")
        self.on_db_assay_selected()
        warnings = status.get("schema_warnings") or []
        if warnings:
            self.var_db_status.set(f"{status.get('message', '')} | {'; '.join(warnings)}")
        self._log(f"Datenbank geladen: {len(assay_keys)} Assay(s).")

    def on_db_assay_selected(self, _event: object = None) -> None:
        assay_key = self._selected_db_assay_key()
        if not assay_key:
            self.cmb_db_charge.configure(values=[""])
            self.var_db_charge.set("")
            return
        charges = [""] + [row["lot_id"] for row in list_result_charges(self._database_store_spec(), assay_key)]
        self.cmb_db_charge.configure(values=charges)
        if self.var_db_charge.get() not in charges:
            self.var_db_charge.set("")

    def show_database_runs(self) -> None:
        assay_key = self._selected_db_assay_key()
        if not assay_key:
            messagebox.showinfo("Datenbank", "Bitte Assay wählen.")
            return
        charge = self.var_db_charge.get().strip() or None
        result = list_result_runs(
            self._database_store_spec(),
            assay_key=assay_key,
            charge=charge,
        )
        self._db_runs = list(result.get("runs") or [])
        self._db_runs_by_id = {str(run.get("id")): run for run in self._db_runs if run.get("id") is not None}
        self._db_display_context = self._build_db_display_context(assay_key)
        self._db_column_catalog = build_result_column_catalog(self._db_runs, self._db_display_context)
        visible = normalize_visible_result_columns(self._db_visible_columns, self._db_column_catalog)
        self._apply_result_columns(visible, self._db_runs)
        status_parts = [f"{result.get('total_returned', 0)} Eintrag/Einträge"]
        if result.get("truncated"):
            status_parts.append("Anzeige auf 500 Einträge begrenzt")
        self.var_db_status.set(" | ".join(status_parts))
        self._set_text(self.txt_db_detail, "")
        self._log(f"Datenbank-Einträge geladen: {result.get('total_returned', 0)}.")

    def configure_database_columns(self) -> None:
        if not self._db_column_catalog:
            self._db_column_catalog = build_result_column_catalog(self._db_runs, self._db_display_context)
        if not self._db_column_catalog:
            messagebox.showinfo("Datenbank", "Bitte zuerst Einträge laden.")
            return

        dialog = tk.Toplevel(self)
        dialog.title("Spalten ein-/ausblenden")
        dialog.transient(self)
        dialog.grab_set()

        vars_by_id: dict[str, tk.BooleanVar] = {}
        frame = tk.Frame(dialog)
        frame.pack(fill="both", expand=True, padx=10, pady=10)
        for col_id in sorted(self._db_column_catalog.keys(), key=lambda key: self._db_column_catalog[key].lower()):
            var = tk.BooleanVar(value=col_id in self._db_visible_columns)
            vars_by_id[col_id] = var
            tk.Checkbutton(frame, text=self._db_column_catalog[col_id], variable=var).pack(anchor="w")

        buttons = tk.Frame(dialog)
        buttons.pack(fill="x", padx=10, pady=(0, 10))

        def apply_columns() -> None:
            selected = [col_id for col_id, var in vars_by_id.items() if var.get()]
            self._db_visible_columns = normalize_visible_result_columns(selected, self._db_column_catalog)
            self._apply_result_columns(self._db_visible_columns, self._db_runs)
            dialog.destroy()

        tk.Button(buttons, text="Übernehmen", command=apply_columns).pack(side="right")
        tk.Button(buttons, text="Abbrechen", command=dialog.destroy).pack(side="right", padx=(0, 6))

    def _apply_result_columns(self, visible_columns: list[str], runs: list[dict[str, object]]) -> None:
        self._db_column_catalog = build_result_column_catalog(runs, self._db_display_context)
        self._db_visible_columns = list(visible_columns)
        for item in self.tree_db_runs.get_children():
            self.tree_db_runs.delete(item)

        headings = {
            col_id: self._db_column_catalog.get(col_id, col_id)
            for col_id in visible_columns
        }
        self.tree_db_runs["columns"] = tuple(visible_columns)
        for col_id in visible_columns:
            title = headings.get(col_id, col_id)
            self.tree_db_runs.heading(col_id, text=title)
            width = 360 if col_id == "meta:pdf_path" else 140
            self.tree_db_runs.column(col_id, width=width, anchor="w")

        for run in runs:
            run_id = run.get("id")
            if run_id is None:
                continue
            iid = str(run_id)
            self.tree_db_runs.insert(
                "",
                tk.END,
                iid=iid,
                values=format_result_run_row(run, visible_columns, self._db_display_context),
            )

        self._tree_db_sorter = TreeviewSorter(self.tree_db_runs)
        self._tree_db_sorter.attach(headings)

    def on_database_run_selected(self, _event: object = None) -> None:
        sel = self.tree_db_runs.selection()
        if not sel:
            return
        run = self._db_runs_by_id.get(str(sel[0]))
        if not run:
            return
        self._set_text(self.txt_db_detail, format_result_run_detail(run))

    def _build_admin_tab(self, parent: tk.Frame) -> None:
        controls = tk.Frame(parent)
        controls.pack(fill="x", padx=8, pady=8)
        tk.Button(controls, text="Queue aktualisieren", command=self.refresh_queue).pack(side="left")
        self.tree_queue, queue_frame = create_scrollable_treeview(
            parent,
            columns=("job_id", "file", "status", "source", "attempts", "last_error", "updated_at", "path"),
            show="headings",
            height=12,
        )
        queue_headings = {
            "job_id": "Job-ID",
            "file": "Datei",
            "status": "Status",
            "source": "Quelle",
            "attempts": "Versuche",
            "last_error": "Letzter Fehler",
            "updated_at": "Aktualisiert",
            "path": "Pfad",
        }
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
            self.tree_queue.column(col, width=width, anchor="w")
        self._tree_queue_sorter = TreeviewSorter(
            self.tree_queue,
            numeric_columns=("attempts",),
            date_columns=("updated_at",),
        )
        self._tree_queue_sorter.attach(queue_headings)
        queue_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))

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
            }
        )
        self._set_text(self.txt_options, "\n".join(lines))

    def _log(self, message: str) -> None:
        self.txt_logs.configure(state="normal")
        self.txt_logs.insert(tk.END, message + "\n")
        self.txt_logs.see(tk.END)
        self.txt_logs.configure(state="disabled")
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
                        self._log(f"Auto-Suche Fehler beim Vormerken von {Path(path).name}: {e}")
                if queued_count:
                    self.refresh_queue()
                    self._log(f"Auto-Suche: {queued_count} PDF(s) für Extraktion vorgemerkt.")
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
        queued_count, skipped_count, error_count = self._enqueue_paths(paths, source="test-app-watch")
        self.refresh_queue()
        recursive_label = "ja" if recursive else "nein"
        self._log(
            f"Ergebnisse gesucht: {len(paths)} PDF(s), vorgemerkt={queued_count}, "
            f"übersprungen={skipped_count}, Fehler={error_count}, rekursiv={recursive_label}"
        )

    def pick_manual_files(self) -> None:
        files = filedialog.askopenfilenames(title="PDFs waehlen", filetypes=[("PDF Dateien", "*.pdf")])
        queued_count, skipped_count, error_count = self._enqueue_paths(files, source="test-app-manual")
        self.refresh_queue()
        self._log(
            f"Dateien hinzugefügt: {len(files)} PDF(s), vorgemerkt={queued_count}, "
            f"übersprungen={skipped_count}, Fehler={error_count}"
        )

    def _enqueue_paths(self, paths: list[str] | tuple[str, ...], *, source: str) -> tuple[int, int, int]:
        queued_count = 0
        skipped_count = 0
        error_count = 0
        for path in paths:
            try:
                job = enqueue_pdf_job(str(self.project_root), str(path), source=source)
                status = str(job.get("status", "") if isinstance(job, dict) else getattr(job, "status", ""))
                if status == "PENDING":
                    queued_count += 1
                else:
                    skipped_count += 1
            except Exception as e:
                error_count += 1
                self._log(f"Vormerken fehlgeschlagen bei {Path(path).name}: {e}")
        return queued_count, skipped_count, error_count

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
            display = format_extractor_file_row(row)
            self.tree_files.insert(
                "",
                tk.END,
                iid=key,
                values=(
                    display["file"],
                    display["source"],
                    display["queue_status"],
                    display["device_id"],
                    display["last_error"],
                    display["action"],
                    display["path"],
                    display["job_id"],
                ),
            )
        self._tree_files_sorter.resort()

    def start_extraction(self) -> None:
        pending_count = sum(1 for job in list_jobs(str(self.project_root)) if job.status == "PENDING")
        if pending_count == 0:
            messagebox.showinfo("Extraktion", "Keine wartenden Ergebnisse in der Arbeitsliste.")
            return
        if not self._start_background_action("Extraktion laeuft..."):
            return
        self._extraction_running = True
        self._stop_extraction_event.clear()
        self.btn_stop_extraction.configure(state=tk.NORMAL)
        snapshot = self._build_worker_config_snapshot()
        threading.Thread(target=self._process_queue_thread, args=(snapshot, pending_count), daemon=True).start()

    def start_selected_files(self) -> None:
        self.start_extraction()

    def retry_selected_failed_jobs(self) -> None:
        selected = list(self.tree_files.selection())
        if not selected:
            messagebox.showinfo("Arbeitsliste", "Bitte fehlgeschlagene Ergebnisse auswählen.")
            return
        restarted = 0
        skipped = 0
        for key in selected:
            row = self._watch_rows.get(str(key))
            if not row:
                skipped += 1
                continue
            if row.get("queue_status") != "FAILED" or not row.get("job_id"):
                skipped += 1
                continue
            try:
                retry_failed_job(str(self.project_root), row["job_id"])
                restarted += 1
            except Exception as e:
                skipped += 1
                self._log(f"Erneut starten fehlgeschlagen: {row.get('file', row.get('job_id', '?'))} | {e}")
        self.refresh_queue()
        self._log(f"Erneut gestartet: {restarted} Ergebnis(se). Übersprungen: {skipped}.")

    def stop_extraction(self) -> None:
        if not self._extraction_running:
            return
        self._stop_extraction_event.set()
        self.var_status.set("Extraktion wird nach aktuellem Ergebnis gestoppt...")
        self.btn_stop_extraction.configure(state=tk.DISABLED)

    def _build_worker_config_snapshot(self) -> QueueWorkerConfig:
        return QueueWorkerConfig(
            output_mode=self.var_output_mode.get(),
            sqlite_path=self.var_sqlite_path.get().strip() or None,
            device_id=self._selected_device_id(),
            queue_processing_ttl_s=self._queue_processing_ttl_s,
            queue_claim_lock_ttl_s=self._queue_claim_lock_ttl_s,
            queue_max_attempts=self._queue_max_attempts,
            pipeline_lock_ttl_s=self._pipeline_lock_ttl_s,
            sqlite_busy_timeout_ms=self._sqlite_busy_timeout_ms,
            sqlite_retry_count=self._sqlite_retry_count,
            sqlite_retry_sleep_s=self._sqlite_retry_sleep_s,
        )

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

    def _process_queue_thread(self, snapshot: QueueWorkerConfig, pending_count: int) -> None:
        processed_count = 0
        stopped = False
        final_error = ""
        try:
            for _ in range(pending_count):
                if self._stop_extraction_event.is_set():
                    stopped = True
                    break
                result = process_next_pending(self.project_root, snapshot)
                if not result.processed:
                    break
                processed_count += 1
                self.after(
                    0,
                    lambda r=result, count=processed_count: self._handle_extraction_progress(
                        r,
                        count,
                        pending_count,
                    ),
                )
                if result.queue_status == "PENDING":
                    break
                if self._stop_extraction_event.is_set():
                    stopped = True
                    break
        except Exception as e:
            final_error = f"Extraktion abgebrochen: {e}"
        self.after(
            0,
            lambda: self._finish_queue_processing(
                processed_count,
                pending_count,
                stopped or self._stop_extraction_event.is_set(),
                final_error,
            ),
        )

    def _handle_extraction_progress(self, result, processed_count: int, pending_count: int) -> None:
        name = Path(result.pdf_path).name if result.pdf_path else result.job_id
        status = result.queue_status or result.submit_status or "unbekannt"
        self._log(f"Extraktion: {processed_count}/{pending_count} {name} -> {status}")
        self.refresh_queue()

    def _finish_queue_processing(
        self,
        processed_count: int,
        pending_count: int,
        stopped: bool,
        final_error: str = "",
    ) -> None:
        try:
            if final_error:
                self._log(final_error)
            elif processed_count == 0:
                self._log("Keine wartenden Ergebnisse in der Arbeitsliste.")
            elif stopped:
                self._log(f"Extraktion nach aktuellem Ergebnis gestoppt: {processed_count}/{pending_count} Job(s).")
            else:
                self._log(f"Extraktion abgeschlossen: {processed_count} Job(s) verarbeitet.")
            self.refresh_queue()
        finally:
            self._busy = False
            self._extraction_running = False
            self._stop_extraction_event.clear()
            self.progress.stop()
            self.progress.configure(mode="determinate", value=0)
            self.var_technical_status.set("idle")
            self.btn_stop_extraction.configure(state=tk.DISABLED)
            self._set_action_buttons_state(tk.NORMAL)

    def refresh_queue(self) -> None:
        jobs = list_jobs(str(self.project_root))
        rows = [format_queue_job_row(job) for job in jobs]
        if self._admin_enabled:
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
            self._tree_queue_sorter.resort()
        merged_rows = merge_file_rows_with_queue(
            [],
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
        if getattr(sys, "frozen", False):
            env = os.environ.copy()
            env["ARE_HOME"] = str(self.project_root)
            env["ARE_START_RULE_EDITOR"] = "1"
            subprocess.Popen([sys.executable], cwd=str(self.project_root), env=env)
            self._log("Rule Editor gestartet.")
            return

        script = self.project_root / "rule_editor_main.py"
        if not script.exists():
            messagebox.showerror("Rule Editor", f"Nicht gefunden:\n{script}")
            return
        subprocess.Popen([sys.executable, str(script)], cwd=str(self.project_root))
        self._log("Rule Editor gestartet.")

    def refresh_rework_items(self) -> None:
        self._set_text(self.txt_rework_detail, "")
        self._clear_rework_candidates("Noch keine Kandidaten geprüft.")
        jobs = list_jobs(str(self.project_root))
        self._rework_items_all = build_rework_items(str(self.project_root), jobs)
        filtered = filter_rework_items(self._rework_items_all, self.var_rework_filter.get())
        self._render_rework_table(filtered)
        self._log(
            f"Nacharbeit aktualisiert: {len(self._rework_items_all)} geladen, "
            f"{len(filtered)} angezeigt."
        )

    def _on_rework_filter_changed(self, _event: object = None) -> None:
        filtered = filter_rework_items(self._rework_items_all, self.var_rework_filter.get())
        self._set_text(self.txt_rework_detail, "")
        self._clear_rework_candidates("Noch keine Kandidaten geprüft.")
        self._render_rework_table(filtered)

    def _render_rework_table(self, items: list[dict[str, object]]) -> None:
        for item in self.tree_rework.get_children():
            self.tree_rework.delete(item)
        self._rework_items = {str(item["item_id"]): item for item in items}
        for item in items:
            summary = format_rework_item_summary(item)
            item_id = str(item["item_id"])
            self.tree_rework.insert(
                "",
                tk.END,
                iid=item_id,
                values=(
                    summary["file"],
                    summary["error_label"],
                    summary["queue_status"],
                    summary["job_id"],
                    summary["context_label"],
                ),
            )
        self._tree_rework_sorter.resort()

    def on_rework_selected(self, _event: object = None) -> None:
        selection = self.tree_rework.selection()
        if not selection:
            return
        self._clear_rework_candidates("Noch keine Kandidaten geprüft.")
        item = self._rework_items.get(str(selection[0]))
        if item:
            self._set_text(self.txt_rework_detail, format_rework_item_detail(item))

    def _clear_rework_candidates(self, message: str) -> None:
        for row_id in self.tree_rework_candidates.get_children():
            self.tree_rework_candidates.delete(row_id)
        self._rework_candidates_by_id = {}
        self.lbl_rework_candidates.configure(text=message)

    def _render_rework_candidates(self, candidates: list[dict[str, str]], message: str) -> None:
        self._clear_rework_candidates(message)
        for candidate in candidates:
            candidate_id = str(candidate.get("candidate_id", "") or "").strip()
            if not candidate_id:
                continue
            self._rework_candidates_by_id[candidate_id] = dict(candidate)
            status = REWORK_CANDIDATE_STATUS_LABELS.get(
                str(candidate.get("known_status", "")),
                str(candidate.get("known_status", "")),
            )
            self.tree_rework_candidates.insert(
                "",
                tk.END,
                iid=candidate_id,
                values=(
                    candidate.get("assay_key") or "-",
                    candidate.get("assay_name_hint") or "-",
                    candidate.get("test_file") or "-",
                    candidate.get("line_no") or "-",
                    status,
                    candidate.get("confidence") or "-",
                    candidate.get("reason") or "-",
                ),
            )

    def preview_assay_candidates(self) -> None:
        selection = self.tree_rework.selection()
        if not selection:
            messagebox.showinfo("Nacharbeit", "Bitte zuerst einen Eintrag auswaehlen.")
            return
        item = self._rework_items.get(str(selection[0]))
        if not item:
            return
        if str(item.get("error_label", "")) != "Assay nicht erkannt":
            messagebox.showinfo(
                "Nacharbeit",
                "Assay-Kandidatenpruefung ist nur fuer 'Assay nicht erkannt' verfuegbar.",
            )
            return

        normalized_dump = str(item.get("normalized_dump", "") or "").strip()
        if not normalized_dump or not Path(normalized_dump).exists():
            self._clear_rework_candidates("Kein normalisierter Kontext vorhanden.")
            return

        try:
            text = Path(normalized_dump).read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            self._clear_rework_candidates(f"Normalisierter Kontext konnte nicht gelesen werden: {exc}")
            return

        candidates = find_assay_candidates(text)
        index_path = self.project_root / "rules" / "index.json"
        known_keys = load_known_assay_keys(str(index_path))
        if known_keys is None:
            self._log(
                "Assay-Kandidaten: rules/index.json konnte nicht gelesen werden; Status ungeprueft."
            )
        annotated = annotate_assay_candidates(candidates, known_keys)
        if not annotated:
            self._clear_rework_candidates("Keine Kandidaten erkannt.")
            return

        self._render_rework_candidates(
            annotated,
            f"{len(annotated)} Kandidat(en) aus normalisiertem Kontext.",
        )
        self._log(f"Assay-Kandidaten geprueft: {len(annotated)} Kandidat(en).")

    def create_draft_from_rework_candidate(self) -> None:
        selection = self.tree_rework_candidates.selection()
        if not selection:
            messagebox.showinfo("Nacharbeit", "Bitte zuerst einen Assay-Kandidaten auswaehlen.")
            return
        candidate = self._rework_candidates_by_id.get(str(selection[0]))
        if not candidate:
            return

        known_status = str(candidate.get("known_status", ""))
        if known_status == "known":
            messagebox.showinfo(
                "Nacharbeit",
                "Regelwerk existiert bereits. Bitte Retry oder vorhandene Rule pruefen.",
            )
            return

        assay_key = str(candidate.get("assay_key", "") or "").strip()
        assay_name = str(candidate.get("assay_name_hint", "") or "").strip()
        if not assay_key or not assay_name:
            messagebox.showinfo(
                "Nacharbeit",
                "Draft erfordert Assay-Key und Namenshinweis aus einer Testzeile.",
            )
            return

        if known_status == "unchecked":
            proceed = messagebox.askokcancel(
                "Nacharbeit",
                "Index konnte nicht geprueft werden. Draft wird nur angelegt, nicht aktiviert.",
            )
            if not proceed:
                return

        try:
            result = create_draft_from_template_if_missing(
                str(self.project_root),
                assay_key,
                assay_name,
            )
        except Exception as exc:
            messagebox.showerror("Nacharbeit", f"Draft konnte nicht erstellt werden: {exc}")
            return

        draft_path = str(result["draft_path"])
        status = str(result["status"])
        if status == "created":
            self._log(f"Draft erstellt: {draft_path}")
        else:
            self._log(f"Draft existiert bereits: {draft_path}")

        rework_selection = self.tree_rework.selection()
        detail = ""
        if rework_selection:
            item = self._rework_items.get(str(rework_selection[0]))
            if item:
                detail = format_rework_item_detail(item) + "\n\n"
        detail += (
            f"Draft-Pfad: {draft_path}\n"
            f"Draft-Status: {status}\n"
            f"Assay-Key: {assay_key}\n"
            f"Assay-Name: {assay_name}"
        )
        self._set_text(self.txt_rework_detail, detail)

        if messagebox.askyesno("Nacharbeit", "Rule Editor oeffnen?"):
            self.open_rule_editor()

    def show_rework_context(self) -> None:
        selection = self.tree_rework.selection()
        if not selection:
            messagebox.showinfo("Nacharbeit", "Bitte zuerst einen Eintrag auswaehlen.")
            return
        item = self._rework_items.get(str(selection[0]))
        if not item:
            return
        detail = format_rework_item_detail(item)
        label, path = resolve_rework_context_source(item)
        content: str | None = None
        if path and Path(path).exists():
            try:
                content = Path(path).read_text(encoding="utf-8", errors="replace")
            except OSError:
                content = None
        context_text = format_rework_context_text(item, content, label, path)
        self._set_text(self.txt_rework_detail, detail + "\n\n" + context_text)

    def open_rule_editor_from_rework(self) -> None:
        selection = self.tree_rework.selection()
        if selection:
            item = self._rework_items.get(str(selection[0]))
            if item:
                pdf_path = str(item.get("pdf_path", "") or item.get("file", "?"))
                dump_path = preferred_rework_dump_path(item) or "-"
                self._log(f"Rule Editor fuer Nacharbeit: PDF={pdf_path}, Dump={dump_path}")
        self.open_rule_editor()

    def retry_selected_rework_items(self) -> None:
        selection = list(self.tree_rework.selection())
        if not selection:
            messagebox.showinfo("Nacharbeit", "Bitte fehlgeschlagene Eintraege auswaehlen.")
            return
        restarted = 0
        skipped = 0
        for item_id in selection:
            item = self._rework_items.get(str(item_id))
            if not item:
                skipped += 1
                continue
            try:
                retry_failed_job(str(self.project_root), str(item["job_id"]))
                restarted += 1
            except Exception as e:
                skipped += 1
                self._log(f"Erneut starten fehlgeschlagen: {item.get('file', item.get('job_id', '?'))} | {e}")
        self.refresh_queue()
        self.refresh_rework_items()
        self._log(f"Nacharbeit erneut gestartet: {restarted}. Uebersprungen: {skipped}.")

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
    resolved_root = Path(project_root).resolve() if project_root is not None else resolve_app_root()
    if legacy_ui_enabled():
        app = LegacyTestApp(project_root=resolved_root)
    else:
        app = AnalyzerDesktopApp(project_root=resolved_root)
    app.mainloop()


def run_startup_smoke_check(project_root: str | Path | None = None) -> None:
    root = Path(project_root) if project_root is not None else resolve_app_root()
    rules_dir = root / "rules"
    index_path = rules_dir / "index.json"
    report = validate_rules_integrity(str(rules_dir), str(index_path))
    if any(bool(v) for v in report.values()):
        raise RuntimeError(f"rules_integrity_failed: {json.dumps(report, ensure_ascii=False)}")
    _ = load_runtime_config(root)


def run_entry(module_file: str | Path) -> None:
    app_root = resolve_app_root(Path(module_file))
    if os.getenv("ARE_SMOKE_EXIT", "").strip() == "1":
        run_startup_smoke_check(app_root)
    elif os.getenv("ARE_START_RULE_EDITOR", "").strip() == "1":
        from rule_editor_main import RuleEditorWindow

        RuleEditorWindow(project_root=app_root).mainloop()
    else:
        main(project_root=app_root)

LegacyTestApp = TestApp


class AnalyzerDesktopApp(tk.Tk):
    """V2.1 desktop shell (Phase 3B). Default product UI via main(); LegacyTestApp via ARE_LEGACY_UI."""

    __test__ = False

    VIEW_KEYS = (
        "dashboard",
        "results",
        "validation",
        "rules",
        "settings",
        "diagnostics",
    )
    TASK_REFRESH = "refresh"
    TASK_PROCESSING = "processing_queue"
    TASK_BOOTSTRAP = "bootstrap"
    TASK_SETTINGS_SAVE = "settings-save"

    def __init__(
        self,
        project_root: str | Path,
        *,
        services: object | None = None,
    ) -> None:
        from interfaces.tk.desktop_theme import (
            APP_TITLE,
            DEFAULT_HEIGHT,
            DEFAULT_WIDTH,
            MIN_HEIGHT,
            MIN_WIDTH,
            configure_desktop_theme,
        )
        from interfaces.tk.task_runner import TkTaskRunner
        from interfaces.tk.view_models import DASHBOARD_REPORT_JOIN_LIMIT, NAV_LABELS, PRIMARY_NAV_KEYS, SECONDARY_NAV_KEYS
        from interfaces.tk.views import (
            DashboardView,
            DiagnosticsView,
            ResultsView,
            RulesView,
            SettingsView,
            ValidationView,
        )
        from interfaces.tk.widgets.common import StatusBadge
        from interfaces.tk.widgets.dialogs import (
            show_confirm_dialog,
            show_details_dialog,
            show_error_dialog,
            show_info_dialog,
        )
        from src.application.api import (
            ApplicationWatchError,
            DesktopAppServices,
            PathOpenError,
            ProcessingOutcome,
            ReportNotFoundError,
            SettingsSaveError,
            SettingsValidationError,
            WatchCycleSummary,
            create_desktop_services,
        )

        super().__init__()
        self.project_root = Path(project_root).resolve()
        self._show_confirm_dialog = show_confirm_dialog
        self._show_details_dialog = show_details_dialog
        self._show_error_dialog = show_error_dialog
        self._show_info_dialog = show_info_dialog
        self._ApplicationWatchError = ApplicationWatchError
        self._PathOpenError = PathOpenError
        self._ReportNotFoundError = ReportNotFoundError
        self._SettingsSaveError = SettingsSaveError
        self._SettingsValidationError = SettingsValidationError
        self._WatchCycleSummary = WatchCycleSummary
        self._ProcessingOutcome = ProcessingOutcome
        self._dashboard_report_join_limit = DASHBOARD_REPORT_JOIN_LIMIT

        self.title(APP_TITLE)
        self.minsize(MIN_WIDTH, MIN_HEIGHT)
        self.geometry(f"{DEFAULT_WIDTH}x{DEFAULT_HEIGHT}")
        configure_desktop_theme(self)

        self._services: DesktopAppServices | None = None
        self._settings = None
        self._device_label_map: dict[str, str] = {}
        self._bootstrapped = False
        self._create_desktop_services = create_desktop_services
        self._task_runner = TkTaskRunner(self)
        self._watch_after_id: str | None = None
        self._watch_schedule_generation = 0
        self._last_watch_summary: WatchCycleSummary | None = None
        self._last_watch_error: str = ""
        self._refresh_generation = 0
        self._settings_save_latest_id = 0
        self._settings_save_latest = None
        self._settings_save_latest_edit_generation = 0
        self._settings_save_inflight_id: int | None = None
        self._current_view = "dashboard"
        self._nav_buttons: dict[str, ttk.Button] = {}
        self._validation_badge: StatusBadge | None = None
        self._views: dict[str, ttk.Frame] = {}

        self._build_header()
        shell = ttk.Frame(self, style="Content.TFrame")
        shell.pack(fill="both", expand=True)
        shell.columnconfigure(1, weight=1)
        shell.rowconfigure(0, weight=1)

        nav = ttk.Frame(shell, style="Nav.TFrame", padding=8, width=200)
        nav.grid(row=0, column=0, sticky="ns")
        nav.grid_propagate(False)
        for key in PRIMARY_NAV_KEYS:
            label = NAV_LABELS[key]
            if key == "validation":
                row = ttk.Frame(nav, style="Nav.TFrame")
                row.pack(fill="x", pady=(0, 4))
                btn = ttk.Button(row, text=label, style="Nav.TButton", command=lambda k=key: self.show_view(k))
                btn.pack(side="left", fill="x", expand=True)
                self._validation_badge = StatusBadge(row, "0", kind="good")
                self._validation_badge.pack(side="right", padx=(6, 2))
            else:
                btn = ttk.Button(nav, text=label, style="Nav.TButton", command=lambda k=key: self.show_view(k))
                btn.pack(fill="x", pady=(0, 4))
            self._nav_buttons[key] = btn
        ttk.Separator(nav).pack(fill="x", pady=8)
        for key in SECONDARY_NAV_KEYS:
            label = NAV_LABELS[key]
            btn = ttk.Button(nav, text=label, style="Nav.TButton", command=lambda k=key: self.show_view(k))
            btn.pack(fill="x", pady=(0, 4))
            self._nav_buttons[key] = btn

        content = ttk.Frame(shell, style="Content.TFrame", padding=(12, 8))
        content.grid(row=0, column=1, sticky="nsew")
        content.rowconfigure(0, weight=1)
        content.columnconfigure(0, weight=1)

        self._views["dashboard"] = DashboardView(
            content,
            on_pick_and_process_pdfs=self._pick_and_process_pdfs,
            on_open_settings=lambda: self.show_view("settings"),
            on_refresh=self.refresh_current_view,
            on_open_report=self._open_report_from_dashboard,
            on_open_selected_report=self._open_selected_dashboard_report,
        )
        self._views["results"] = ResultsView(
            content,
            on_refresh=self.refresh_current_view,
            on_open_selected=self._open_selected_report,
            on_open_pdf=self._open_report_pdf,
            on_open_output_folder=self._open_output_folder,
            on_back=self._show_results_list,
            on_occurrence_selected=lambda _occ_id: None,
            on_save_validation=self._save_selected_validation,
            on_correct_validation=self._correct_selected_validation,
        )
        self._views["validation"] = ValidationView(
            content,
            on_refresh=self.refresh_current_view,
            on_save=self._save_pending_validation,
            on_open_pdf=self._open_validation_pdf,
        )
        self._views["rules"] = RulesView(
            content,
            on_open_rule_editor=self.open_rule_editor,
            on_refresh=self.refresh_current_view,
            on_validate=self._validate_rules,
        )
        self._views["settings"] = SettingsView(
            content,
            on_save=self._save_settings,
            on_pick_watch_input=self._pick_watch_input_folder,
            on_pick_watch_backup=self._pick_watch_backup_folder,
            on_pick_sqlite=self._pick_sqlite_path,
            on_reload_devices=self._reload_devices,
            on_open_output_folder=self._open_output_folder,
        )
        self._views["diagnostics"] = DiagnosticsView(
            content,
            on_refresh=self.refresh_current_view,
            on_show_diagnosis=self._show_diagnosis_details,
            on_retry_job=self._retry_selected_job,
            on_create_draft=self._create_draft_from_candidate,
            on_show_duplicate=self._show_duplicate_details,
            on_discard_duplicate=self._discard_selected_duplicate,
        )
        self._views["dashboard"].set_actions_enabled(False)
        self._views["dashboard"].set_activity_message("Lade Anwendung …")

        self.protocol("WM_DELETE_WINDOW", self.close_app)
        self.show_view("dashboard", refresh=False)
        if services is not None:
            self._services = services
            self._finish_bootstrap()
        else:
            self._start_bootstrap()

    @property
    def services(self) -> object:
        return self._services

    @property
    def task_runner(self) -> object:
        return self._task_runner

    def _start_bootstrap(self) -> None:
        def work() -> DesktopAppServices:
            return self._create_desktop_services(self.project_root)

        def on_success(services: DesktopAppServices) -> None:
            self._services = services
            self._finish_bootstrap()

        def on_error(exc: BaseException) -> None:
            message, details = self._friendly_error_parts(exc)
            self._views["dashboard"].set_activity_message(f"Start fehlgeschlagen: {message}")
            self._show_error_dialog(self, "Start", message, details=details)

        self._task_runner.submit(self.TASK_BOOTSTRAP, work, on_success=on_success, on_error=on_error)

    def _finish_bootstrap(self) -> None:
        self._bootstrapped = True
        self._views["dashboard"].set_actions_enabled(True)
        self._views["dashboard"].set_activity_message("Bereit.")
        self._schedule_watch()
        self.refresh_current_view()

    def _require_services(self) -> bool:
        return self._bootstrapped and self._services is not None

    def show_view(self, key: str, *, refresh: bool = True) -> None:
        if key not in self.VIEW_KEYS:
            return
        self._current_view = key
        for view_key, frame in self._views.items():
            if view_key == key:
                frame.grid(row=0, column=0, sticky="nsew")
            else:
                frame.grid_remove()
        for view_key, button in self._nav_buttons.items():
            style = "NavActive.TButton" if view_key == key else "Nav.TButton"
            button.configure(style=style)
        if refresh:
            self.refresh_current_view()

    def _friendly_error_parts(self, error: BaseException | str) -> tuple[str, str]:
        from interfaces.tk.view_models import user_error_dialog_parts

        return user_error_dialog_parts(error)

    def _submit_refresh_task(self, generation: int, view_key: str) -> bool:
        def work() -> dict[str, object]:
            return self._load_view_payload(view_key)

        def on_success(payload: dict[str, object]) -> None:
            self._complete_refresh(generation, view_key, payload=payload)

        def on_error(exc: BaseException) -> None:
            self._complete_refresh(generation, view_key, error=exc)

        return self._task_runner.submit(
            self.TASK_REFRESH,
            work,
            on_success=on_success,
            on_error=on_error,
        )

    def _maybe_submit_latest_refresh(self) -> None:
        if getattr(self._task_runner, "shutdown", False):
            return
        if self._task_runner.is_active(self.TASK_REFRESH):
            return
        if not self._require_services():
            return
        self._submit_refresh_task(self._refresh_generation, self._current_view)

    def _complete_refresh(
        self,
        generation: int,
        view_key: str,
        *,
        payload: dict[str, object] | None = None,
        error: BaseException | None = None,
    ) -> None:
        if view_key != self._current_view:
            self.refresh_current_view()
            return
        if generation != self._refresh_generation:
            self._maybe_submit_latest_refresh()
            return
        if error is not None:
            message, details = self._friendly_error_parts(error)
            self._show_error_dialog(self, "Aktualisierung", message, details=details)
            return
        if payload is not None:
            self._apply_view_payload(view_key, payload)

    def refresh_current_view(self) -> None:
        if not self._require_services():
            return
        self._refresh_generation += 1
        generation = self._refresh_generation
        view_key = self._current_view
        if not self._submit_refresh_task(generation, view_key):
            return

    def _load_view_payload(self, view_key: str) -> dict[str, object]:
        from interfaces.tk.view_models import build_dashboard_recent_rows

        assert self._services is not None
        settings = self._services.settings.load()
        payload: dict[str, object] = {"view": view_key, "settings": settings}
        validation_cases = self._services.results.list_open_validation_cases()
        payload["validation_open_count"] = len(validation_cases)
        if view_key == "dashboard":
            ingestions = self._services.extraction.list_ingestion_instances()
            reports = self._services.results.list_recent_reports(limit=self._dashboard_report_join_limit)
            payload["recent"] = build_dashboard_recent_rows(ingestions, reports)
            payload["watch_summary"] = self._last_watch_summary
            payload["watch_error"] = self._last_watch_error
        elif view_key == "results":
            payload["reports"] = self._services.results.list_recent_reports()
        elif view_key == "validation":
            payload["validation_cases"] = validation_cases
        elif view_key == "rules":
            payload["inventory"] = self._services.rules.list_inventory()
        elif view_key == "settings":
            payload["devices"] = self._services.settings.get_device_inventory()
            payload["timing"] = self._services.settings.get_watch_timing()
        elif view_key == "diagnostics":
            payload["diagnoses"] = self._services.extraction.list_job_diagnoses()
            payload["duplicates"] = self._services.results.list_duplicate_candidates(status="pending")
        return payload

    def _apply_view_payload(self, view_key: str, payload: dict[str, object]) -> None:
        settings = payload["settings"]
        self._settings = settings
        self._set_validation_badge(int(payload.get("validation_open_count") or 0))
        if view_key == "dashboard":
            dashboard = self._views["dashboard"]
            dashboard.render_watch_settings(settings)
            dashboard.render_recent_rows(payload.get("recent", ()))
            summary = payload.get("watch_summary")
            error = str(payload.get("watch_error") or "")
            if isinstance(summary, self._WatchCycleSummary) or summary is None:
                dashboard.render_watch_session_summary(summary, error=error)
        elif view_key == "results":
            self._views["results"].render_report_list(payload.get("reports", ()))
        elif view_key == "validation":
            validation = self._views["validation"]
            validation.set_default_operator_initials(str(getattr(settings, "operator_initials", "") or ""))
            validation.render_cases(payload.get("validation_cases", ()))
        elif view_key == "rules":
            self._views["rules"].render_inventory(payload.get("inventory", ()))
        elif view_key == "settings":
            devices = getattr(payload["devices"], "devices", ())
            self._device_label_map = {
                f"{item.display_name} ({item.device_id})": item.device_id for item in devices
            }
            self._views["settings"].render_settings(
                settings,
                devices=devices,
                timing=payload["timing"],
            )
        elif view_key == "diagnostics":
            self._views["diagnostics"].render_diagnoses(payload.get("diagnoses", ()))
            self._views["diagnostics"].render_duplicates(payload.get("duplicates", ()))
            self._views["diagnostics"].render_candidates(())

    def _drain_processing_queue(self) -> tuple[ProcessingOutcome, ...]:
        assert self._services is not None
        outcomes: list[ProcessingOutcome] = []
        while True:
            outcome = self._services.extraction.process_next()
            if not outcome.processed:
                break
            outcomes.append(outcome)
        return tuple(outcomes)

    def _submit_processing(
        self,
        *,
        activity_message: str,
        work: object,
        on_success: object,
        on_error: object | None = None,
    ) -> bool:
        dashboard = self._views["dashboard"]

        def wrapped_work() -> object:
            return work()

        def wrapped_success(result: object) -> None:
            dashboard.set_processing_busy(False)
            dashboard.set_activity_message("Bereit.")
            on_success(result)

        def wrapped_error(exc: BaseException) -> None:
            dashboard.set_processing_busy(False)
            dashboard.set_activity_message("Bereit.")
            handler = on_error or self._show_task_error
            handler(exc)

        dashboard.set_processing_busy(True)
        dashboard.set_activity_message(activity_message)
        submitted = self._task_runner.submit(
            self.TASK_PROCESSING,
            wrapped_work,
            on_success=wrapped_success,
            on_error=wrapped_error,
        )
        if not submitted:
            dashboard.set_processing_busy(False)
            dashboard.set_activity_message("Verarbeitung läuft bereits – bitte warten.")
        return submitted

    def _pick_and_process_pdfs(self) -> None:
        from interfaces.tk.view_models import build_batch_file_statuses

        if not self._require_services():
            return
        paths = filedialog.askopenfilenames(
            parent=self,
            title="PDF-Berichte auswählen",
            filetypes=[("PDF", "*.pdf"), ("Alle Dateien", "*.*")],
        )
        if not paths:
            return
        selected = tuple(str(path) for path in paths)

        def work() -> tuple[object, tuple[ProcessingOutcome, ...]]:
            summary = self._services.extraction.enqueue_manual_pdfs(selected)
            outcomes = self._drain_processing_queue()
            return summary, outcomes

        def on_success(result: tuple[object, tuple[ProcessingOutcome, ...]]) -> None:
            summary, processing_outcomes = result
            statuses = build_batch_file_statuses(summary.outcomes, processing_outcomes)
            self._views["dashboard"].render_batch_statuses(statuses)
            self.refresh_current_view()

        self._submit_processing(
            activity_message=f"{len(selected)} Datei(en) werden verarbeitet …",
            work=work,
            on_success=on_success,
        )

    def _open_selected_dashboard_report(self) -> None:
        report_id = self._views["dashboard"].selected_report_id()
        if report_id:
            self._open_report_from_dashboard(report_id)

    def _open_report_from_dashboard(self, report_id: str) -> None:
        if not self._require_services():
            return
        self.show_view("results", refresh=False)

        def work() -> object:
            return self._services.results.get_report_detail(report_id)

        def on_success(detail: object) -> None:
            if detail is None:
                self._show_error_dialog(self, "Ergebnisse", "Bericht nicht gefunden.")
                return
            results = self._views["results"]
            self._apply_report_detail(results, detail)

        self._task_runner.submit(
            f"report-detail-{report_id}",
            work,
            on_success=on_success,
            on_error=self._show_task_error,
        )

    def _open_selected_report(self) -> None:
        if not self._require_services():
            return
        results = self._views["results"]
        report_id = results.selected_report_id()
        if not report_id:
            self._show_info_dialog(self, "Ergebnisse", "Bitte einen Bericht auswählen.")
            return

        def work() -> object:
            return self._services.results.get_report_detail(report_id)

        def on_success(detail: object) -> None:
            if detail is None:
                self._show_error_dialog(self, "Ergebnisse", "Bericht nicht gefunden.")
                return
            self._apply_report_detail(results, detail)

        self._task_runner.submit(
            f"report-detail-{report_id}",
            work,
            on_success=on_success,
            on_error=self._show_task_error,
        )

    def _apply_report_detail(self, results: object, detail: object) -> None:
        results.set_default_operator_initials(str(getattr(self._settings, "operator_initials", "") or ""))
        results.render_report_detail(detail)
        results.show_detail()

    def _save_selected_validation(self) -> None:
        self._start_validation(correct=False)

    def _set_validation_badge(self, count: int) -> None:
        badge = getattr(self, "_validation_badge", None)
        if badge is not None:
            badge.set_status(str(max(0, int(count))), kind="warning" if count else "good")

    def _save_pending_validation(self) -> None:
        if not self._require_services():
            return
        validation = self._views["validation"]
        item = validation.selected_item()
        if item is None:
            self._show_info_dialog(self, "Validierung", "Bitte eine offene Messung auswaehlen.")
            return
        if item.validation_ambiguous:
            self._show_info_dialog(self, "Validierung", "Die Validierungshistorie ist nicht eindeutig.")
            return
        initials = str(validation.validation_initials() or "").strip()
        if not initials:
            self._show_info_dialog(self, "Validierung", "Bitte Initialen fuer die Validierung angeben.")
            return
        comment = str(validation.validation_comment() or "").strip()
        key = f"validation-{item.report_id}-{item.run_id}"
        if self._task_runner.is_active(key):
            self._show_info_dialog(self, "Validierung", "Die Validierung wird bereits gespeichert.")
            return

        def work() -> tuple[object, object]:
            assert self._services is not None
            saved = self._services.results.validate_report_run(item.report_id, item.run_id, initials, comment)
            return saved, self._services.results.list_open_validation_cases()

        def on_success(result: tuple[object, object]) -> None:
            saved, items = result
            validation.clear_comment()
            validation.render_cases(items)
            self._set_validation_badge(len(items))
            export_error = str(getattr(saved, "excel_export_error", "") or "")
            if export_error:
                self._show_error_dialog(
                    self,
                    "Validierung gespeichert",
                    "Die Validierung wurde gespeichert. Der Excel-Export ist fehlgeschlagen und kann unter Diagnose erneut versucht werden.",
                )

        self._task_runner.submit(key, work, on_success=on_success, on_error=self._show_task_error)

    def _open_validation_pdf(self) -> None:
        if not self._require_services():
            return
        item = self._views["validation"].selected_item()
        if item is None:
            self._show_info_dialog(self, "PDF", "Bitte eine offene Messung auswaehlen.")
            return

        def work() -> str:
            assert self._services is not None
            return self._services.results.open_report_pdf(item.report_id)

        self._task_runner.submit(
            f"open-pdf-{item.report_id}",
            work,
            on_success=lambda _path: None,
            on_error=self._show_task_error,
        )

    def _correct_selected_validation(self) -> None:
        if not self._require_services():
            return
        request = self._selected_validation_request()
        if request is None:
            return
        if not self._show_confirm_dialog(
            self,
            "Validierung korrigieren",
            (
                "Korrektur der Validierung: Die bestehende Validierung wird nicht überschrieben. "
                "Es wird ein neuer Datensatz angelegt, der auf die bisherige Validierung verweist. "
                "Diese Korrektur jetzt speichern?"
            ),
        ):
            return
        self._submit_validation(*request, correct=True)

    def _start_validation(self, *, correct: bool) -> None:
        if not self._require_services():
            return
        request = self._selected_validation_request()
        if request is None:
            return
        self._submit_validation(*request, correct=correct)

    def _selected_validation_request(self) -> tuple[str, int, str, str] | None:
        results = self._views["results"]
        report_id = str(results.current_detail_report_id() or "")
        run_id = results.validation_run_id()
        if not report_id or run_id is None:
            self._show_info_dialog(self, "Validierung", "Bitte eine Messung auswählen.")
            return None
        initials = str(results.validation_initials() or "").strip()
        if not initials:
            self._show_info_dialog(self, "Validierung", "Bitte Initialen für die Validierung angeben.")
            return None
        return report_id, int(run_id), initials, str(results.validation_comment() or "").strip()

    def _submit_validation(self, report_id: str, run_id: int, initials: str, comment: str, *, correct: bool) -> None:
        key = f"validation-{report_id}-{run_id}"
        if self._task_runner.is_active(key):
            self._show_info_dialog(self, "Validierung", "Die Validierung wird bereits gespeichert.")
            return

        def work() -> tuple[object, object, object]:
            assert self._services is not None
            if correct:
                saved = self._services.results.correct_report_run(report_id, run_id, initials, comment)
            else:
                saved = self._services.results.validate_report_run(report_id, run_id, initials, comment)
            detail = self._services.results.get_report_detail(report_id)
            reports = self._services.results.list_recent_reports()
            return saved, detail, reports

        def on_success(result: tuple[object, object, object]) -> None:
            saved, detail, reports = result
            results = self._views["results"]
            results.render_report_list(reports)
            if detail is None:
                self._show_error_dialog(self, "Validierung", "Bericht nicht gefunden.")
                return
            results.clear_validation_comment()
            self._apply_report_detail(results, detail)
            if str(getattr(saved, "excel_export_error", "") or ""):
                self._show_error_dialog(
                    self,
                    "Validierung gespeichert",
                    "Die Validierung wurde gespeichert. Der Excel-Export ist fehlgeschlagen und kann unter Diagnose erneut versucht werden.",
                )

        self._task_runner.submit(key, work, on_success=on_success, on_error=self._show_task_error)

    def _show_results_list(self) -> None:
        self._views["results"].show_list()

    def _open_report_pdf(self) -> None:
        if not self._require_services():
            return
        report_id = self._views["results"].current_detail_report_id()
        if not report_id:
            self._show_info_dialog(self, "PDF", "Kein Bericht ausgewählt.")
            return

        def work() -> str:
            return self._services.results.open_report_pdf(report_id)

        def on_success(_path: str) -> None:
            return

        def on_error(exc: BaseException) -> None:
            if isinstance(exc, self._ReportNotFoundError):
                self._show_error_dialog(self, "PDF", "Bericht nicht gefunden.")
                return
            if isinstance(exc, self._PathOpenError):
                message = "Die PDF konnte nicht geöffnet werden."
                if str(exc) == "report_pdf_ambiguous":
                    message = "Der PDF-Pfad ist mehrdeutig."
                elif str(exc) == "report_pdf_missing":
                    message = "Für diesen Bericht ist kein PDF-Pfad hinterlegt."
                self._show_error_dialog(self, "PDF", message, details=str(exc))
                return
            self._show_task_error(exc)

        self._task_runner.submit(f"open-pdf-{report_id}", work, on_success=on_success, on_error=on_error)

    def _save_settings(self) -> None:
        if not self._require_services():
            return
        settings_view = self._views["settings"]
        settings = settings_view.collect_settings(device_id_map=self._device_label_map)
        edit_generation = settings_view.edit_generation
        self._settings_save_latest_id += 1
        request_id = self._settings_save_latest_id
        self._settings_save_latest = settings
        self._settings_save_latest_edit_generation = edit_generation

        if self._task_runner.is_active(self.TASK_SETTINGS_SAVE):
            settings_view.set_status_message("Speichern läuft bereits – bitte warten.")
            return

        self._start_settings_save(settings, request_id, edit_generation)

    def _maybe_start_pending_settings_save(self) -> None:
        if self._task_runner.is_active(self.TASK_SETTINGS_SAVE):
            return
        if self._settings_save_latest is None:
            return
        if self._settings_save_inflight_id == self._settings_save_latest_id:
            return
        self._start_settings_save(
            self._settings_save_latest,
            self._settings_save_latest_id,
            self._settings_save_latest_edit_generation,
        )

    def _start_settings_save(self, settings: object, request_id: int, edit_generation: int) -> None:
        settings_view = self._views["settings"]
        self._settings_save_inflight_id = request_id

        def work() -> object:
            return self._services.settings.save(settings)

        def on_success(saved: object) -> None:
            self._settings_save_inflight_id = None
            if request_id < self._settings_save_latest_id:
                self._maybe_start_pending_settings_save()
                return
            settings_view.mark_saved_generation(edit_generation)
            self._settings = saved
            settings_view.set_status_message("Einstellungen gespeichert.")
            self._views["dashboard"].render_watch_settings(saved)
            self._reschedule_watch()

        def on_error(exc: BaseException) -> None:
            from interfaces.tk.view_models import format_user_error_message

            self._settings_save_inflight_id = None
            if request_id < self._settings_save_latest_id:
                self._maybe_start_pending_settings_save()
                return
            if isinstance(exc, self._SettingsValidationError):
                settings_view.set_status_message(format_user_error_message(exc))
            elif isinstance(exc, self._SettingsSaveError):
                message, details = self._friendly_error_parts(exc)
                self._show_error_dialog(self, "Einstellungen", message, details=details)
            else:
                self._show_task_error(exc)

        submitted = self._task_runner.submit(
            self.TASK_SETTINGS_SAVE,
            work,
            on_success=on_success,
            on_error=on_error,
        )
        if not submitted:
            self._settings_save_inflight_id = None
            settings_view.set_status_message("Speichern läuft bereits – bitte warten.")

    def _pick_watch_input_folder(self) -> None:
        path = filedialog.askdirectory(parent=self, title="Eingabeordner wählen")
        if path:
            self._views["settings"].set_watch_input_path(path)

    def _pick_watch_backup_folder(self) -> None:
        path = filedialog.askdirectory(parent=self, title="Archivordner wählen")
        if path:
            self._views["settings"].set_watch_backup_path(path)

    def _pick_sqlite_path(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self,
            title="SQLite-Datei wählen",
            defaultextension=".sqlite3",
            filetypes=[("SQLite", "*.sqlite3"), ("Alle Dateien", "*.*")],
        )
        if path:
            self._views["settings"].set_sqlite_path(path)

    def _reload_devices(self) -> None:
        if not self._require_services():
            return
        settings_view = self._views["settings"]

        def work() -> object:
            inventory = self._services.settings.reload_device_inventory()
            timing = self._services.settings.get_watch_timing()
            return inventory, timing

        def on_success(result: tuple[object, object]) -> None:
            inventory, timing = result
            self._device_label_map = {
                f"{item.display_name} ({item.device_id})": item.device_id for item in inventory.devices
            }
            settings_view.render_settings(self._settings, devices=inventory.devices, timing=timing)

        self._task_runner.submit("devices-reload", work, on_success=on_success, on_error=self._show_task_error)

    def _open_output_folder(self) -> None:
        if not self._require_services():
            return

        def work() -> str:
            return self._services.settings.open_output_folder()

        def on_success(_path: str) -> None:
            return

        def on_error(exc: BaseException) -> None:
            message, details = self._friendly_error_parts(exc)
            self._show_error_dialog(self, "Ausgabeordner", message, details=details)

        self._task_runner.submit("open-output-folder", work, on_success=on_success, on_error=on_error)

    def _validate_rules(self) -> None:
        if not self._require_services():
            return

        def work() -> dict[str, object]:
            return self._services.rules.validate_rules_integrity()

        def on_success(report: dict[str, object]) -> None:
            self._views["rules"].render_integrity_report(report)

        self._task_runner.submit("rules-validate", work, on_success=on_success, on_error=self._show_task_error)

    def open_rule_editor(self) -> None:
        if getattr(sys, "frozen", False):
            env = os.environ.copy()
            env["ARE_HOME"] = str(self.project_root)
            env["ARE_START_RULE_EDITOR"] = "1"
            subprocess.Popen([sys.executable], cwd=str(self.project_root), env=env)
            return
        script = self.project_root / "rule_editor_main.py"
        if not script.exists():
            messagebox.showerror("Rule Editor", f"Nicht gefunden:\n{script}")
            return
        subprocess.Popen([sys.executable, str(script)], cwd=str(self.project_root))

    def _show_diagnosis_details(self) -> None:
        if not self._require_services():
            return
        diagnostics = self._views["diagnostics"]
        job_id = diagnostics.selected_job_id()
        if not job_id:
            self._show_info_dialog(self, "Diagnose", "Bitte einen Eintrag auswählen.")
            return

        def work() -> tuple[object, object]:
            item = self._services.extraction.get_job_diagnosis(job_id)
            candidates = self._services.rules.discover_assay_candidates_for_job(job_id)
            return item, candidates

        def on_success(result: tuple[object, object]) -> None:
            item, candidates = result
            if item is None:
                self._show_error_dialog(self, "Diagnose", "Diagnose nicht verfügbar.")
                return
            diagnostics.render_candidates(candidates)
            details = item.technical_detail or item.friendly_message
            if item.context_text:
                details = f"{details}\n\n{item.context_text}"
            self._show_details_dialog(self, item.error_label or "Diagnose", item.friendly_message or item.file_name, details)

        self._task_runner.submit(f"diagnosis-{job_id}", work, on_success=on_success, on_error=self._show_task_error)

    def _create_draft_from_candidate(self) -> None:
        if not self._require_services():
            return
        diagnostics = self._views["diagnostics"]
        candidate = diagnostics.selected_candidate()
        if candidate is None:
            self._show_info_dialog(self, "Draft", "Bitte einen Assay-Kandidaten auswählen.")
            return
        if not self._show_confirm_dialog(
            self,
            "Draft aus Kandidat",
            f"Draft für Assay '{candidate.assay_key}' anlegen?",
        ):
            return

        def work() -> object:
            return self._services.rules.create_draft_from_template_if_missing(
                candidate.assay_key,
                candidate.assay_name_hint or candidate.assay_key,
            )

        def on_success(_result: object) -> None:
            self.open_rule_editor()

        self._task_runner.submit(
            f"draft-{candidate.assay_key}",
            work,
            on_success=on_success,
            on_error=self._show_task_error,
        )

    def _retry_selected_job(self) -> None:
        if not self._require_services():
            return
        job_id = self._views["diagnostics"].selected_job_id()
        if not job_id:
            return

        def work() -> tuple[object, tuple[ProcessingOutcome, ...]]:
            diagnosis = self._services.extraction.get_job_diagnosis(job_id)
            if diagnosis is not None and getattr(diagnosis, "retry_kind", "") == "export_only":
                outcome = self._services.extraction.retry_excel_export(job_id)
                return outcome, (outcome,)
            item = self._services.extraction.retry_failed(job_id)
            outcomes = self._drain_processing_queue()
            return item, outcomes

        def on_success(_result: tuple[object, tuple[ProcessingOutcome, ...]]) -> None:
            self.refresh_current_view()

        self._submit_processing(
            activity_message="Fehlerhafte Verarbeitung wird erneut ausgeführt …",
            work=work,
            on_success=on_success,
        )

    def _show_duplicate_details(self) -> None:
        if not self._require_services():
            return
        candidate_id = self._views["diagnostics"].selected_duplicate_id()
        if candidate_id is None:
            return

        def work() -> object:
            return self._services.results.get_duplicate_candidate_detail(candidate_id)

        def on_success(detail: object) -> None:
            from interfaces.tk.view_models import format_duplicate_detail_lines

            if detail is None:
                self._show_error_dialog(self, "Klärfall", "Kandidat nicht gefunden.")
                return
            self._show_details_dialog(
                self,
                "Klärfall",
                f"Kandidat {candidate_id}",
                format_duplicate_detail_lines(detail),
            )

        self._task_runner.submit(
            f"duplicate-detail-{candidate_id}",
            work,
            on_success=on_success,
            on_error=self._show_task_error,
        )

    def _discard_selected_duplicate(self) -> None:
        if not self._require_services():
            return
        candidate_id = self._views["diagnostics"].selected_duplicate_id()
        if candidate_id is None:
            return
        if not self._show_confirm_dialog(
            self,
            "Klärfall verwerfen",
            f"Duplikat-Kandidat {candidate_id} wirklich verwerfen?",
        ):
            return

        def work() -> object:
            return self._services.results.discard_duplicate_candidate(candidate_id)

        def on_success(_result: object) -> None:
            self.refresh_current_view()

        self._task_runner.submit(
            f"discard-dup-{candidate_id}",
            work,
            on_success=on_success,
            on_error=self._show_task_error,
        )

    def _show_task_error(self, exc: BaseException) -> None:
        message, details = self._friendly_error_parts(exc)
        self._show_error_dialog(self, "Aktion", message, details=details)

    def _build_header(self) -> None:
        from interfaces.tk.desktop_theme import APP_SUBTITLE, APP_TITLE

        header = ttk.Frame(self, style="Header.TFrame", padding=(12, 10))
        header.pack(fill="x")
        title_col = ttk.Frame(header, style="Header.TFrame")
        title_col.pack(side="left", fill="x", expand=True)
        ttk.Label(title_col, text=APP_TITLE, style="AppTitle.TLabel").pack(anchor="w")
        ttk.Label(title_col, text=APP_SUBTITLE, style="AppSubtitle.TLabel").pack(anchor="w")
        ttk.Button(header, text="Einstellungen", command=lambda: self.show_view("settings")).pack(side="right")

    def _schedule_watch(self) -> None:
        if not self._require_services():
            return
        self._cancel_watch_schedule()
        self._watch_schedule_generation += 1
        generation = self._watch_schedule_generation
        task_key = f"watch-schedule-{generation}"

        def work() -> tuple[object, object, bool]:
            settings = self._services.settings.load()
            if not settings.watch_enabled:
                return settings, None, False
            timing = self._services.settings.get_watch_timing()
            return settings, timing, True

        def on_success(result: tuple[object, object, bool]) -> None:
            if generation != self._watch_schedule_generation:
                return
            _settings, timing, enabled = result
            if not enabled or timing is None:
                return
            delay_ms = max(1000, int(timing.scan_interval_s * 1000))
            self._watch_after_id = self.after(delay_ms, self._run_scheduled_watch)

        def on_error(exc: BaseException) -> None:
            if generation != self._watch_schedule_generation:
                return
            self._show_task_error(exc)

        self._task_runner.submit(task_key, work, on_success=on_success, on_error=on_error)

    def _reschedule_watch(self) -> None:
        self._schedule_watch()

    def _cancel_watch_schedule(self) -> None:
        if self._watch_after_id is not None:
            try:
                self.after_cancel(self._watch_after_id)
            except Exception:
                pass
            self._watch_after_id = None

    def _run_scheduled_watch(self) -> None:
        from interfaces.tk.view_models import build_batch_file_statuses

        self._watch_after_id = None
        if not self._require_services():
            return

        def work() -> tuple[object, tuple[ProcessingOutcome, ...]]:
            settings = self._services.settings.load()
            if not settings.watch_enabled:
                return None, ()
            summary = self._services.extraction.run_watch_cycle()
            outcomes = self._drain_processing_queue()
            return summary, outcomes

        def on_success(result: tuple[object, tuple[ProcessingOutcome, ...]]) -> None:
            summary, processing_outcomes = result
            self._last_watch_error = ""
            if summary is not None:
                self._last_watch_summary = summary
                dashboard = self._views["dashboard"]
                dashboard.render_watch_session_summary(summary)
                if summary.outcomes:
                    statuses = build_batch_file_statuses(summary.outcomes, processing_outcomes)
                    if statuses:
                        dashboard.render_batch_statuses(statuses)
            if self._current_view != "settings":
                self.refresh_current_view()
            self._schedule_watch()

        def on_error(exc: BaseException) -> None:
            message, details = self._friendly_error_parts(exc)
            self._last_watch_summary = None
            self._last_watch_error = message
            self._views["dashboard"].render_watch_session_summary(None, error=message)
            if isinstance(exc, self._ApplicationWatchError):
                self._show_error_dialog(self, "Auto-Import", message, details=details)
            self._schedule_watch()

        if not self._submit_processing(
            activity_message="Auto-Import wird ausgeführt …",
            work=work,
            on_success=on_success,
            on_error=on_error,
        ):
            self._schedule_watch()

    def close_app(self) -> None:
        if self._task_runner.is_active(self.TASK_PROCESSING) or self._task_runner.has_in_flight_workers():
            messagebox.showinfo(
                "Bitte warten",
                "Eine Verarbeitung läuft noch. Das Fenster bleibt geöffnet, bis die Verarbeitung abgeschlossen ist.",
                parent=self,
            )
            return
        self._cancel_watch_schedule()
        self._task_runner.shutdown_runner()
        self.destroy()

    def destroy(self) -> None:
        if getattr(self, "_watch_after_id", None):
            self._cancel_watch_schedule()
        if getattr(self, "_task_runner", None) and not self._task_runner.shutdown:
            self._task_runner.shutdown_runner()
        super().destroy()
