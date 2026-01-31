from __future__ import annotations

import json
import os
import re
import shutil
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox

from src.jobcontroller.api import JobController


class MinimalBatchGUI(tk.Tk):
    """
    Minimalistische GUI + Regex-Tester:

    - PDFs auswählen
    - Batch-Import (wie bisher)
    - Buttons zum Leeren von /jobs und /output/final
    - Regex testen:
        - läuft die vollständige Extraktionskette (JobController.submit)
        - lädt anschließend jobs/<job_id>.json und zeigt extrahierte Daten an
        - Regex kann gegen erzeugte *_normalized.txt oder *_block.txt Dateien getestet werden
    """

    def __init__(self) -> None:
        super().__init__()

        self.title("AnalyzerExtractorV2 – Minimal GUI + Regex Tester")
        self.geometry("1100x720")

        self.project_root = str(Path(__file__).resolve().parent)
        self.selected_files: list[str] = []
        self._is_running = False

        # Regex Tester state
        self.last_job_id: str | None = None
        self.last_job_dir: Path | None = None
        self.regex_target_files: list[Path] = []

        self._build_ui()

    # =========================
    # UI
    # =========================

    def _build_ui(self) -> None:
        # Top bar
        top = tk.Frame(self)
        top.pack(fill="x", padx=10, pady=10)

        btn_pick = tk.Button(top, text="PDFs auswählen…", command=self.on_pick_pdfs)
        btn_pick.pack(side="left")

        btn_clear = tk.Button(top, text="Liste leeren", command=self.on_clear_list)
        btn_clear.pack(side="left", padx=(8, 0))

        self.btn_run = tk.Button(top, text="Import starten", command=self.on_run)
        self.btn_run.pack(side="left", padx=(8, 0))

        btn_regex_chain = tk.Button(top, text="Regex testen (volle Kette)", command=self.on_regex_full_chain)
        btn_regex_chain.pack(side="left", padx=(8, 0))

        btn_clear_jobs = tk.Button(top, text="/jobs leeren", command=self.on_clear_jobs)
        btn_clear_jobs.pack(side="left", padx=(18, 0))

        btn_clear_final = tk.Button(top, text="/output/final leeren", command=self.on_clear_output_final)
        btn_clear_final.pack(side="left", padx=(8, 0))

        self.lbl_status = tk.Label(top, text="Bereit.")
        self.lbl_status.pack(side="right")

        # Main area
        middle = tk.Frame(self)
        middle.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # Left: file list
        left = tk.Frame(middle)
        left.pack(side="left", fill="both", expand=True)

        tk.Label(left, text="Ausgewählte PDFs:").pack(anchor="w")

        self.listbox = tk.Listbox(left, height=12)
        self.listbox.pack(fill="both", expand=True)

        # Right: output + regex tester
        right = tk.Frame(middle)
        right.pack(side="left", fill="both", expand=True, padx=(10, 0))

        tk.Label(right, text="Ausgabe / Log:").pack(anchor="w")

        self.txt_log = tk.Text(right, height=18, wrap="word")
        self.txt_log.pack(fill="both", expand=True)

        # Regex tester panel
        regex_panel = tk.LabelFrame(self, text="Regex Tester")
        regex_panel.pack(fill="x", padx=10, pady=(0, 10))

        row1 = tk.Frame(regex_panel)
        row1.pack(fill="x", padx=8, pady=(8, 4))

        tk.Label(row1, text="Regex:").pack(side="left")
        self.ent_regex = tk.Entry(row1)
        self.ent_regex.pack(side="left", fill="x", expand=True, padx=(6, 6))

        self.var_regex_flags = tk.StringVar(value="MULTILINE")
        flags_menu = tk.OptionMenu(row1, self.var_regex_flags, "NONE", "MULTILINE", "DOTALL", "MULTILINE|DOTALL")
        flags_menu.pack(side="left")

        btn_run_regex = tk.Button(row1, text="Regex auf Zieltext testen", command=self.on_run_regex)
        btn_run_regex.pack(side="left", padx=(8, 0))

        row2 = tk.Frame(regex_panel)
        row2.pack(fill="x", padx=8, pady=(0, 8))

        tk.Label(row2, text="Zieltext-Datei (aus /jobs):").pack(side="left")

        self.var_target_file = tk.StringVar(value="")
        self.dd_target = tk.OptionMenu(row2, self.var_target_file, "")
        self.dd_target.config(width=60)
        self.dd_target.pack(side="left", padx=(6, 6), fill="x", expand=True)

        btn_refresh_targets = tk.Button(row2, text="Ziel-Dateien neu laden", command=self.refresh_regex_targets)
        btn_refresh_targets.pack(side="left")

        # Footer: project_root
        footer = tk.Frame(self)
        footer.pack(fill="x", padx=10, pady=(0, 10))

        tk.Label(footer, text="project_root:").pack(side="left")
        self.ent_root = tk.Entry(footer)
        self.ent_root.pack(side="left", fill="x", expand=True, padx=(6, 6))
        self.ent_root.insert(0, self.project_root)

        btn_set_root = tk.Button(footer, text="Ordner wählen…", command=self.on_pick_root)
        btn_set_root.pack(side="left")

    # =========================
    # Helpers / Logging
    # =========================

    def _log(self, msg: str) -> None:
        def _append() -> None:
            self.txt_log.insert(tk.END, msg + "\n")
            self.txt_log.see(tk.END)

        self.after(0, _append)

    def _set_status(self, msg: str) -> None:
        self.after(0, lambda: self.lbl_status.config(text=msg))

    def _enable_run_button(self) -> None:
        self.after(0, lambda: self.btn_run.config(state="normal"))

    def _disable_run_button(self) -> None:
        self.after(0, lambda: self.btn_run.config(state="disabled"))

    # =========================
    # Project root + PDF list
    # =========================

    def on_pick_root(self) -> None:
        if self._is_running:
            return

        d = filedialog.askdirectory(title="Projekt-Root auswählen (Repo-Ordner)")
        if not d:
            return

        self.project_root = d
        self.ent_root.delete(0, tk.END)
        self.ent_root.insert(0, self.project_root)
        self._log(f"project_root gesetzt: {self.project_root}")

    def on_pick_pdfs(self) -> None:
        if self._is_running:
            return

        files = filedialog.askopenfilenames(
            title="PDFs auswählen",
            filetypes=[("PDF Dateien", "*.pdf")],
        )
        if not files:
            return

        for f in files:
            if f not in self.selected_files:
                self.selected_files.append(f)

        self._refresh_listbox()
        self._log(f"{len(files)} Datei(en) hinzugefügt. Gesamt: {len(self.selected_files)}")

    def on_clear_list(self) -> None:
        if self._is_running:
            return

        self.selected_files = []
        self._refresh_listbox()
        self._log("Liste geleert.")

    def _refresh_listbox(self) -> None:
        self.listbox.delete(0, tk.END)
        for f in self.selected_files:
            self.listbox.insert(tk.END, f)

    # =========================
    # Clear folders
    # =========================

    def on_clear_jobs(self) -> None:
        if self._is_running:
            return

        root = self.ent_root.get().strip()
        jobs_dir = Path(root) / "jobs"
        if not jobs_dir.exists():
            messagebox.showinfo("Info", f"Ordner existiert nicht:\n{jobs_dir}")
            return

        if not messagebox.askyesno("Bestätigung", f"Wirklich ALLES in /jobs löschen?\n\n{jobs_dir}"):
            return

        deleted = self._clear_directory_contents(jobs_dir)
        self._log(f"/jobs geleert. Gelöscht: {deleted} Einträge.")
        self.refresh_regex_targets()

    def on_clear_output_final(self) -> None:
        if self._is_running:
            return

        root = self.ent_root.get().strip()
        final_dir = Path(root) / "output" / "final"
        if not final_dir.exists():
            messagebox.showinfo("Info", f"Ordner existiert nicht:\n{final_dir}")
            return

        if not messagebox.askyesno("Bestätigung", f"Wirklich ALLES in /output/final löschen?\n\n{final_dir}"):
            return

        deleted = self._clear_directory_contents(final_dir)
        self._log(f"/output/final geleert. Gelöscht: {deleted} Einträge.")

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
                self._log(f"  [WARN] Konnte nicht löschen: {item} -> {e}")
        return count

    # =========================
    # Import (Batch)
    # =========================

    def on_run(self) -> None:
        if self._is_running:
            return

        root = self.ent_root.get().strip()
        if not root:
            messagebox.showerror("Fehler", "project_root ist leer.")
            return
        if not Path(root).exists():
            messagebox.showerror("Fehler", f"project_root existiert nicht:\n{root}")
            return
        if not self.selected_files:
            messagebox.showinfo("Info", "Bitte zuerst PDFs auswählen.")
            return

        self.project_root = root

        self._is_running = True
        self._disable_run_button()
        self._set_status("Läuft…")

        t = threading.Thread(target=self._run_batch, daemon=True)
        t.start()

    def _run_batch(self) -> None:
        jc = JobController()

        total = len(self.selected_files)
        done = 0

        self._log("=== Batch-Import gestartet ===")
        self._log(f"project_root: {self.project_root}")
        self._log(f"Anzahl PDFs: {total}\n")

        for pdf in self.selected_files:
            done += 1
            self._set_status(f"{done}/{total} …")

            self._log(f"[{done}/{total}] Import: {pdf}")
            try:
                result = jc.submit(pdf, self.project_root)
                self._log(f"  -> status={result.status}, job_id={result.job_id}")
                if result.details:
                    if "reason" in result.details:
                        self._log(f"     reason={result.details.get('reason')}")
                    if "error" in result.details:
                        self._log(f"     error={result.details.get('error')}")
                    if "writes" in result.details:
                        writes = result.details.get("writes") or []
                        for w in writes:
                            self._log(
                                f"     write: {w.get('excel_path')} | sheet={w.get('sheet')} | {w.get('status')}"
                            )
            except Exception as e:
                self._log(f"  -> EXCEPTION: {e}")

            self._log("")

        self._log("=== Batch-Import beendet ===")

        self._is_running = False
        self._set_status("Fertig.")
        self._enable_run_button()

    # =========================
    # Regex Tester: Full chain + display extracted data
    # =========================

    def on_regex_full_chain(self) -> None:
        """
        Läuft die komplette Kette auf *einer* PDF (aus der Liste) und zeigt danach:
        - extrahierte Daten aus jobs/<job_id>.json (wenn vorhanden)
        - sonst Fallback: kompletter State
        Zusätzlich werden Regex-Zieltexte (normalized/block) in den Dropdown geladen.
        """
        if self._is_running:
            return

        root = self.ent_root.get().strip()
        if not root or not Path(root).exists():
            messagebox.showerror("Fehler", "project_root ist ungültig.")
            return

        if not self.selected_files:
            messagebox.showinfo("Info", "Bitte zuerst mindestens eine PDF auswählen.")
            return

        # Wir nehmen die aktuell selektierte PDF, sonst die erste.
        pdf = None
        sel = self.listbox.curselection()
        if sel:
            pdf = self.selected_files[int(sel[0])]
        else:
            pdf = self.selected_files[0]

        self.project_root = root

        self._is_running = True
        self._disable_run_button()
        self._set_status("Regex-Chain läuft…")

        t = threading.Thread(target=self._run_full_chain_for_regex, args=(pdf,), daemon=True)
        t.start()

    def _run_full_chain_for_regex(self, pdf: str) -> None:
        jc = JobController()

        self._log("=== Regex-Test: volle Kette ===")
        self._log(f"PDF: {pdf}")
        self._log(f"project_root: {self.project_root}\n")

        try:
            result = jc.submit(pdf, self.project_root)
            self.last_job_id = result.job_id
            self.last_job_dir = Path(self.project_root) / "jobs"

            self._log(f"JobController.submit -> status={result.status}, job_id={result.job_id}")

            # Job state laden (falls vorhanden)
            state_path = (Path(self.project_root) / "jobs" / f"{result.job_id}.json")
            if state_path.exists():
                state = json.loads(state_path.read_text(encoding="utf-8"))
                self._log("\n--- Extrahierte Daten (aus Job-State) ---")
                self._print_extracted_from_state(state)
            else:
                self._log("\n[WARN] Job-State nicht gefunden:")
                self._log(f"  {state_path}")

            self._log("\n--- Regex Ziel-Dateien (jobs) ---")
            self.refresh_regex_targets(job_id=result.job_id)
            self._log("Ziel-Dateien geladen. Wähle im Dropdown und nutze 'Regex auf Zieltext testen'.\n")

        except Exception as e:
            self._log(f"[ERROR] Full chain failed: {e}")

        self._log("=== Ende Regex-Test (volle Kette) ===\n")

        self._is_running = False
        self._set_status("Fertig.")
        self._enable_run_button()

    def _print_extracted_from_state(self, state: dict) -> None:
        """
        Versucht, aus dem Job-State die 'Extractor'-Ergebnisse zu finden.
        Falls Struktur anders ist, wird am Ende ein Fallback (pretty JSON) ausgegeben.
        """
        steps = state.get("steps", [])
        if not isinstance(steps, list):
            self._log("[WARN] state.steps ist nicht eine Liste. Fallback JSON folgt.")
            self._log(json.dumps(state, ensure_ascii=False, indent=2))
            return

        # Suche nach bekannten Step-Namen
        extractor_payloads = []
        for s in steps:
            if not isinstance(s, dict):
                continue
            step_name = str(s.get("step", "")).lower()
            if step_name in ("extractor", "extract", "extraction"):
                extractor_payloads.append(s)

        if extractor_payloads:
            for idx, payload in enumerate(extractor_payloads, start=1):
                self._log(f"\n[Extractor Step #{idx}]")
                # Typische Varianten: records / record / data
                if "records" in payload:
                    self._print_records(payload.get("records"))
                elif "record" in payload:
                    self._print_records(payload.get("record"))
                elif "data" in payload:
                    self._print_records(payload.get("data"))
                else:
                    # unbekannt -> dump payload
                    self._log(json.dumps(payload, ensure_ascii=False, indent=2))
            return

        # Kein extractor step gefunden -> Fallback: versuche dennoch record.data aus anderen steps zu finden
        # (wir bleiben defensiv, weil Struktur projektabhängig ist)
        for s in steps:
            if isinstance(s, dict) and "writes" in s:
                self._log("\n[Writer Step]")
                self._log(json.dumps(s, ensure_ascii=False, indent=2))

        self._log("\n[Fallback] Konnte keinen 'extractor' Step finden – kompletter State:")
        self._log(json.dumps(state, ensure_ascii=False, indent=2))

    def _print_records(self, rec_obj) -> None:
        """
        Druckt record/data Strukturen möglichst lesbar.
        Unterstützt:
        - dict (ein record)
        - list[dict] (mehrere)
        - andere -> json dump
        """
        if isinstance(rec_obj, list):
            for i, r in enumerate(rec_obj, start=1):
                self._log(f"  Record #{i}:")
                self._print_one_record(r, indent="    ")
        elif isinstance(rec_obj, dict):
            self._print_one_record(rec_obj, indent="  ")
        else:
            self._log(json.dumps(rec_obj, ensure_ascii=False, indent=2))

    def _print_one_record(self, r: dict, indent: str) -> None:
        if not isinstance(r, dict):
            self._log(indent + str(r))
            return

        # Häufig: {"assay_key":..., "lot_id":..., "data": {...}}
        # Wir versuchen, 'data' hübsch zu drucken, wenn vorhanden.
        assay_key = r.get("assay_key")
        lot_id = r.get("lot_id")
        if assay_key is not None:
            self._log(f"{indent}assay_key: {assay_key}")
        if lot_id is not None:
            self._log(f"{indent}lot_id: {lot_id}")

        data = r.get("data")
        if isinstance(data, dict):
            for k in sorted(data.keys()):
                self._log(f"{indent}{k}: {data.get(k)}")
        else:
            # Falls record selbst schon flach ist
            for k in sorted(r.keys()):
                if k in ("assay_key", "lot_id", "data"):
                    continue
                self._log(f"{indent}{k}: {r.get(k)}")

    # =========================
    # Regex tester against job artifacts
    # =========================

    def refresh_regex_targets(self, job_id: str | None = None) -> None:
        """
        Lädt mögliche Zieltexte aus /jobs:
        - <job_id>_normalized.txt
        - <job_id>_*_block.txt
        Wenn job_id None: verwendet last_job_id.
        """
        root = self.ent_root.get().strip()
        jobs_dir = Path(root) / "jobs"
        if not jobs_dir.exists():
            self._log("[WARN] /jobs existiert nicht, keine Zieltexte.")
            return

        if job_id is None:
            job_id = self.last_job_id

        targets: list[Path] = []

        if job_id:
            # exakt für diesen Job
            targets.extend(sorted(jobs_dir.glob(f"{job_id}_normalized.txt")))
            targets.extend(sorted(jobs_dir.glob(f"{job_id}_*_block.txt")))
        else:
            # fallback: alles anbieten (kann groß sein)
            targets.extend(sorted(jobs_dir.glob("*_normalized.txt")))
            targets.extend(sorted(jobs_dir.glob("*_block.txt")))

        self.regex_target_files = targets

        # Dropdown neu aufbauen
        def _rebuild_dropdown() -> None:
            menu = self.dd_target["menu"]
            menu.delete(0, "end")

            if not self.regex_target_files:
                self.var_target_file.set("")
                menu.add_command(label="", command=lambda: self.var_target_file.set(""))
                return

            # hübsche labels (nur filename)
            first_label = self.regex_target_files[0].name
            self.var_target_file.set(first_label)

            for p in self.regex_target_files:
                lbl = p.name
                menu.add_command(label=lbl, command=lambda v=lbl: self.var_target_file.set(v))

        self.after(0, _rebuild_dropdown)

    def on_run_regex(self) -> None:
        """
        Testet den Regex gegen die aktuell ausgewählte Zieltext-Datei aus /jobs.
        Gibt Match + Gruppen im Log aus.
        """
        regex = self.ent_regex.get().strip()
        if not regex:
            messagebox.showinfo("Info", "Bitte Regex eingeben.")
            return

        target_name = self.var_target_file.get().strip()
        if not target_name:
            messagebox.showinfo("Info", "Bitte eine Zieltext-Datei auswählen (Dropdown).")
            return

        root = self.ent_root.get().strip()
        jobs_dir = Path(root) / "jobs"
        target_path = jobs_dir / target_name
        if not target_path.exists():
            messagebox.showerror("Fehler", f"Zieltext-Datei nicht gefunden:\n{target_path}")
            return

        try:
            text = target_path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            messagebox.showerror("Fehler", f"Konnte Datei nicht lesen:\n{e}")
            return

        flags = 0
        flag_choice = self.var_regex_flags.get()
        if flag_choice == "MULTILINE":
            flags = re.MULTILINE
        elif flag_choice == "DOTALL":
            flags = re.DOTALL
        elif flag_choice == "MULTILINE|DOTALL":
            flags = re.MULTILINE | re.DOTALL

        self._log("=== Regex Test ===")
        self._log(f"Target: {target_path}")
        self._log(f"Flags: {flag_choice}")
        self._log(f"Regex: {regex}")

        try:
            pattern = re.compile(regex, flags)
        except re.error as e:
            self._log(f"[REGEX ERROR] {e}")
            self._log("=== Ende Regex Test ===\n")
            return

        m = pattern.search(text)
        if not m:
            self._log("-> Kein Treffer.")
            self._log("=== Ende Regex Test ===\n")
            return

        self._log("-> Treffer gefunden.")
        self._log(f"   match[0]: {m.group(0)}")
        if m.groups():
            for i, g in enumerate(m.groups(), start=1):
                self._log(f"   group({i}): {g}")

        # Context anzeigen (Zeile + Umgebung)
        ctx = self._extract_match_context(text, m.start(), m.end(), max_lines=6)
        self._log("\n--- Kontext (Ausschnitt) ---")
        self._log(ctx)
        self._log("=== Ende Regex Test ===\n")

    def _extract_match_context(self, text: str, start: int, end: int, max_lines: int = 6) -> str:
        """
        Gibt einen kurzen Kontext um den Match zurück (einige Zeilen davor/danach).
        """
        lines = text.splitlines()
        # Position -> Zeilenindex bestimmen
        pos = 0
        hit_line_idx = 0
        for i, ln in enumerate(lines):
            # +1 wegen splitlines ohne \n
            next_pos = pos + len(ln) + 1
            if pos <= start < next_pos:
                hit_line_idx = i
                break
            pos = next_pos

        lo = max(0, hit_line_idx - max_lines)
        hi = min(len(lines), hit_line_idx + max_lines + 1)

        out = []
        for i in range(lo, hi):
            prefix = ">> " if i == hit_line_idx else "   "
            out.append(f"{prefix}{lines[i]}")
        return "\n".join(out)


if __name__ == "__main__":
    app = MinimalBatchGUI()
    app.mainloop()
