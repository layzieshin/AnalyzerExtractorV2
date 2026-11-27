from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from collections.abc import Callable, Sequence
from tkinter import ttk

from interfaces.tk.scroll_helpers import bind_mousewheel
from interfaces.tk.widgets.common import Card, ScrollableFrame, create_scrollable_tree
from src.application.api import DesktopSettings, DeviceInventoryItem, QCConfigurationState, WatchTimingSettings


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
        self._edit_generation = 0
        self._clean_generation = 0
        self._suppress_dirty = False
        self._layout_after_id = None
        self._compact = None
        self._configuration_store = ""
        self._profile_records = {}
        self._qc_editor_intent = None
        self._configure_styles()
        self._build()
        self._bind_dirty_tracking()

    def _configure_styles(self) -> None:
        style = ttk.Style(self)
        style.configure("Settings.TButton", font=("Segoe UI", 9), padding=(8, 5), background="#ffffff",
            foreground="#21486f", bordercolor="#cbdbea", lightcolor="#ffffff", darkcolor="#ffffff", borderwidth=1, relief="solid")
        style.map("Settings.TButton", background=[("active", "#eef5fd")], foreground=[("disabled", "#8b9bad")], bordercolor=[("focus", "#8bb2df")])
        style.configure("Settings.Primary.TButton", font=("Segoe UI", 9, "bold"), padding=(10, 5))
        style.configure("Ghost.Settings.TButton", bordercolor="#ffffff")
        style.configure("Settings.TEntry", padding=(8, 6), fieldbackground="#ffffff", bordercolor="#cbdbea",
            lightcolor="#ffffff", darkcolor="#ffffff", borderwidth=1, relief="solid")
        style.map("Settings.TEntry", bordercolor=[("focus", "#8bb2df")])
        style.configure("Settings.TCombobox", padding=(8, 5), arrowsize=14, bordercolor="#cbdbea", lightcolor="#ffffff", darkcolor="#ffffff")
        style.map("Settings.TCombobox", fieldbackground=[("disabled", "#edf1f5"), ("readonly", "#ffffff")],
            foreground=[("disabled", "#8b9bad"), ("readonly", "#16293c")])
        style.configure("Settings.Muted.TLabel", font=("Segoe UI", 9), background="#ffffff", foreground="#53677a")
        style.configure("Settings.Title.TLabel", font=("Segoe UI", 12, "bold"), background="#ffffff", foreground="#16293c")
        style.configure("Settings.TCheckbutton", font=("Segoe UI", 9), background="#ffffff")
        style.configure("Settings.TNotebook", background="#ffffff", borderwidth=0, relief="flat", bordercolor="#ffffff",
            lightcolor="#ffffff", darkcolor="#ffffff", tabmargins=(0, 0, 0, 0))
        if "Settings.TabUnderline" not in style.element_names():
            normal, active = tk.PhotoImage(master=self, width=2, height=2), tk.PhotoImage(master=self, width=2, height=2)
            normal.put("#ffffff", to=(0, 0, 2, 2))
            active.put("#175ba4", to=(0, 0, 2, 2))
            self.winfo_toplevel()._settings_tab_images = normal, active
            style.element_create("Settings.TabUnderline", "image", normal, ("selected", active), sticky="ew")
        style.layout("Settings.TNotebook.Tab", [("Notebook.padding", {"sticky": "nswe", "children": [
            ("Notebook.focus", {"side": "top", "sticky": "nswe", "children": [("Notebook.label", {"sticky": ""})]}),
            ("Settings.TabUnderline", {"side": "bottom", "sticky": "ew"}),
        ]})])
        style.configure("Settings.TNotebook.Tab", font=("Segoe UI", 10, "bold"), padding=(12, 8), expand=(0, 0, 0, 0), background="#ffffff")
        style.map("Settings.TNotebook.Tab", foreground=[("selected", "#175ba4"), ("!selected", "#53677a")],
            background=[("selected", "#ffffff"), ("!selected", "#ffffff")], expand=[("selected", (0, 0, 0, 0))],
            padding=[("selected", (12, 8, 12, 8)), ("!selected", (12, 8, 12, 8))])
        style.configure("Settings.Treeview", rowheight=36, font=("Segoe UI", 9))
        style.configure("Settings.Treeview.Heading", font=("Segoe UI", 9, "bold"), padding=(8, 6), background="#f0f5fb")

    def _build(self) -> None:
        self._page_header = ttk.Frame(self, style="Content.TFrame", padding=(12, 12, 12, 10))
        self._page_header.pack(fill="x")
        self._eyebrow = ttk.Label(self._page_header, text="WEITERE", style="Eyebrow.TLabel")
        self._eyebrow.pack(anchor="w")
        self._page_title = ttk.Label(self._page_header, text="Einstellungen", style="PageTitle.TLabel")
        self._page_title.pack(anchor="w", pady=(4, 2))
        self._page_subtitle = ttk.Label(self._page_header, text="Import, Geräte, Prüfprofile und Speicheroptionen an einem Ort.", style="PageSubtitle.TLabel")
        self._page_subtitle.pack(anchor="w")
        self._card = Card(self, padding=16, rounded=True)
        self._card.pack(fill="x", padx=12, pady=(0, 12))
        self._footer = ttk.Frame(self._card.body, style="CardInner.TFrame")
        self._footer.pack(side="bottom", fill="x", pady=(6, 0))
        self._tabs = ttk.Notebook(self._card.body, style="Settings.TNotebook")
        self._tabs.pack(fill="both", expand=True)
        self._panels = {}
        for key, label in (("import", "Import"), ("devices", "Geräte"), ("profiles", "Prüfprofile"), ("advanced", "Erweitert")):
            panel = ScrollableFrame(self._tabs, autohide=True)
            panel._canvas.configure(takefocus=True, height=1)
            self._tabs.add(panel, text=label)
            panel.body.bind("<Configure>", self._schedule_layout, add="+")
            self._panels[key] = panel
        self._settings_canvas = self._panels["import"]._canvas
        self._build_import_tab(self._panels["import"].body)
        self._build_devices_tab(self._panels["devices"].body)
        self._build_profiles_tab(self._panels["profiles"].body)
        self._build_advanced_tab(self._panels["advanced"].body)
        self._lbl_status = ttk.Label(self._footer, text="", style="Settings.Muted.TLabel", wraplength=640)
        actions = ttk.Frame(self._footer, style="CardInner.TFrame")
        actions.pack(fill="x")
        self._btn_save = ttk.Button(actions, text="Einstellungen speichern", style="Settings.Primary.TButton", command=self._on_save)
        self._btn_save.pack(side="left")
        self._btn_output = ttk.Button(actions, text="Ausgabeordner öffnen", style="Settings.TButton", command=self._on_open_output_folder)
        self._btn_output.pack(side="left", padx=(8, 0))
        for tree in (self._device_tree, self._profile_tree):
            tree.configure(style="Settings.Treeview")
            for column in tree.cget("columns"):
                tree.heading(column, anchor="w")
            tree.bind("<Configure>", self._schedule_layout)
        for panel in self._panels.values():
            self._bind_tab_scroll(panel, panel._canvas)
        self._tabs.bind("<<NotebookTabChanged>>", self._schedule_layout)
        for variable in (self._var_watch_enabled, self._var_watch_input, self._var_watch_backup,
                         self._var_watch_recursive, self._var_sqlite, self._var_device, self._var_operator_initials):
            variable.trace_add("write", lambda *_args: self._schedule_layout())
        self.bind("<Configure>", self._schedule_layout)
        self.bind("<Destroy>", self._cancel_layout)
        self._schedule_layout()

    def _build_import_tab(self, body: ttk.Frame) -> None:
        ttk.Label(body, text="Automatischer PDF-Import", style="Settings.Title.TLabel").pack(anchor="w", pady=(12, 4))
        ttk.Label(body, text="Änderungen werden erst mit „Einstellungen speichern“ übernommen.", style="Settings.Muted.TLabel").pack(anchor="w", pady=(0, 12))
        self._var_watch_enabled = tk.BooleanVar(value=False)
        ttk.Checkbutton(body, text="Automatischen Ordnerimport aktivieren", variable=self._var_watch_enabled, style="Settings.TCheckbutton").pack(anchor="w")
        self._path_fields = ttk.Frame(body, style="CardInner.TFrame")
        self._path_fields.pack(fill="x", pady=(12, 8))
        self._path_fields.columnconfigure(0, weight=1, uniform="paths")
        self._path_fields.columnconfigure(1, weight=1, uniform="paths")
        self._input_field = ttk.Frame(self._path_fields, style="CardInner.TFrame")
        self._backup_field = ttk.Frame(self._path_fields, style="CardInner.TFrame")
        self._var_watch_input, self._var_watch_backup = tk.StringVar(), tk.StringVar()
        ttk.Label(self._input_field, text="Eingabeordner", style="Settings.Muted.TLabel").pack(anchor="w", pady=(0, 5))
        self._input_entry = ttk.Entry(self._input_field, textvariable=self._var_watch_input, width=1, style="Settings.TEntry", font=("Segoe UI", 9))
        self._input_entry.pack(fill="x")
        self._input_pick = ttk.Button(self._input_field, text="Eingabeordner auswählen", command=self._on_pick_watch_input, style="Settings.TButton")
        self._input_pick.pack(anchor="w", pady=(8, 0))
        ttk.Label(self._backup_field, text="Archivordner", style="Settings.Muted.TLabel").pack(anchor="w", pady=(0, 5))
        self._backup_entry = ttk.Entry(self._backup_field, textvariable=self._var_watch_backup, width=1, style="Settings.TEntry", font=("Segoe UI", 9))
        self._backup_entry.pack(fill="x")
        backup_actions = ttk.Frame(self._backup_field, style="CardInner.TFrame")
        backup_actions.pack(fill="x", pady=(8, 5))
        self._backup_pick = ttk.Button(backup_actions, text="Archivordner auswählen", command=self._on_pick_watch_backup, style="Settings.TButton")
        self._backup_pick.pack(side="left")
        self._backup_clear = ttk.Button(backup_actions, text="Archivpfad leeren", command=lambda: self.set_watch_backup_path(""), style="Ghost.Settings.TButton")
        self._backup_clear.pack(side="left", padx=(8, 0))
        self._archive_hint = ttk.Label(self._backup_field, text="Bei automatischem Ordnerimport erforderlich.", style="Settings.Muted.TLabel", wraplength=420)
        self._archive_hint.pack(anchor="w")
        self._var_watch_recursive = tk.BooleanVar(value=False)
        ttk.Checkbutton(body, text="Unterordner einbeziehen", variable=self._var_watch_recursive, style="Settings.TCheckbutton").pack(anchor="w", pady=(4, 12))
        ttk.Label(body, text="Initialen als Vorschlag", style="Settings.Muted.TLabel").pack(anchor="w", pady=(0, 5))
        self._var_operator_initials = tk.StringVar()
        ttk.Entry(body, textvariable=self._var_operator_initials, width=16, style="Settings.TEntry", font=("Segoe UI", 9)).pack(anchor="w")
        ttk.Label(body, text="Vorschlag für die Ergebnis-Validierung. Keine Benutzerverwaltung.", style="Settings.Muted.TLabel").pack(anchor="w", pady=(5, 8))

    def _build_devices_tab(self, body: ttk.Frame) -> None:
        heading = ttk.Frame(body, style="CardInner.TFrame")
        heading.pack(fill="x", pady=(12, 10))
        heading.columnconfigure(0, weight=1)
        ttk.Label(heading, text="Geräte", style="Settings.Title.TLabel").grid(row=0, column=0, sticky="w")
        self._new_device = ttk.Button(heading, text="Neues Gerät", style="Settings.Primary.TButton", command=lambda: self._request_qc_editor("devices", create=True), state="disabled")
        self._new_device.grid(row=0, column=1, sticky="e")
        row = ttk.Frame(body, style="CardInner.TFrame")
        row.pack(fill="x", pady=(0, 10))
        row.columnconfigure(1, weight=1)
        ttk.Label(row, text="Importgerät", style="Settings.Muted.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self._var_device = tk.StringVar()
        self._device_combo = ttk.Combobox(row, textvariable=self._var_device, state="readonly", width=1, style="Settings.TCombobox", font=("Segoe UI", 9))
        self._device_combo.grid(row=0, column=1, sticky="nsew", padx=(0, 8))
        ttk.Button(row, text="Neu laden", command=self._on_reload_devices, style="Settings.TButton").grid(row=0, column=2, sticky="nsew")
        frame, self._device_tree = create_scrollable_tree(body, ("name", "identity", "state"), ("Gerät", "Seriennummer / LNR / EVA", "Status"), height=1, autohide=True)
        frame.pack(fill="x", pady=(0, 8))
        self._device_tree.bind("<<TreeviewSelect>>", lambda _event: self._update_qc_edit_buttons())
        self._device_tree.bind("<Double-1>", lambda _event: self._request_qc_editor("devices", create=False))
        actions = ttk.Frame(body, style="CardInner.TFrame")
        actions.pack(fill="x", pady=(4, 6))
        self._edit_device = ttk.Button(actions, text="Bearbeiten", command=lambda: self._request_qc_editor("devices", create=False), state="disabled", style="Settings.TButton")
        self._edit_device.pack(side="left")
        ttk.Button(actions, text="Altgeräte übernehmen", command=self._on_migrate_devices, style="Settings.TButton").pack(side="left", padx=8)
        self._device_status = ttk.Label(body, text="Gerätebestand wird geladen …", style="Settings.Muted.TLabel", wraplength=600)
        self._device_status.pack(anchor="w", pady=6)

    def _build_profiles_tab(self, body: ttk.Frame) -> None:
        heading = ttk.Frame(body, style="CardInner.TFrame")
        heading.pack(fill="x", pady=(12, 10))
        heading.columnconfigure(0, weight=1)
        ttk.Label(heading, text="Prüfprofile", style="Settings.Title.TLabel").grid(row=0, column=0, sticky="w")
        self._new_profile = ttk.Button(heading, text="Neues Profil", command=lambda: self._request_qc_editor("profiles", create=True), style="Settings.Primary.TButton", state="disabled")
        self._new_profile.grid(row=0, column=1, sticky="e")
        self._profile_hint = ttk.Label(body, text="Aktuelle Prüfprofile mit ihrer gespeicherten Fassung. Die Zuordnung bleibt an Assay und Gerät gebunden.", style="Settings.Muted.TLabel", wraplength=600)
        self._profile_hint.pack(anchor="w", pady=(0, 10))
        frame, self._profile_tree = create_scrollable_tree(body, ("name", "assay", "device", "version"), ("Profil", "Assay", "Gerät", "Fassung"), height=1, autohide=True)
        frame.pack(fill="x", pady=(0, 8))
        self._profile_tree.bind("<<TreeviewSelect>>", lambda _event: self._update_qc_edit_buttons())
        self._profile_tree.bind("<Double-1>", lambda _event: self._request_qc_editor("profiles", create=False))
        actions = ttk.Frame(body, style="CardInner.TFrame")
        actions.pack(fill="x")
        self._edit_profile = ttk.Button(actions, text="Bearbeiten", command=lambda: self._request_qc_editor("profiles", create=False), style="Settings.TButton", state="disabled")
        self._edit_profile.pack(side="left")
        ttk.Button(actions, text="Neu laden", command=self._on_reload_devices, style="Settings.TButton").pack(side="left", padx=8)
        self._profile_status = ttk.Label(body, text="Prüfprofile werden geladen …", style="Settings.Muted.TLabel", wraplength=600)
        self._profile_status.pack(anchor="w", pady=6)

    def _build_advanced_tab(self, body: ttk.Frame) -> None:
        ttk.Label(body, text="Erweitert", style="Settings.Title.TLabel").pack(anchor="w", pady=(12, 4))
        self._storage_hint = ttk.Label(body, text="Auswertung und Validierung verwenden denselben Ergebnisspeicher.", style="Settings.Muted.TLabel", wraplength=600)
        self._storage_hint.pack(anchor="w", pady=(0, 12))
        row = ttk.Frame(body, style="CardInner.TFrame")
        row.pack(fill="x", pady=(0, 8))
        row.columnconfigure(0, weight=1)
        ttk.Label(row, text="SQLite-Speicher", style="Settings.Muted.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 5))
        self._var_sqlite = tk.StringVar()
        self._sqlite_entry = ttk.Entry(row, textvariable=self._var_sqlite, width=1, style="Settings.TEntry", font=("Segoe UI", 9))
        self._sqlite_entry.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        self._sqlite_pick = ttk.Button(row, text="Datei auswählen", command=self._on_pick_sqlite, style="Settings.TButton")
        self._sqlite_pick.grid(row=1, column=1, sticky="nsew")
        self._workbook_hint = ttk.Label(body, text="Neue Ergebnisse werden nur in SQLite gespeichert. Vorhandene Arbeitsmappen werden nicht verändert.", style="Settings.Muted.TLabel", wraplength=600)
        self._workbook_hint.pack(anchor="w", pady=(4, 8))
        self._lbl_timing = ttk.Label(body, text="", style="Settings.Muted.TLabel", wraplength=640)
        self._lbl_timing.pack(anchor="w", pady=(8, 0))

    def _bind_tab_scroll(self, widget, canvas) -> None:
        if isinstance(widget, (ttk.Treeview, ttk.Combobox, ttk.Entry)):
            return
        bind_mousewheel(widget, canvas)
        for child in widget.winfo_children():
            self._bind_tab_scroll(child, canvas)

    def _schedule_layout(self, _event=None) -> None:
        if self._layout_after_id is None:
            self._layout_after_id = self.after_idle(self._layout_settings)

    def _cancel_layout(self, event) -> None:
        if event.widget is self and self._layout_after_id is not None:
            self.after_cancel(self._layout_after_id)
            self._layout_after_id = None

    def _layout_settings(self) -> None:
        self._layout_after_id = None
        width = self.winfo_width() - 56
        if width < 40:
            return
        compact = width < 900
        if compact != self._compact:
            self._page_header.configure(padding=(12, 4, 12, 6) if compact else (12, 12, 12, 10))
            self._page_title.configure(style="CompactPageTitle.TLabel" if compact else "PageTitle.TLabel")
            self._page_title.pack_configure(pady=(0, 2) if compact else (4, 2))
            if compact:
                self._eyebrow.pack_forget()
            else:
                self._eyebrow.pack(anchor="w", before=self._page_title)
            self._compact = compact
        self._input_field.grid(row=0, column=0, columnspan=2 if compact else 1, sticky="new", padx=0 if compact else (0, 8))
        self._backup_field.grid(row=1 if compact else 0, column=0 if compact else 1, columnspan=2 if compact else 1,
            sticky="new", padx=0 if compact else (8, 0), pady=(12, 0) if compact else 0)
        self._page_subtitle.configure(wraplength=width)
        self._archive_hint.configure(wraplength=max(180, width if compact else width // 2 - 16))
        for label in (self._profile_hint, self._storage_hint, self._workbook_hint, self._lbl_timing,
                      self._lbl_status, self._device_status, self._profile_status):
            label.configure(wraplength=width)
        current = self._tabs.nametowidget(self._tabs.select()) if self._tabs.select() else self._panels["import"]
        profile_tab = current is self._panels["profiles"]
        show_save = not profile_tab or self.is_dirty()
        if show_save:
            self._btn_save.configure(text="Allgemeine Änderungen speichern" if profile_tab else "Einstellungen speichern")
            self._btn_save.pack(side="left")
        else:
            self._btn_save.pack_forget()
        if current is self._panels["import"]:
            self._btn_output.pack(side="left", padx=(8, 0))
        else:
            self._btn_output.pack_forget()
        if show_save or self._lbl_status.cget("text"):
            self._footer.pack(side="bottom", fill="x", pady=(6, 0), before=self._tabs)
        else:
            self._footer.pack_forget()
        footer_height = self._footer.winfo_reqheight() + 6 if self._footer.winfo_manager() else 0
        tab_font = tkfont.Font(self, font=ttk.Style(self).lookup("Settings.TNotebook.Tab", "font"))
        available = self.winfo_height() - self._page_header.winfo_reqheight() - footer_height - 46 - tab_font.metrics("linespace") - 20
        self._tabs.configure(height=max(1, min(current.body.winfo_reqheight(), max(100, available))))
        heading_font = tkfont.Font(self, font=ttk.Style(self).lookup("Settings.Treeview.Heading", "font"))
        cell_font = tkfont.Font(self, font=ttk.Style(self).lookup("Settings.Treeview", "font"))
        for tree, flexible in ((self._device_tree, "name"), (self._profile_tree, "assay")):
            if tree.winfo_width() < 10:
                continue
            columns = tuple(tree.cget("columns"))
            values = [tree.item(row, "values") for row in tree.get_children()]
            minima = {column: heading_font.measure(tree.heading(column, "text")) + 24 for column in columns}
            desired = {column: max(minima[column], min(320, max((cell_font.measure(str(row[index])) + 24 for row in values), default=0)))
                for index, column in enumerate(columns)}
            extra = tree.winfo_width() - 4 - sum(desired.values())
            if extra > 0 and not compact:
                shares = (("name", .45), ("identity", .4)) if tree is self._device_tree else (("name", .3), ("assay", .35), ("device", .2))
                remaining = extra
                for column, share in shares:
                    growth = int(extra * share)
                    desired[column] += growth
                    remaining -= growth
                desired[columns[-1]] += remaining
            else:
                desired[flexible] = max(minima[flexible], desired[flexible] + extra)
            for column in columns:
                tree.column(column, width=desired[column], minwidth=desired[column], stretch=column == flexible)

    def render_qc_configuration(self, state: QCConfigurationState | None, *, assay_names: dict[str, str], error: str = "") -> None:
        selected_device, selected_profile = self._device_tree.selection(), self._profile_tree.selection()
        self.invalidate_qc_configuration(message=error or "Bestand wird geladen …")
        if state is None:
            return
        self._configuration_store = state.store_path
        devices = state.inventory["snapshot"]["devices"]
        device_names = {row["device_id"]: str(row.get("display_name") or "Gerätename fehlt") for row in devices}
        for row in devices:
            identity = " · ".join(str(row.get(key) or "") for key in ("serial_number", "lnr", "eva") if row.get(key)) or "Noch unvollständig"
            status = "Unvollständig" if row.get("incomplete") else "Aktiv" if row.get("active") else "Inaktiv"
            self._device_tree.insert("", "end", iid=row["device_id"], values=(device_names[row["device_id"]], identity, status))
        self._profile_records = {str(row["version_id"]): row for row in state.profiles}
        for identifier, row in self._profile_records.items():
            value = row["snapshot"]
            self._profile_tree.insert("", "end", iid=identifier, values=(value.get("name") or "Profilname fehlt",
                assay_names.get(str(value.get("assay_key") or "")) or "Assayname fehlt",
                device_names.get(value.get("device_id")) or "Gerätename fehlt", f"Fassung {row['version_id']}"))
        for tree, previous in ((self._device_tree, selected_device), (self._profile_tree, selected_profile)):
            tree.configure(height=max(1, min(6, len(tree.get_children()))))
            if previous and tree.exists(previous[0]):
                tree.selection_set(previous[0])
                tree.focus(previous[0])
        self._device_status.configure(text=f"{len(devices)} {'Gerät' if len(devices) == 1 else 'Geräte'} im ausgewählten Ergebnisspeicher.")
        self._profile_status.configure(text=error or f"{len(state.profiles)} {'Prüfprofil' if len(state.profiles) == 1 else 'Prüfprofile'} im ausgewählten Ergebnisspeicher.")
        self._update_qc_edit_buttons()
        self._schedule_layout()

    def invalidate_qc_configuration(self, *, message: str = "Ergebnisspeicher gewechselt. Bitte neu laden.") -> None:
        self._configuration_store = ""
        self._qc_editor_intent = None
        self._profile_records = {}
        for tree in (self._device_tree, self._profile_tree):
            tree.delete(*tree.get_children())
            tree.configure(height=1)
        self._device_status.configure(text=message)
        self._profile_status.configure(text=message)
        self._update_qc_edit_buttons()

    def _update_qc_edit_buttons(self) -> None:
        ready = bool(self._configuration_store)
        for button in (self._new_device, self._new_profile):
            button.configure(state="normal" if ready else "disabled")
        for button, tree in ((self._edit_device, self._device_tree), (self._edit_profile, self._profile_tree)):
            button.configure(state="normal" if ready and tree.selection() else "disabled")

    def _request_qc_editor(self, kind: str, *, create: bool) -> None:
        tree = self._device_tree if kind == "devices" else self._profile_tree
        selected = tree.selection()
        if not self._configuration_store or (not create and not selected):
            return
        self._qc_editor_intent = (kind, create, None if create else str(selected[0]), self._configuration_store)
        (self._on_manage_devices if kind == "devices" else self._on_manage_profiles)()

    def take_qc_editor_intent(self, kind: str) -> tuple[bool, str | None, str] | None:
        intent, self._qc_editor_intent = self._qc_editor_intent, None
        return (intent[1], intent[2], intent[3]) if intent is not None and intent[0] == kind else None

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
        if message:
            self._lbl_status.pack(anchor="w", pady=(0, 5), before=self._footer.winfo_children()[-1])
        else:
            self._lbl_status.pack_forget()
        self._schedule_layout()

    def set_watch_input_path(self, path: str) -> None:
        self._var_watch_input.set(path)

    def set_watch_backup_path(self, path: str) -> None:
        self._var_watch_backup.set(path)

    def set_sqlite_path(self, path: str) -> None:
        self._var_sqlite.set(path)
