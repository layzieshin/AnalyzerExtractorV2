from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
import copy
from collections import Counter
from uuid import uuid4
from tkinter import messagebox, ttk

from interfaces.tk.desktop_theme import COLOR_CARD
from interfaces.tk.scroll_helpers import bind_mousewheel
from interfaces.tk.widgets.common import Card, OverflowScrollbar, ScrollableFrame, create_scrollable_tree
from src.application.api import DuplicateCandidateDetail, QCConfigurationState, QCLotDetail
from interfaces.tk.view_models import format_timestamp


def show_error_dialog(parent: tk.Misc, title: str, message: str, *, details: str = "") -> None:
    if details:
        show_details_dialog(parent, title, message, details)
        return
    messagebox.showerror(title, message, parent=parent)


def show_info_dialog(parent: tk.Misc, title: str, message: str) -> None:
    messagebox.showinfo(title, message, parent=parent)


def show_confirm_dialog(parent: tk.Misc, title: str, message: str) -> bool:
    return bool(messagebox.askyesno(title, message, parent=parent))


def show_details_dialog(parent: tk.Misc, title: str, message: str, details: str) -> None:
    dialog = tk.Toplevel(parent)
    dialog.title(title)
    dialog.transient(parent)
    dialog.grab_set()
    dialog.configure(background=COLOR_CARD)
    dialog.geometry("520x360")

    frame = ttk.Frame(dialog, padding=12)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text=message, wraplength=480).pack(anchor="w")
    text = tk.Text(frame, height=12, wrap="word")
    text.pack(fill="both", expand=True, pady=(8, 8))
    text.insert("1.0", details)
    text.configure(state="disabled")
    ttk.Button(frame, text="Schließen", command=dialog.destroy).pack(anchor="e")


def show_duplicate_comparison_dialog(parent: tk.Misc, detail: DuplicateCandidateDetail, *, technical_details: str):
    """Read the existing comparison projection; decisions stay in DiagnosticsView."""
    dialog = tk.Toplevel(parent)
    dialog.title("Duplikatvergleich")
    dialog.transient(parent)
    dialog.configure(background="#f3f6fa")
    dialog.geometry(f"{max(600, min(1080, parent.winfo_width() - 60))}x{max(400, min(700, parent.winfo_height() - 80))}")
    dialog.minsize(600, 380)
    outer = ttk.Frame(dialog, style="Content.TFrame", padding=12)
    outer.pack(fill="both", expand=True)
    footer = ttk.Frame(outer, style="Content.TFrame")
    footer.pack(side="bottom", fill="x", pady=(10, 0))
    close_button = ttk.Button(footer, text="Schließen", command=dialog.destroy, style="Diagnostics.TButton")
    close_button.pack(side="right")
    dialog.bind("<Escape>", lambda _event: dialog.destroy())
    scroll = ScrollableFrame(outer, autohide=True)
    scroll.pack(fill="both", expand=True)
    scroll.body.configure(style="Content.TFrame")
    scroll._canvas.configure(background="#f3f6fa", takefocus=True)
    card = Card(scroll.body, padding=16, rounded=True)
    card.pack(fill="x")
    body = card.body
    candidate = detail.candidate
    title = ttk.Label(body, text=candidate.assay_name or "Assayname fehlt", style="Diagnostics.Title.TLabel", wraplength=800)
    title.pack(anchor="w")
    status = {"pending": "Offen", "deleted": "Verworfen"}.get(candidate.status, candidate.status)
    metadata = f"Erkannt: {format_timestamp(candidate.detected_at)} · Status: {status}"
    source = str(candidate.candidate_meta.get("pdf_path") or "")
    if source:
        filename = source.rsplit("\\", 1)[-1].rsplit("/", 1)[-1]
        if len(filename) > 1 and filename[1] == ":":
            filename = filename[2:]
        metadata += f"\nQuelle: {filename}"
    context = ttk.Label(body, text=metadata, style="Diagnostics.Muted.TLabel", wraplength=800)
    context.pack(anchor="w", pady=(5, 8))
    rows = sorted(detail.field_comparison, key=lambda field: not field.changed)
    differences = sum(1 for field in rows if field.changed)
    ttk.Label(body, text=f"{differences} {'Unterschied' if differences == 1 else 'Unterschiede'} · {len(rows)} {'Feld' if len(rows) == 1 else 'Felder'} · Unterschiede zuerst",
        style="Diagnostics.Muted.TLabel").pack(anchor="w", pady=(0, 8))
    table_frame, tree = create_scrollable_tree(body, ("field", "selected", "candidate"),
        ("Feld", "Ausgewählte Fassung", "Kandidat"), height=max(1, min(9, len(rows))), autohide=True)
    tree.configure(style="Diagnostics.Treeview")
    tree.tag_configure("changed", background="#fff2d8", foreground="#75490f")
    for index, field in enumerate(rows):
        tree.insert("", "end", iid=str(index), values=(field.field_key,
            "" if field.existing_value is None else str(field.existing_value),
            "" if field.candidate_value is None else str(field.candidate_value)), tags=("changed",) if field.changed else ())
    if rows:
        table_frame.pack(fill="x", pady=(0, 10))
    else:
        ttk.Label(body, text="Keine Feldvergleichswerte verfügbar.", style="Diagnostics.Muted.TLabel").pack(anchor="w", pady=(0, 10))
    technical = ttk.Frame(body, style="CardInner.TFrame")
    text = tk.Text(technical, height=9, wrap="word", font=("Consolas", 9), borderwidth=1, relief="solid", highlightthickness=0)
    text.insert("1.0", technical_details)
    text.configure(state="disabled")
    text.pack(fill="both", expand=True)
    scrollbar = OverflowScrollbar(technical, orient="vertical", command=text.yview)
    text.configure(yscrollcommand=scrollbar.set)
    def toggle_technical():
        if technical.winfo_manager():
            technical.pack_forget()
            toggle.configure(text="Technische Details anzeigen")
        else:
            technical.pack(fill="x", pady=(8, 0))
            toggle.configure(text="Technische Details ausblenden")
    toggle = ttk.Button(body, text="Technische Details anzeigen", command=toggle_technical, style="Diagnostics.TButton")
    toggle.pack(anchor="w")
    def fit(event):
        width = max(1, event.width - 4)
        title.configure(wraplength=width)
        context.configure(wraplength=width)
        tree.configure(height=max(1, min(5 if width < 900 else 9, len(rows))))
        font = tkfont.Font(dialog, font=ttk.Style(dialog).lookup("Diagnostics.Treeview.Heading", "font"))
        minima = [font.measure(tree.heading(column, "text")) + 24 for column in ("field", "selected", "candidate")]
        extra = max(0, width - sum(minima))
        for index, column in enumerate(("field", "selected", "candidate")):
            value = minima[index] + int(extra * (.25 if index == 0 else .375))
            tree.column(column, width=value, minwidth=minima[index], stretch=True)
            tree.heading(column, anchor="w")
    body.bind("<Configure>", fit)
    for widget in (scroll._canvas, scroll.body, body, title, context, toggle):
        bind_mousewheel(widget, scroll._canvas)
    dialog._comparison_tree, dialog._technical_frame, dialog._technical_toggle = tree, technical, toggle
    dialog._comparison_context, dialog._comparison_close = context, close_button
    dialog.grab_set()
    (tree if rows else close_button).focus_set()
    return dialog


def _qc_form(parent: tk.Misc, title: str, *, width=820, height=650, autohide=False):
    """Scrollable form with a permanently reachable action row."""
    dialog = tk.Toplevel(parent)
    dialog.title(title)
    dialog.transient(parent)
    dialog.geometry(f"{min(width, dialog.winfo_screenwidth() - 80)}x{min(height, dialog.winfo_screenheight() - 100)}")
    dialog.minsize(560, 380)
    outer = ttk.Frame(dialog, padding=10)
    outer.pack(fill="both", expand=True)
    footer = ttk.Frame(outer)
    footer.pack(side="bottom", fill="x", pady=(10, 0))
    canvas = tk.Canvas(outer, highlightthickness=0)
    scrollbar = (OverflowScrollbar if autohide else ttk.Scrollbar)(outer, orient="vertical", command=canvas.yview)
    if not autohide:
        scrollbar.pack(side="right", fill="y")
    canvas.pack(fill="both", expand=True)
    canvas.configure(yscrollcommand=scrollbar.set)
    body = ttk.Frame(canvas, padding=(0, 0, 10, 0))
    body._qc_responsive = bool(autohide)
    window = canvas.create_window((0, 0), window=body, anchor="nw")
    body.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window, width=event.width))
    if autohide:
        canvas.configure(takefocus=True)
        bind_mousewheel(body, canvas)
        canvas.bind("<Prior>", lambda _event: canvas.yview_scroll(-1, "pages"))
        canvas.bind("<Next>", lambda _event: canvas.yview_scroll(1, "pages"))
    dialog.grab_set()
    return dialog, body, footer


def _qc_field(parent, label, value="", *, choices=None):
    row = ttk.Frame(parent)
    row.pack(fill="x", pady=3)
    responsive = bool(getattr(parent, "_qc_responsive", False))
    caption = ttk.Label(row, text=label, width=0 if responsive else 26)
    variable = tk.StringVar(value=str(value or ""))
    widget = (ttk.Combobox(row, textvariable=variable, values=tuple(choices), width=1 if responsive else 35) if choices is not None
              else ttk.Entry(row, textvariable=variable, width=1 if responsive else 35))
    if responsive:
        row.columnconfigure(1, weight=1)
        def fit(event):
            compact = event.width < 720
            row.columnconfigure(0, weight=1 if compact else 0, minsize=0 if compact else 300)
            caption.configure(wraplength=max(180, event.width - 10) if compact else 290)
            caption.grid(row=0, column=0, columnspan=2 if compact else 1, sticky="w", pady=(0, 4) if compact else 0)
            widget.grid(row=1 if compact else 0, column=0 if compact else 1, columnspan=2 if compact else 1, sticky="ew")
        row.bind("<Configure>", fit)
    else:
        caption.pack(side="left", anchor="n")
        widget.pack(side="left", fill="x", expand=True)
    return variable, widget


def _qc_actions(dialog, footer, submit):
    ttk.Button(footer, text="Abbrechen", command=dialog.destroy).pack(side="right")
    dialog.save_button = ttk.Button(footer, text="Speichern", style="Primary.TButton", command=submit)
    dialog.save_button.pack(side="right", padx=8)


def show_qc_inventory_dialog(parent, state: QCConfigurationState, *, initials: str, on_submit, initial_device_id=None, create_new=False):
    if initial_device_id is not None and not create_new and not any(row["device_id"] == initial_device_id for row in state.inventory["snapshot"]["devices"]):
        raise ValueError("Das ausgewählte Gerät ist nicht mehr im Bestand. Bitte neu laden.")
    dialog, body, footer = _qc_form(parent, "Geräte verwalten", autohide=True)
    snapshot = copy.deepcopy(state.inventory["snapshot"])
    devices = snapshot["devices"]
    ttk.Label(body, text="Geräte benennen und mindestens SN, LNR oder EVA erfassen. Altgeräte bleiben mit ihrer Kennung erhalten.", wraplength=700).pack(anchor="w", pady=(0, 8))
    tree_frame, tree = create_scrollable_tree(body, ("name", "state"), ("Gerät", "Erfassung"), height=max(1, min(5, len(devices))), autohide=True)
    tree_frame.pack(fill="x", pady=4)
    name, _ = _qc_field(body, "Gerätename")
    serial, _ = _qc_field(body, "Seriennummer (SN)")
    lnr, _ = _qc_field(body, "LNR")
    eva, _ = _qc_field(body, "EVA")
    active = tk.BooleanVar(value=True)
    default = tk.BooleanVar(value=False)
    ttk.Checkbutton(body, text="Gerät aktiv", variable=active).pack(anchor="w")
    ttk.Checkbutton(body, text="Als Standardgerät verwenden", variable=default).pack(anchor="w")
    operator, _ = _qc_field(body, "Operator-Initialen", initials)
    selected = [None]
    loading = [False]

    def stash():
        if selected[0] is not None:
            device = devices[selected[0]]
            device.update(display_name=name.get().strip(), serial_number=serial.get().strip(), lnr=lnr.get().strip(), eva=eva.get().strip(), active=active.get())
            if default.get():
                snapshot["default_device_id"] = device["device_id"]

    def render(index):
        loading[0] = True
        selected[0] = index
        device = devices[index]
        name.set(device.get("display_name", ""))
        serial.set(device.get("serial_number", ""))
        lnr.set(device.get("lnr", ""))
        eva.set(device.get("eva", ""))
        active.set(device.get("active", True))
        default.set(device["device_id"] == snapshot["default_device_id"])
        loading[0] = False

    def refresh():
        tree.delete(*tree.get_children())
        for index, device in enumerate(devices):
            incomplete = not (device.get("display_name") and any(device.get(key) for key in ("serial_number", "lnr", "eva")))
            label = device.get("display_name") or f"{device['device_id']} (Altgerät unvollständig)"
            tree.insert("", "end", iid=str(index), values=(label, "Unvollständig" if incomplete else "Erfasst"))

    def select(_event):
        if not loading[0] and tree.selection():
            stash()
            render(int(tree.selection()[0]))

    def add():
        stash()
        devices.append({"device_id": f"device-{uuid4().hex}", "display_name": "", "serial_number": "", "lnr": "", "eva": "", "active": True, "legacy": False})
        refresh()
        tree.selection_set(str(len(devices) - 1))
        render(len(devices) - 1)

    ttk.Button(body, text="Neues Gerät", command=add).pack(anchor="w", pady=6)
    tree.bind("<<TreeviewSelect>>", select)

    def submit():
        stash()
        on_submit(snapshot, operator.get(), dialog)

    _qc_actions(dialog, footer, submit)
    refresh()
    if create_new or not devices:
        add()
    else:
        index = next((index for index, row in enumerate(devices) if row["device_id"] == initial_device_id), 0)
        tree.selection_set(str(index))
        render(index)
    return dialog


def show_qc_profile_dialog(parent, state: QCConfigurationState, *, initials: str, assays, field_choices, on_submit, initial_version_id=None):
    if initial_version_id is not None and not any(row["version_id"] == initial_version_id for row in state.profiles):
        raise ValueError("Die ausgewählte Profilfassung ist nicht mehr aktuell. Bitte neu laden.")
    dialog, body, footer = _qc_form(parent, "Prüfprofile verwalten", width=940, height=790, autohide=True)
    profiles = {f"{row['snapshot']['name']} · Fassung {row['version_id']}": row for row in state.profiles}
    initial = next((label for label, row in profiles.items() if row["version_id"] == initial_version_id), "Neues Prüfprofil")
    choice, chooser = _qc_field(body, "Prüfprofil", initial, choices=("Neues Prüfprofil", *profiles))
    chooser.configure(state="readonly")
    ttk.Label(body, text="Jedes Speichern legt eine vollständige neue Fassung an. Frühere Namen, Kontrollen und Feldzuordnungen bleiben erhalten.", wraplength=800).pack(anchor="w", pady=6)
    name, _ = _qc_field(body, "Profilname")
    eligible = [row for row in state.inventory["snapshot"]["devices"] if row["active"] and not row["incomplete"]]
    name_counts = Counter(row["display_name"] for row in eligible)
    labels = [row["display_name"] if name_counts[row["display_name"]] == 1 else
              f"{row['display_name']} · {row.get('serial_number') or row.get('lnr') or row.get('eva')}" for row in eligible]
    label_counts = Counter(labels)
    available = {}
    for row, label in zip(eligible, labels):
        if label_counts[label] > 1:
            label = f"{label} · Kennung {row['device_id']}"
        # User-supplied names can also resemble an expanded display label.
        # Preserve every stable ID even in that secondary collision.
        while label in available:
            label = f"{label} · Kennung {row['device_id']}"
        available[label] = row["device_id"]
    device, device_widget = _qc_field(body, "Gerät", choices=available)
    device_widget.configure(state="readonly")
    assay_options = list(assays.items()) if isinstance(assays, dict) else list(assays)
    assay, assay_widget = _qc_field(body, "Assay", choices=[label for label, _ in assay_options])
    assay_widget.configure(state="readonly")
    def selected_assay_key():
        index = assay_widget.current()
        return assay_options[index][1] if 0 <= index < len(assay_options) else ""
    date_field, date_widget = _qc_field(body, "Messdatumsfeld", choices=())
    date_format, _ = _qc_field(body, "Datumsformat (z. B. %d.%m.%Y)", "%d.%m.%Y")
    time_field, time_widget = _qc_field(body, "Messzeitfeld (optional)", choices=())
    time_format, _ = _qc_field(body, "Zeitformat (optional, z. B. %H:%M:%S)")
    ttk.Label(body, text="Nur bei getrennt extrahierter Uhrzeit beide Zeitfelder ausdrücklich ausfüllen. Beispiele: %H:%M, %H:%M:%S oder %H%M. Das Datumsformat enthält dann keine Uhrzeit.", wraplength=800).pack(anchor="w", pady=4)
    grammar, grammar_widget = _qc_field(body, "Zahlenschreibweise", "Dezimalkomma (42,5)", choices=("Dezimalkomma (42,5)", "Dezimalpunkt (42.5)"))
    grammar_widget.configure(state="readonly")
    ttk.Label(body, text="Keine Tausendertrennzeichen. Leere, qualifizierte oder abweichende Werte werden als Klärfälle angezeigt.", wraplength=800).pack(anchor="w")
    unit, _ = _qc_field(body, "Einheit")
    grouping, grouping_widget = _qc_field(body, "Analysenlauf-Feld (optional)", choices=())
    ttk.Label(body, text="Leer: Kontrollen einer gespeicherten Assay-Messung bilden einen Lauf. Wiederholungen brauchen ein ausdrückliches Quellenfeld; ein Kalendertag ist keine Laufkennung.", wraplength=800).pack(anchor="w", pady=4)
    rili = tk.BooleanVar(value=False)
    relative = tk.BooleanVar(value=False)
    ttk.Checkbutton(body, text="Richtlinienbezug für diesen Assay anwendbar", variable=rili).pack(anchor="w")
    reference, _ = _qc_field(body, "Richtlinie / Referenzfassung")
    ttk.Checkbutton(body, text="Relative Abweichung auswerten", variable=relative).pack(anchor="w")
    relative_limit, _ = _qc_field(body, "Relative Grenze % (Punkt)")
    rule_frame = ttk.LabelFrame(body, text="Westgard: klassisch (classic-six-v1)", padding=6)
    rule_frame.pack(fill="x", pady=8)
    rule_vars = {}
    for index, rule in enumerate(("1_2s", "1_3s", "2_2s", "R_4s", "4_1s", "10x")):
        variable = tk.BooleanVar(value=True)
        rule_vars[rule] = variable
        ttk.Checkbutton(rule_frame, text=rule, variable=variable).grid(row=0, column=index, padx=4)
    ttk.Label(body, text="Das klassische 2-SD-Prüfsignal bleibt aktiv. Die Auswahl 1₂s steuert dessen Warnanzeige.", wraplength=800).pack(anchor="w")
    controls_frame, controls_tree = create_scrollable_tree(body, ("name", "ist", "soll", "min", "max"),
        ("Kontrolle", "IST-Feld", "SOLL-Feld", "MIN-Feld", "MAX-Feld"), height=4, autohide=True)
    controls_frame.pack(fill="x", pady=(10, 6))
    controls_tree.bind("<Configure>", lambda event: [controls_tree.column(key, width=max(85, (event.width - 4) // 5), minwidth=85, stretch=True)
        for key in ("name", "ist", "soll", "min", "max")])
    control_name, _ = _qc_field(body, "Kontrollname")
    field_vars, field_widgets = {}, []
    for key, label in (("IST", "Gemessener Wert (IST)"), ("SOLL", "Zielwert (SOLL)"), ("MIN", "Hersteller-Untergrenze (MIN)"), ("MAX", "Hersteller-Obergrenze (MAX)")):
        field_vars[key], widget = _qc_field(body, label, choices=())
        field_widgets.append(widget)
    unit_field, unit_field_widget = _qc_field(body, "Einheitenfeld (optional)", choices=())
    sd_value, _ = _qc_field(body, "Manuelle SD (optional, Punkt)")
    ttk.Label(body, text="MIN/MAX ergeben keine SD. Ohne SD bleiben Erfassungsvalidierung und QMMA nutzbar.", wraplength=800).pack(anchor="w", pady=4)
    operator, _ = _qc_field(body, "Operator-Initialen", initials)
    current = [None]
    selected_control = [0]
    controls = []

    def update_field_choices(_event=None):
        fields = tuple(field_choices.get(selected_assay_key(), ()))
        for widget in (date_widget, time_widget, grouping_widget, unit_field_widget, *field_widgets):
            widget.configure(values=("", *fields))

    def stash_control():
        if controls and selected_control[0] < len(controls):
            control = controls[selected_control[0]]
            control.update(name=control_name.get().strip(), fields={key: variable.get().strip() for key, variable in field_vars.items()},
                unit=unit.get().strip(), unit_field=unit_field.get().strip(),
                sd_reference={"kind": "manual", "value": sd_value.get().strip()} if sd_value.get().strip() else None)

    def render_control(index):
        selected_control[0] = index
        control = controls[index]
        control_name.set(control.get("name", ""))
        for key, variable in field_vars.items():
            variable.set(control.get("fields", {}).get(key, ""))
        unit_field.set(control.get("unit_field", ""))
        sd = control.get("sd_reference") or {}
        sd_value.set(sd.get("value", "") if sd.get("kind") == "manual" else "")

    def refresh_controls():
        controls_tree.delete(*controls_tree.get_children())
        for index, control in enumerate(controls):
            controls_tree.insert("", "end", iid=str(index), values=(control.get("name", ""), *(control.get("fields", {}).get(key, "") for key in ("IST", "SOLL", "MIN", "MAX"))))

    def select_control(_event):
        if controls_tree.selection():
            stash_control()
            render_control(int(controls_tree.selection()[0]))

    def add_control():
        stash_control()
        controls.append({"control_id": f"control-{uuid4().hex}", "name": "", "fields": {}})
        refresh_controls()
        controls_tree.selection_set(str(len(controls) - 1))
        render_control(len(controls) - 1)

    def load_profile(_event=None):
        record = profiles.get(choice.get())
        current[0] = record
        value = record["snapshot"] if record else {}
        name.set(value.get("name", ""))
        device.set(next((label for label, identifier in available.items() if identifier == value.get("device_id")), ""))
        key = value.get("assay_key", "")
        if key and key not in {identifier for _, identifier in assay_options}:
            assay_options.append(("Assayname fehlt", key))
            assay_widget.configure(values=[label for label, _ in assay_options])
        index = next((index for index, (_, identifier) in enumerate(assay_options) if identifier == key), -1)
        if index >= 0:
            assay_widget.current(index)
        else:
            assay.set("")
        date_field.set(value.get("measurement_date_field", ""))
        date_format.set(value.get("measurement_date_format", "%d.%m.%Y"))
        time_field.set(value.get("measurement_time_field", ""))
        time_format.set(value.get("measurement_time_format", ""))
        grammar.set("Dezimalpunkt (42.5)" if value.get("numeric_grammar") == "decimal_dot" else "Dezimalkomma (42,5)")
        unit.set(value.get("unit", ""))
        grouping.set(value.get("run_grouping_field", ""))
        rili.set(value.get("rili_applicable", False))
        relative.set(value.get("relative_enabled", False))
        relative_limit.set(value.get("relative_limit_percent") or "")
        reference.set(value.get("guideline_reference", ""))
        for rule, variable in rule_vars.items():
            variable.set(rule in value.get("enabled_rules", rule_vars))
        controls[:] = copy.deepcopy(value.get("controls") or [{"control_id": f"control-{uuid4().hex}", "name": "", "fields": {}}])
        refresh_controls()
        render_control(0)
        controls_tree.selection_set("0")
        update_field_choices()

    def submit():
        stash_control()
        record = current[0]
        value = {"profile_id": record["profile_id"] if record else f"profile-{uuid4().hex}", "name": name.get().strip(),
            "device_id": available.get(device.get(), ""), "assay_key": selected_assay_key(),
            "measurement_date_field": date_field.get().strip(), "measurement_date_format": date_format.get().strip(),
            "numeric_grammar": "decimal_dot" if grammar.get().startswith("Dezimalpunkt") else "decimal_comma", "unit": unit.get().strip(),
            "rili_applicable": rili.get(), "relative_enabled": relative.get(), "relative_limit_percent": relative_limit.get().strip(),
            "guideline_reference": reference.get().strip(), "qc_profile": "classic-six-v1", "enabled_rules": [rule for rule, variable in rule_vars.items() if variable.get()],
            "run_grouping_field": grouping.get().strip(), "controls": copy.deepcopy(controls)}
        if time_field.get().strip() or time_format.get().strip():
            value.update(measurement_time_field=time_field.get().strip(), measurement_time_format=time_format.get().strip())
        on_submit(value, record["version_id"] if record else 0, operator.get(), dialog)

    chooser.bind("<<ComboboxSelected>>", load_profile)
    assay_widget.bind("<<ComboboxSelected>>", update_field_choices)
    controls_tree.bind("<<TreeviewSelect>>", select_control)
    ttk.Button(body, text="Weitere Kontrolle", command=add_control).pack(anchor="w", pady=6)
    _qc_actions(dialog, footer, submit)
    load_profile()
    return dialog


def show_qc_lot_dialog(parent, detail: QCLotDetail, *, initials: str, on_submit):
    dialog, body, footer = _qc_form(parent, "Chargenreferenzen festlegen", height=560)
    ttk.Label(body, text=f"{detail.case.device_name} · {detail.case.assay_name or 'Assayname fehlt'} · Kit-Charge {detail.case.kit_lot}", wraplength=720).pack(anchor="w", pady=6)
    ttk.Label(body, text="SD ist optional. Eine bestätigte Referenzserie friert die vollständigen validierten Werte ein. Die Auswertung berechnet daraus Referenzmittelwert und Stichproben-SD; spätere Messwerte verändern diese Referenz nicht.", wraplength=720).pack(anchor="w", pady=6)
    choices = {}
    for control in detail.source_manifest["profile_snapshot"]["controls"]:
        identifier = control["control_id"]
        frame = ttk.LabelFrame(body, text=control["name"], padding=8)
        frame.pack(fill="x", pady=5)
        previous = detail.sd_references.get(identifier)
        default_reference = control.get("sd_reference") or {}
        options = ("Keine SD", "Manuelle SD", "Referenzserie bestätigen") + (("Bestehende Referenz behalten",) if previous else ())
        initial_mode = "Bestehende Referenz behalten" if previous else ("Manuelle SD" if default_reference.get("kind") == "manual" else "Keine SD")
        mode, widget = _qc_field(frame, "SD-Referenz", initial_mode, choices=options)
        widget.configure(state="readonly")
        value, _ = _qc_field(frame, "SD (Punkt, z. B. 1.2)", previous.get("value", "") if previous else default_reference.get("value", ""))
        count = sum(point["control_id"] == identifier for point in detail.source_manifest["included"])
        ttk.Label(frame, text=f"{count} eindeutig validierte Messwerte stehen als Referenzserie bereit.").pack(anchor="w")
        choices[identifier] = mode, value, previous
    operator, _ = _qc_field(body, "Operator-Initialen", initials)

    def submit():
        references = {}
        for identifier, (mode, value, previous) in choices.items():
            if mode.get() == "Manuelle SD":
                references[identifier] = {"kind": "manual", "value": value.get().strip()}
            elif mode.get() == "Referenzserie bestätigen":
                references[identifier] = {"kind": "confirmed_baseline", "confirmed": True}
            elif mode.get() == "Bestehende Referenz behalten":
                references[identifier] = previous
        on_submit(references, operator.get(), dialog)

    _qc_actions(dialog, footer, submit)
    return dialog


def show_qc_initials_dialog(parent, *, title, message, initials, on_submit, require_reason=False):
    dialog, body, footer = _qc_form(parent, title, width=680, height=400)
    ttk.Label(body, text=message, wraplength=600).pack(anchor="w", pady=8)
    operator, _ = _qc_field(body, "Operator-Initialen", initials)
    reason, _ = _qc_field(body, "Grund für Wiederöffnung") if require_reason else (None, None)
    _qc_actions(dialog, footer, lambda: on_submit(operator.get(), reason.get() if reason is not None else "", dialog))
    dialog.save_button.configure(text=title)
    return dialog


def show_qc_close_dialog(parent, detail: QCLotDetail, witnesses, *, initials, on_submit):
    dialog, body, footer = _qc_form(parent, "Charge mit PDF abschließen", width=760, height=440)
    ttk.Label(body, text=f"{detail.case.device_name} · {detail.case.assay_name or 'Assayname fehlt'} · Kit-Charge {detail.case.kit_lot}", wraplength=680).pack(anchor="w", pady=8)
    ttk.Label(body, text="Bitte die neuere validierte Folgecharge als Abschlussnachweis wählen. Die angezeigte Auswertung und ihr PDF bleiben anschließend unveränderlich erhalten. Menschliche Validierung und statistische Befunde bleiben getrennt.", wraplength=680).pack(anchor="w", pady=8)
    choices = {f"{index}. Kit-Charge {item.case.kit_lot} · Beginn {item.source_manifest['start_date']} · {item.source_manifest['population_count']} Messungen": item
               for index, item in enumerate(witnesses, 1)}
    choice, widget = _qc_field(body, "Neuere Folgecharge", choices=choices)
    widget.configure(state="readonly")
    operator, _ = _qc_field(body, "Operator-Initialen", initials)
    def submit():
        if choice.get() not in choices:
            messagebox.showerror("Folgecharge", "Bitte die neuere Folgecharge ausdrücklich auswählen.", parent=dialog)
            return
        on_submit(choices[choice.get()], operator.get(), dialog)
    _qc_actions(dialog, footer, submit)
    dialog.save_button.configure(text="Mit PDF abschließen")
    return dialog
