from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Sequence
from tkinter import ttk

from interfaces.tk.widgets.common import Card, SectionHeader
from src.application.api import DesktopSettings, DeviceInventoryItem, WatchTimingSettings


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
    ) -> None:
        super().__init__(master, style="Content.TFrame")
        self._on_save = on_save
        self._on_pick_watch_input = on_pick_watch_input
        self._on_pick_watch_backup = on_pick_watch_backup
        self._on_pick_sqlite = on_pick_sqlite
        self._on_reload_devices = on_reload_devices
        self._on_open_output_folder = on_open_output_folder
        self._edit_generation = 0
        self._clean_generation = 0
        self._suppress_dirty = False
        self._build()
        self._bind_dirty_tracking()

    def _build(self) -> None:
        card = Card(self)
        card.pack(fill="both", expand=True)
        body = card.body
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

        self._var_excel_after_validation = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            body,
            text="Excel nach Validierung erzeugen",
            variable=self._var_excel_after_validation,
        ).pack(anchor="w", pady=4)
        ttk.Label(
            body,
            text="SQLite wird immer gespeichert. Excel wird erst nach menschlicher Validierung freigegeben.",
            style="Muted.TLabel",
        ).pack(anchor="w")

        row_device = ttk.Frame(body, style="CardInner.TFrame")
        row_device.pack(fill="x", pady=4)
        ttk.Label(row_device, text="Gerät").pack(side="left")
        self._var_device = tk.StringVar()
        self._device_combo = ttk.Combobox(row_device, textvariable=self._var_device, state="readonly", width=40)
        self._device_combo.pack(side="left", padx=8)
        ttk.Button(row_device, text="Neu laden", command=self._on_reload_devices).pack(side="left")

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
        ttk.Button(body, text="Speichern", style="Primary.TButton", command=self._on_save).pack(anchor="w")

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
            self._var_excel_after_validation,
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
            self._var_excel_after_validation.set(settings.output_mode in {"both", "excel"})
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
        labels = [f"{item.display_name} ({item.device_id})" for item in devices if item.active]
        self._device_combo.configure(values=labels)
        if preserve_selection:
            return
        self._suppress_dirty = True
        try:
            selected_label = ""
            if preferred_device_id:
                for item in devices:
                    if item.device_id == preferred_device_id:
                        selected_label = f"{item.display_name} ({item.device_id})"
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
            output_mode="both" if bool(self._var_excel_after_validation.get()) else "sqlite",
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
