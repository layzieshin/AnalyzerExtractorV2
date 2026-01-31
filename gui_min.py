from __future__ import annotations

import os
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox

from src.jobcontroller.api import JobController


class MinimalBatchGUI(tk.Tk):
    """
    Minimalistische GUI (Option A):
    - User wählt mehrere PDFs aus
    - GUI ruft JobController.submit(...) pro PDF sequenziell auf
    - Ergebnisse werden geloggt
    """

    def __init__(self) -> None:
        super().__init__()

        self.title("AnalyzerExtractorV2 – Minimal GUI (Batch Option A)")
        self.geometry("900x520")

        # project_root = Repo-Ordner (da, wo gui_min.py liegt)
        self.project_root = str(Path(__file__).resolve().parent)

        self.selected_files: list[str] = []
        self._is_running = False

        self._build_ui()

    def _build_ui(self) -> None:
        top = tk.Frame(self)
        top.pack(fill="x", padx=10, pady=10)

        btn_pick = tk.Button(top, text="PDFs auswählen…", command=self.on_pick_pdfs)
        btn_pick.pack(side="left")

        btn_clear = tk.Button(top, text="Liste leeren", command=self.on_clear_list)
        btn_clear.pack(side="left", padx=(8, 0))

        self.btn_run = tk.Button(top, text="Import starten", command=self.on_run)
        self.btn_run.pack(side="left", padx=(8, 0))

        # Statuszeile
        self.lbl_status = tk.Label(top, text="Bereit.")
        self.lbl_status.pack(side="right")

        middle = tk.Frame(self)
        middle.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # Dateiliste
        left = tk.Frame(middle)
        left.pack(side="left", fill="both", expand=True)

        tk.Label(left, text="Ausgewählte PDFs:").pack(anchor="w")

        self.listbox = tk.Listbox(left, height=12)
        self.listbox.pack(fill="both", expand=True)

        # Log
        right = tk.Frame(middle)
        right.pack(side="left", fill="both", expand=True, padx=(10, 0))

        tk.Label(right, text="Log:").pack(anchor="w")

        self.txt_log = tk.Text(right, height=12, wrap="word")
        self.txt_log.pack(fill="both", expand=True)

        # Footer: project_root anzeigen
        footer = tk.Frame(self)
        footer.pack(fill="x", padx=10, pady=(0, 10))

        tk.Label(footer, text="project_root:").pack(side="left")
        self.ent_root = tk.Entry(footer)
        self.ent_root.pack(side="left", fill="x", expand=True, padx=(6, 6))
        self.ent_root.insert(0, self.project_root)

        btn_set_root = tk.Button(footer, text="Ordner wählen…", command=self.on_pick_root)
        btn_set_root.pack(side="left")

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

        # anhängen (nicht ersetzen) – minimalistisch, aber praktisch
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

    def on_run(self) -> None:
        if self._is_running:
            return

        # Root aus Entry übernehmen (falls User es editiert hat)
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

        # In separatem Thread ausführen, damit GUI nicht einfriert
        self._is_running = True
        self.btn_run.config(state="disabled")
        self.lbl_status.config(text="Läuft…")

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
                # result ist JobResult (dataclass) – wir loggen kompakt
                self._log(f"  -> status={result.status}, job_id={result.job_id}")
                if result.details:
                    # nur ein paar wichtige Felder hübsch ausgeben
                    if "reason" in result.details:
                        self._log(f"     reason={result.details.get('reason')}")
                    if "error" in result.details:
                        self._log(f"     error={result.details.get('error')}")
                    if "writes" in result.details:
                        writes = result.details.get("writes") or []
                        for w in writes:
                            self._log(f"     write: {w.get('excel_path')} | sheet={w.get('sheet')} | {w.get('status')}")
            except Exception as e:
                self._log(f"  -> EXCEPTION: {e}")

            self._log("")

        self._log("=== Batch-Import beendet ===")

        # GUI wieder freigeben
        self._is_running = False
        self._set_status("Fertig.")
        self._enable_run_button()

    def _refresh_listbox(self) -> None:
        self.listbox.delete(0, tk.END)
        for f in self.selected_files:
            self.listbox.insert(tk.END, f)

    def _log(self, msg: str) -> None:
        def _append() -> None:
            self.txt_log.insert(tk.END, msg + "\n")
            self.txt_log.see(tk.END)

        self.after(0, _append)

    def _set_status(self, msg: str) -> None:
        self.after(0, lambda: self.lbl_status.config(text=msg))

    def _enable_run_button(self) -> None:
        self.after(0, lambda: self.btn_run.config(state="normal"))


if __name__ == "__main__":
    app = MinimalBatchGUI()
    app.mainloop()
