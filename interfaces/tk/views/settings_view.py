from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Sequence
from tkinter import ttk

from interfaces.tk.widgets.common import Card, SectionHeader
from src.application.api import DesktopSettings, DeviceInventoryItem, QCConfigurationState, QCAssayConfigurationItem, WatchTimingSettings


class SettingsView(ttk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        *,
        on_save: Callable[[], None],
        on_pick_watch_input: Callable[[], None],
        on_pick_watch_backup: Callable[[], None],
        on_pick_sqlite: Callable[[], None],
        on_reload_devices: Callable[[], None],
        on_open_output_folder: Callable[[], None],
        on_manage_devices: Callable[[], None] | None = None,
        on_migrate_devices: Callable[[], None] | None = None,
        on_manage_profiles: Callable[[], None] | None = None,
        on_new_qc_profile: Callable[[], None] | None = None,
        on_refresh_qc: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(master, style="Content.TFrame")
        self._on_save = on_save
        self._on_pick_watch_input = on_pick_watch_input
        self._on_pick_watch_backup = on_pick_watch_backup
        self._on_pick_sqlite = on_pick_sqlite
        self._on_reload_devices = on_reload_devices
        self._on_open_output_folder = on_open_output_folder
        self._on_manage_devices = on_manage_devices or (lambda: None)
        self._on_migrate_devices = on_migrate_devices or (lambda: None)
        self._on_manage_profiles = on_manage_profiles or (lambda: None)
        self._on_new_qc_profile = on_new_qc_profile or self._on_manage_profiles
        self._on_refresh_qc = on_refresh_qc or (lambda: None)
        self._qc_rows: dict[str, QCAssayConfigurationItem] = {}
        self._qc_state: QCConfigurationState | None = None
        self._edit_generation = 0
        self._clean_generation = 0
        self._suppress_dirty = False
        self._build()
        self._bind_dirty_tracking()

    def _build(self) -> None:
        card = Card(self)
        card.pack(fill="both", expand=True)
        self._notebook = ttk.Notebook(card.body)
        self._notebook.pack(fill="both", expand=True)
        general = ttk.Frame(self._notebook, style="CardInner.TFrame", padding=6)
        qc = ttk.Frame(self._notebook, style="CardInner.TFrame", padding=8)
        self._notebook.add(general, text="Allgemein & Geräte")
        self._notebook.add(qc, text="Assays & QK")
        self._build_qc_tab(qc)
        footer = ttk.Frame(general, style="CardInner.TFrame")
        footer.pack(side="bottom", fill="x", pady=(6, 0))
        scroll = ttk.Scrollbar(general, orient="vertical")
        scroll.pack(side="right", fill="y")
        self._settings_canvas = tk.Canvas(general, highlightthickness=0, yscrollcommand=scroll.set)
        self._settings_canvas.pack(fill="both", expand=True)
        scroll.configure(command=self._settings_canvas.yview)
        body = ttk.Frame(self._settings_canvas, style="CardInner.TFrame")
        window = self._settings_canvas.create_window((0, 0), window=body, anchor="nw")
        body.bind("<Configure>", lambda _event: self._settings_canvas.configure(scrollregion=self._settings_canvas.bbox("all")))
        self._settings_canvas.bind("<Configure>", lambda event: self._settings_canvas.itemconfigure(window, width=event.width))
        SectionHeader(body, "Einstellungen", subtitle="Konfiguration für Import, Ausgabe und Geräte.").pack(
            fill="x", pady=(0, 12)
        )

        self._var_watch_enabled = tk.BooleanVar(value=False)
        ttk.Checkbutton(body, text="Automatischer Import aktiv", variable=self._var_watch_enabled).pack(anchor="w")

        row_input = ttk.Frame(body, style="CardInner.TFrame")
        row_input.pack(fill="x", pady=(8, 4))
        ttk.Label(row_input, text="Eingabeordner").pack(side="left")
        self._var_watch_input = tk.StringVar()
        ttk.Entry(row_input, textvariable=self._var_watch_input).pack(side="left", fill="x", expand=True, padx=8)
        ttk.Button(row_input, text="...", width=3, command=self._on_pick_watch_input).pack(side="left")

        row_backup = ttk.Frame(body, style="CardInner.TFrame")
        row_backup.pack(fill="x", pady=4)
        ttk.Label(row_backup, text="Archivordner").pack(side="left")
        self._var_watch_backup = tk.StringVar()
        ttk.Entry(row_backup, textvariable=self._var_watch_backup).pack(side="left", fill="x", expand=True, padx=8)
        ttk.Button(row_backup, text="...", width=3, command=self._on_pick_watch_backup).pack(side="left")

        self._var_watch_recursive = tk.BooleanVar(value=False)
        ttk.Checkbutton(body, text="Unterordner einbeziehen", variable=self._var_watch_recursive).pack(
            anchor="w", pady=(4, 8)
        )

        ttk.Label(
            body,
            text="Ergebnisse und Validierungen werden in SQLite gespeichert. Das Original-PDF dient zur Prüfung.",
            style="Muted.TLabel",
        ).pack(anchor="w")

        row_device = ttk.Frame(body, style="CardInner.TFrame")
        row_device.pack(fill="x", pady=4)
        ttk.Label(row_device, text="Gerät").pack(side="left")
        self._var_device = tk.StringVar()
        self._device_combo = ttk.Combobox(row_device, textvariable=self._var_device, state="readonly", width=40)
        self._device_combo.pack(side="left", padx=8)
        ttk.Button(row_device, text="Neu laden", command=self._on_reload_devices).pack(side="left")
        management = ttk.Frame(body, style="CardInner.TFrame")
        management.pack(fill="x", pady=(4, 6))
        ttk.Button(management, text="Geräte verwalten", command=self._on_manage_devices).pack(side="left")
        ttk.Button(management, text="Geräte übernehmen", command=self._on_migrate_devices).pack(side="left", padx=6)

        row_initials = ttk.Frame(body, style="CardInner.TFrame")
        row_initials.pack(fill="x", pady=(8, 4))
        ttk.Label(row_initials, text="Operator-Initialen").pack(side="left")
        self._var_operator_initials = tk.StringVar()
        ttk.Entry(row_initials, textvariable=self._var_operator_initials, width=16).pack(side="left", padx=8)
        ttk.Label(
            body,
            text="Vorschlag für die Ergebnis-Validierung. Keine Benutzerverwaltung.",
            style="Muted.TLabel",
        ).pack(anchor="w")

        ttk.Button(body, text="Ausgabeordner öffnen", command=self._on_open_output_folder).pack(anchor="w", pady=(8, 0))

        advanced = ttk.LabelFrame(body, text="Erweitert", padding=8)
        advanced.pack(fill="x", pady=(12, 8))
        row_sqlite = ttk.Frame(advanced)
        row_sqlite.pack(fill="x")
        ttk.Label(row_sqlite, text="SQLite-Pfad").pack(side="left")
        self._var_sqlite = tk.StringVar()
        ttk.Entry(row_sqlite, textvariable=self._var_sqlite).pack(side="left", fill="x", expand=True, padx=8)
        ttk.Button(row_sqlite, text="...", width=3, command=self._on_pick_sqlite).pack(side="left")
        self._lbl_timing = ttk.Label(advanced, text="", style="Muted.TLabel", wraplength=640)
        self._lbl_timing.pack(anchor="w", pady=(8, 0))

        self._lbl_status = ttk.Label(body, text="", style="Muted.TLabel", wraplength=640)
        self._lbl_status.pack(anchor="w", pady=(4, 8))
        self._btn_save = ttk.Button(footer, text="Speichern", style="Primary.TButton", command=self._on_save)
        self._btn_save.pack(anchor="w")

    def _build_qc_tab(self, parent: ttk.Frame) -> None:
        SectionHeader(parent, "Assays & QK", subtitle="Aktive Assays und ihre Geräte-/Profilbindungen. Jede Profilfassung bleibt nachvollziehbar.").pack(fill="x", pady=(0, 10))
        actions = ttk.Frame(parent)
        actions.pack(side="bottom", fill="x", pady=(8, 0))
        self._qc_edit = ttk.Button(actions, text="Einrichten / Bearbeiten", command=self._on_manage_profiles, state="disabled")
        self._qc_edit.pack(side="left")
        self._qc_new = ttk.Button(actions, text="Weiteres Profil", command=self._on_new_qc_profile, state="disabled")
        self._qc_new.pack(side="left", padx=8)
        ttk.Button(actions, text="Neu laden", command=self._on_refresh_qc).pack(side="right")
        self._qc_detail = ttk.Label(parent, text="Assay auswählen, um QK-Level einzurichten.", wraplength=780)
        self._qc_detail.pack(side="bottom", anchor="w", pady=6)
        columns = ("assay", "device", "profile", "levels", "status")
        self._qc_tree = ttk.Treeview(parent, columns=columns, show="headings", selectmode="browse", height=10)
        for key, label, width in zip(columns, ("Assay / Kennung", "Gerät / Kennung", "Profil / Kennung", "Level", "QK-Konfiguration"), (220, 200, 220, 55, 190)):
            self._qc_tree.heading(key, text=label)
            self._qc_tree.column(key, width=width, minwidth=50)
        scroll_y = ttk.Scrollbar(parent, orient="vertical", command=self._qc_tree.yview)
        scroll_y.pack(side="right", fill="y")
        scroll_x = ttk.Scrollbar(parent, orient="horizontal", command=self._qc_tree.xview)
        scroll_x.pack(side="bottom", fill="x")
        self._qc_tree.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        self._qc_tree.pack(fill="both", expand=True)
        self._qc_tree.bind("<<TreeviewSelect>>", self._select_qc_row)
        self._qc_tree.bind("<Double-1>", lambda _event: self._on_manage_profiles() if self.selected_qc_configuration() else None)

    def selected_qc_configuration(self) -> QCAssayConfigurationItem | None:
        selection = self._qc_tree.selection()
        return self._qc_rows.get(selection[0]) if selection else None

    def _select_qc_row(self, _event=None) -> None:
        row = self.selected_qc_configuration()
        self._qc_edit.configure(state="normal" if row else "disabled")
        self._qc_edit.configure(text="Entwurf fortsetzen" if row and row.draft_id else "Einrichten / Bearbeiten")
        if row:
            self._qc_detail.configure(text="; ".join(row.issues) if row.issues else
                f"{row.assay_name} [{row.assay_key}] · {row.status}" + (f" · Fassung {row.profile_version_id}" if row.profile_id else " · Level und IST-Feld wählen; ein Gerät ist für das Profil optional."))

    def render_qc_configuration(self, state: QCConfigurationState) -> None:
        previous = self.selected_qc_configuration()
        identity = (previous.assay_key, previous.device_id, previous.profile_id, previous.draft_id) if previous else None
        self._qc_state = state
        self._qc_rows.clear()
        self._qc_tree.delete(*self._qc_tree.get_children())
        self._qc_new.configure(state="normal" if state.assays and not state.catalog_error else "disabled")
        selected = ""
        for index, row in enumerate(state.assay_rows):
            identifier = str(index)
            self._qc_rows[identifier] = row
            self._qc_tree.insert("", "end", iid=identifier, values=(f"{row.assay_name} [{row.assay_key}]",
                row.device_name if row.device_id else "Alle Geräte des Assays" if row.profile_id else "Noch kein Profil",
                row.profile_name if row.profile_id else "Noch kein Profil", row.level_count, row.status))
            if identity == (row.assay_key, row.device_id, row.profile_id, row.draft_id):
                selected = identifier
        if self._qc_rows:
            self._qc_tree.selection_set(selected or next(iter(self._qc_rows)))
        else:
            self._qc_detail.configure(text=state.catalog_error or "Keine aktiven Assays vorhanden. Regeln in der bestehenden Regelverwaltung einrichten.")
        self._select_qc_row()

    @property
    def edit_generation(self) -> int:
        return self._edit_generation

    def is_dirty(self) -> bool:
        return self._edit_generation > self._clean_generation

    def _bind_dirty_tracking(self) -> None:
        for variable in (
            self._var_watch_enabled,
            self._var_watch_input,
            self._var_watch_backup,
            self._var_watch_recursive,
            self._var_sqlite,
            self._var_device,
            self._var_operator_initials,
        ):
            variable.trace_add("write", self._on_field_edited)

    def _on_field_edited(self, *_args: object) -> None:
        if self._suppress_dirty:
            return
        self._edit_generation += 1

    def _apply_settings_values(self, settings: DesktopSettings) -> None:
        self._suppress_dirty = True
        try:
            self._var_watch_enabled.set(settings.watch_enabled)
            self._var_watch_input.set(settings.watch_input_path)
            self._var_watch_backup.set(settings.watch_backup_path)
            self._var_watch_recursive.set(settings.watch_recursive)
            self._var_sqlite.set(settings.sqlite_path)
            self._var_operator_initials.set(str(getattr(settings, "operator_initials", "") or ""))
        finally:
            self._suppress_dirty = False
        self._clean_generation = self._edit_generation

    def _render_devices(
        self,
        devices: Sequence[DeviceInventoryItem],
        *,
        preferred_device_id: str | None,
        preserve_selection: bool = False,
    ) -> None:
        labels = [item.choice_label for item in devices if item.active]
        self._device_combo.configure(values=labels)
        if preserve_selection:
            return
        self._suppress_dirty = True
        try:
            selected_label = ""
            if preferred_device_id:
                for item in devices:
                    if item.device_id == preferred_device_id:
                        selected_label = item.choice_label
                        break
            if not selected_label and labels:
                selected_label = labels[0]
            self._var_device.set(selected_label)
        finally:
            self._suppress_dirty = False

    def _render_timing(self, timing: WatchTimingSettings) -> None:
        self._lbl_timing.configure(
            text=(
                f"Watch-Timing (nur Anzeige): Scan alle {timing.scan_interval_s:.0f}s, "
                f"Stabilitätsfenster {timing.stable_window_s:.0f}s."
            )
        )

    def render_settings(
        self,
        settings: DesktopSettings,
        *,
        devices: Sequence[DeviceInventoryItem],
        timing: WatchTimingSettings,
    ) -> None:
        preserve_selection = self.is_dirty()
        self._render_devices(
            devices,
            preferred_device_id=settings.device_id,
            preserve_selection=preserve_selection,
        )
        self._render_timing(timing)
        if preserve_selection:
            return
        self._apply_settings_values(settings)

    def mark_saved_generation(self, generation: int) -> None:
        if generation > self._clean_generation:
            self._clean_generation = generation

    def collect_settings(self, *, device_id_map: dict[str, str]) -> DesktopSettings:
        device_label = self._var_device.get().strip()
        device_id = device_id_map.get(device_label, None)
        if device_id is None and "(" in device_label and device_label.endswith(")"):
            device_id = device_label.rsplit("(", 1)[-1].rstrip(")")
        return DesktopSettings(
            output_mode="sqlite",
            sqlite_path=self._var_sqlite.get().strip(),
            watch_enabled=bool(self._var_watch_enabled.get()),
            watch_input_path=self._var_watch_input.get().strip(),
            watch_backup_path=self._var_watch_backup.get().strip(),
            watch_recursive=bool(self._var_watch_recursive.get()),
            device_id=device_id or None,
            operator_initials=self._var_operator_initials.get().strip(),
        )

    def set_status_message(self, message: str) -> None:
        self._lbl_status.configure(text=message)

    def set_watch_input_path(self, path: str) -> None:
        self._var_watch_input.set(path)

    def set_watch_backup_path(self, path: str) -> None:
        self._var_watch_backup.set(path)

    def set_sqlite_path(self, path: str) -> None:
        self._var_sqlite.set(path)
