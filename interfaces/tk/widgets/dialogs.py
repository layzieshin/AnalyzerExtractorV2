from __future__ import annotations

import tkinter as tk
import copy
import json
from decimal import Decimal
from uuid import uuid4
from tkinter import messagebox, ttk

from interfaces.tk.desktop_theme import COLOR_CARD
from interfaces.tk.widgets.common import create_scrollable_tree
from src.application.api import QCConfigurationState, QCLotDetail


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


def _qc_form(parent: tk.Misc, title: str, *, width=820, height=650):
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
    scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
    scrollbar.pack(side="right", fill="y")
    canvas.pack(fill="both", expand=True)
    canvas.configure(yscrollcommand=scrollbar.set)
    body = ttk.Frame(canvas, padding=(0, 0, 10, 0))
    window = canvas.create_window((0, 0), window=body, anchor="nw")
    body.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window, width=event.width))
    dialog.grab_set()
    return dialog, body, footer


def _qc_field(parent, label, value="", *, choices=None):
    row = ttk.Frame(parent)
    row.pack(fill="x", pady=3)
    ttk.Label(row, text=label, width=26, wraplength=190).pack(side="left", anchor="n")
    variable = tk.StringVar(value=str(value or ""))
    widget = (ttk.Combobox(row, textvariable=variable, values=tuple(choices), width=35) if choices is not None
              else ttk.Entry(row, textvariable=variable, width=35))
    widget.pack(side="left", fill="x", expand=True)
    return variable, widget


def _qc_actions(dialog, footer, submit):
    dialog._qc_busy = False
    dialog._qc_can_submit = True
    def cancel():
        if not dialog._qc_busy:
            callback = getattr(dialog, "on_cancel", None)
            if callback and callback() is False:
                return
            dialog.destroy()
    dialog.cancel_button = ttk.Button(footer, text="Abbrechen", command=cancel)
    dialog.cancel_button.pack(side="right")
    dialog.save_button = ttk.Button(footer, text="Speichern", style="Primary.TButton", command=submit)
    dialog.save_button.pack(side="right", padx=8)
    def busy(value):
        dialog._qc_busy = value
        dialog.save_button.configure(state="disabled" if value or not dialog._qc_can_submit else "normal")
        dialog.cancel_button.configure(state="disabled" if value else "normal")
    dialog.set_busy = busy
    dialog.protocol("WM_DELETE_WINDOW", cancel)
    dialog.bind("<Escape>", lambda _event: cancel())


def _qc_device_options(devices):
    counts = {}
    for row in devices:
        name = str(row.get("display_name") or "Gerät ohne Namen")
        counts[name.casefold()] = counts.get(name.casefold(), 0) + 1
    result = {}
    for row in devices:
        name = str(row.get("display_name") or "Gerät ohne Namen")
        if counts[name.casefold()] > 1:
            details = [str(row.get("serial_number") or ""), str(row["device_id"])[-6:]]
            name += " · " + " · ".join(value for value in details if value)
        result[name] = row["device_id"]
    return result


def show_qc_inventory_dialog(parent, state: QCConfigurationState, *, initials: str, on_submit, new_device: bool = False):
    dialog, body, footer = _qc_form(parent, "Geräte verwalten")
    snapshot = copy.deepcopy(state.inventory["snapshot"])
    devices = snapshot["devices"]
    ttk.Label(body, text="Ein unterscheidbarer Gerätename genügt. SN, LNR und EVA sind optional. Bestehende Geräte behalten ihre Kennung.", wraplength=700).pack(anchor="w", pady=(0, 8))
    tree = ttk.Treeview(body, columns=("name", "state"), show="headings", height=5, selectmode="browse")
    tree.heading("name", text="Gerät")
    tree.heading("state", text="Erfassung")
    tree.pack(fill="x", pady=4)
    name, _ = _qc_field(body, "Gerätename")
    serial, _ = _qc_field(body, "Seriennummer (optional)")
    lnr, _ = _qc_field(body, "LNR (optional)")
    eva, _ = _qc_field(body, "EVA (optional)")
    active = tk.BooleanVar(value=True)
    default = tk.BooleanVar(value=False)
    ttk.Checkbutton(body, text="Gerät aktiv", variable=active).pack(anchor="w")
    ttk.Checkbutton(body, text="Als Standardgerät verwenden", variable=default).pack(anchor="w")
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
            incomplete = not bool(device.get("display_name"))
            label = device.get("display_name") or f"{device['device_id']} (Altgerät unvollständig)"
            tree.insert("", "end", iid=str(index), values=(label, "Unvollständig" if incomplete else "Erfasst"))

    def select(_event):
        if not loading[0] and tree.selection():
            stash()
            render(int(tree.selection()[0]))

    def add():
        stash()
        devices.append({"device_id": f"device-{uuid4().hex}", "display_name": "", "serial_number": "", "lnr": "", "eva": "", "active": True, "legacy": False})
        if not any(row.get("display_name") and row.get("active", True) for row in devices[:-1]):
            snapshot["default_device_id"] = devices[-1]["device_id"]
        refresh()
        tree.selection_set(str(len(devices) - 1))
        render(len(devices) - 1)

    ttk.Button(body, text="Neues Gerät", command=add).pack(anchor="w", pady=6)
    tree.bind("<<TreeviewSelect>>", select)

    def submit():
        stash()
        on_submit(snapshot, "", dialog)

    _qc_actions(dialog, footer, submit)
    refresh()
    tree.selection_set("0")
    render(0)
    if new_device:
        add()
        dialog.title("Gerät hier anlegen")
    return dialog


def show_qc_profile_dialog(parent, state: QCConfigurationState, *, initials: str, assays, field_choices, on_submit,
                           selected_assay_key="", selected_profile_id="", editor=None, on_draft_change=None,
                           on_retain=None, on_discard=None, on_add_device=None):
    dialog, body, footer = _qc_form(parent, "Assays & QK – Profil einrichten", width=940, height=790)
    devices = {row["device_id"]: row for row in state.inventory["snapshot"]["devices"]}
    assay_options = list(assays.items()) if isinstance(assays, dict) else list(assays)
    assay_names = {key: label for label, key in assay_options}
    device_labels = {key: label for label, key in _qc_device_options(list(devices.values())).items()}
    profiles = {f"{row['snapshot']['name']} · {device_labels.get(row['snapshot']['device_id'], 'Alle Geräte des Assays')}"
                f" · {assay_names.get(row['snapshot']['assay_key'], 'Assay nicht aktiv')}"
                f" [{row['snapshot']['assay_key']}] · Fassung {row['version_id']}": row
                for row in state.profiles}
    choice, chooser = _qc_field(body, "Prüfprofil", "Neues Prüfprofil", choices=("Neues Prüfprofil", *profiles))
    chooser.configure(state="readonly")
    ttk.Label(body, text="Jedes Speichern legt eine neue Fassung an. Frühere Level, Zuordnungen und Nachweise bleiben erhalten.", wraplength=800).pack(anchor="w", pady=6)
    name, _ = _qc_field(body, "Profilname")
    available = _qc_device_options([row for row in devices.values() if row["active"] and row.get("display_name")])
    device, device_widget = _qc_field(body, "Gerät", choices=available)
    device_widget.configure(state="readonly")
    device_scope = tk.BooleanVar(value=False)
    scope_row = ttk.Frame(body)
    scope_row.pack(fill="x", pady=4)
    scope_widget = ttk.Checkbutton(scope_row, text="Nur für ein Gerät", variable=device_scope)
    scope_widget.pack(side="left")
    inline_button = ttk.Button(scope_row, text="Gerät hier anlegen", command=lambda: inline_device())
    inline_button.pack(side="left", padx=8)
    ttk.Label(body, text="Standard: Dieses Profil gilt für den Assay auf jedem Gerät. Die Messwerte werden immer je Gerät getrennt ausgewertet.", wraplength=800).pack(anchor="w", pady=4)
    ttk.Label(body, text="Die Gerätebindung bestehender Profile bleibt erhalten. Für eine andere Bindung: unter Assays & QK 'Weiteres Profil' als Kopie verwenden.", wraplength=800).pack(anchor="w", pady=2)
    # Stable assay keys are visible even when names are identical.
    assay, assay_widget = _qc_field(body, "Assay", choices=[f"{label} [{key}]" for label, key in assay_options])
    assay_widget.configure(state="readonly")
    notebook = ttk.Notebook(body)
    notebook.pack(fill="both", expand=True, pady=8)
    basic, advanced = ttk.Frame(notebook, padding=8), ttk.Frame(notebook, padding=8)
    notebook.add(basic, text="QK-Level & Grenzen")
    notebook.add(advanced, text="Erweitert")
    controls_tree = ttk.Treeview(basic, columns=("name", "min", "max", "soll", "ist"), show="headings", height=4, selectmode="browse")
    for key, label in zip(("name", "min", "max", "soll", "ist"), ("QK-Level", "MIN-Feld", "MAX-Feld", "SOLL-Feld", "IST-Feld")):
        controls_tree.heading(key, text=label)
        controls_tree.column(key, width=130)
    controls_tree.pack(fill="x", pady=(0, 6))
    control_name, _ = _qc_field(basic, "Levelname")
    field_vars, field_widgets = {}, []
    for key, label in (("IST", "Gemessener Wert (IST)"), ("SOLL", "Zielwert (SOLL)"), ("MIN", "Untergrenze (MIN)"), ("MAX", "Obergrenze (MAX)")):
        field_vars[key], widget = _qc_field(basic, label, choices=())
        widget.configure(state="readonly")
        field_widgets.append(widget)
    level_actions = ttk.Frame(basic)
    level_actions.pack(fill="x", pady=6)
    single_enabled = tk.BooleanVar(value=False)
    ttk.Checkbutton(basic, text="RiliBÄK-Grenzen vorhanden", variable=single_enabled).pack(anchor="w", pady=(8, 2))
    single_percent, single_widget = _qc_field(basic, "Erlaubte Abweichung %")
    ttk.Label(basic, text="Gemeinsam für alle Level dieses Geräte-/Assayprofils. Punkt oder Komma, ohne Tausendertrennzeichen. Neue Auswertungen zeigen SOLL × (1 ± Prozent / 100) als Einzelwertgrenzen in Kurve und PDF. Die QMMA-Grenze bleibt getrennt.", wraplength=800).pack(anchor="w", pady=4)
    feedback = ttk.Label(basic, text="", wraplength=800)
    feedback.pack(anchor="w", pady=6)
    ttk.Label(basic, text="Für den Anfang genügt das IST-Feld. SOLL und Herstellergrenzen können später ergänzt werden.", wraplength=800).pack(anchor="w", pady=4)
    unit, _ = _qc_field(basic, "Einheit für gemeinsame Auswertung")
    ttk.Label(basic, text="Kann zur Einrichtung leer bleiben. Für Mittelwert, SD und Vergleiche eine gemeinsame Einheit bestätigen oder unter Erweitert ausdrücklich dimensionslos wählen.", wraplength=800).pack(anchor="w", pady=4)

    date_field, date_widget = _qc_field(advanced, "Messdatumsfeld", choices=())
    date_format, _ = _qc_field(advanced, "Datumsformat (optional)")
    time_field, time_widget = _qc_field(advanced, "Messzeitfeld (optional)", choices=())
    time_format, _ = _qc_field(advanced, "Zeitformat (optional, z. B. %H:%M:%S)")
    ttk.Label(advanced, text="Leer bedeutet automatisch aus Datum/Uhrzeit im Bericht. Ein abweichendes bekanntes Format kann gezielt vorgegeben werden; fehlende Uhrzeit wird nicht erfunden.", wraplength=800).pack(anchor="w", pady=4)
    grammar, grammar_widget = _qc_field(advanced, "Zahlenschreibweise", "Automatisch", choices=("Automatisch", "Dezimalkomma (42,5)", "Dezimalpunkt (42.5)"))
    grammar_widget.configure(state="readonly")
    dimensionless = tk.BooleanVar(value=False)
    ttk.Checkbutton(advanced, text="Ausdrücklich dimensionslose Größe", variable=dimensionless).pack(anchor="w")
    grouping, grouping_widget = _qc_field(advanced, "Analysenlauf-Feld (optional)", choices=())
    ttk.Label(advanced, text="Leer: Kontrollen einer gespeicherten Assay-Messung bilden einen Lauf. Ein Kalendertag ist keine Laufkennung.", wraplength=800).pack(anchor="w", pady=4)
    legacy = ttk.LabelFrame(advanced, text="QMMA-Bestandskonfiguration", padding=6)
    legacy.pack(fill="x", pady=8)
    rili, relative = tk.BooleanVar(value=False), tk.BooleanVar(value=False)
    ttk.Checkbutton(legacy, text="Richtlinienbezug für QMMA anwendbar", variable=rili).pack(anchor="w")
    reference, _ = _qc_field(legacy, "Richtlinie / Referenzfassung")
    ttk.Checkbutton(legacy, text="Relative QMMA auswerten", variable=relative).pack(anchor="w")
    relative_limit, _ = _qc_field(legacy, "QMMA-Grenze % (Punkt)")
    ttk.Label(legacy, text="Bisherige Bedeutung und leere Bestandsgrenzen bleiben erhalten. Dieser Wert erzeugt keine Einzelwertlinien.", wraplength=800).pack(anchor="w")
    rule_frame = ttk.LabelFrame(advanced, text="Westgard: klassisch (classic-six-v1)", padding=6)
    rule_frame.pack(fill="x", pady=8)
    rule_vars = {}
    for index, rule in enumerate(("1_2s", "1_3s", "2_2s", "R_4s", "4_1s", "10x")):
        variable = tk.BooleanVar(value=False)
        rule_vars[rule] = variable
        ttk.Checkbutton(rule_frame, text=rule, variable=variable).grid(row=0, column=index, padx=4)
    ttk.Label(advanced, text="Westgard ist anfangs ausgeschaltet. Nur bewusst ausgewählte Regeln mit passender Referenz und belegter Messreihenfolge werden bewertet.", wraplength=800).pack(anchor="w")
    level_advanced = ttk.LabelFrame(advanced, text="Ausgewähltes QK-Level", padding=6)
    level_advanced.pack(fill="x", pady=8)
    control_unit, _ = _qc_field(level_advanced, "Level-Einheit")
    unit_field, unit_field_widget = _qc_field(level_advanced, "Einheitenfeld (optional)", choices=())
    sd_mode, sd_mode_widget = _qc_field(level_advanced, "SD-Referenz", "Keine SD", choices=("Keine SD", "Manuelle SD", "Bestehende Referenz behalten"))
    sd_mode_widget.configure(state="readonly")
    sd_value, _ = _qc_field(level_advanced, "Manuelle SD (optional, Punkt)")
    sd_reference, _ = _qc_field(level_advanced, "SD-Referenztext")
    ttk.Label(level_advanced, text="MIN/MAX und Prozentgrenzen ergeben keine SD. Ohne SD bleibt QMMA nutzbar. Bestehende Referenzen werden unverändert beibehalten.", wraplength=800).pack(anchor="w")
    current, selected_control, loading, prior_assay = [None], [None], [False], [""]
    controls, draft = [], [{}]
    editor_record = [copy.deepcopy(editor)]
    local_forms, baseline_form = {}, [None]
    dialog.qc_state = state

    def selected_key():
        index = assay_widget.current()
        return assay_options[index][1] if 0 <= index < len(assay_options) else ""

    def row_values(control):
        return (control.get("name", ""), *(control.get("fields", {}).get(key, "") for key in ("MIN", "MAX", "SOLL", "IST")))

    def mapping_feedback():
        problems = []
        fields = set(field_choices.get(selected_key(), ()))
        for control in controls:
            mapping = control.get("fields", {})
            invalid = [f"{key}: {mapping.get(key) or 'fehlt'}" for key in ("MIN", "MAX", "SOLL", "IST")
                       if (not mapping.get(key) and key == "IST") or (mapping.get(key) and mapping.get(key) not in fields)]
            assigned = [value for value in mapping.values() if value]
            if len(set(assigned)) != len(assigned):
                invalid.append("zugeordnete Felder müssen verschieden sein")
            if invalid:
                problems.append(f"{control.get('name') or 'Unbenanntes Level'}: {', '.join(invalid)}")
        return problems

    def update_field_choices():
        fields = tuple(field_choices.get(selected_key(), ()))
        for widget in field_widgets:
            widget.configure(values=("", *fields))
        for widget in (date_widget, time_widget, grouping_widget, unit_field_widget):
            widget.configure(values=("", *fields))
        feedback.configure(text="Feldzuordnung prüfen: " + "; ".join(mapping_feedback()) if mapping_feedback() else "IST zugeordnet; zusätzliche Bewertungen verwenden nur die dafür verfügbaren Angaben.")

    def stash_control():
        index = selected_control[0]
        if index is None or not 0 <= index < len(controls):
            return
        control = controls[index]
        control.update(name=control_name.get(), fields={key: variable.get() for key, variable in field_vars.items()},
                       unit=control_unit.get(), unit_field=unit_field.get())
        if sd_mode.get() == "Keine SD":
            control["sd_reference"] = None
        elif sd_mode.get() == "Manuelle SD":
            sd = copy.deepcopy(control.get("sd_reference") or {})
            sd.update(kind="manual", value=sd_value.get(), reference=sd_reference.get())
            control["sd_reference"] = sd
        if controls_tree.exists(str(index)):
            controls_tree.item(str(index), values=row_values(control))

    def render_control(index):
        loading[0] = True
        selected_control[0] = index
        control = controls[index]
        control_name.set(control.get("name", ""))
        for key, variable in field_vars.items():
            variable.set(control.get("fields", {}).get(key, ""))
        control_unit.set(control.get("unit", unit.get()))
        unit_field.set(control.get("unit_field", ""))
        sd = control.get("sd_reference") or {}
        sd_mode.set("Manuelle SD" if sd.get("kind") == "manual" else "Bestehende Referenz behalten" if sd else "Keine SD")
        sd_value.set(sd.get("value", "") if sd.get("kind") == "manual" else "")
        sd_reference.set(sd.get("reference", ""))
        loading[0] = False
        remove_button.configure(state="normal" if len(controls) > 1 else "disabled")
        update_field_choices()

    def refresh_controls(index=0):
        controls_tree.delete(*controls_tree.get_children())
        for number, control in enumerate(controls):
            controls_tree.insert("", "end", iid=str(number), values=row_values(control))
        render_control(index)
        controls_tree.selection_set(str(index))

    def select_control(_event):
        if not loading[0] and controls_tree.selection():
            index = int(controls_tree.selection()[0])
            if index != selected_control[0]:
                stash_control()
                render_control(index)

    def edit_control(*_args):
        if not loading[0]:
            stash_control()
            update_field_choices()
            remember()

    def add_control():
        stash_control()
        controls.append({"control_id": f"control-{uuid4().hex}", "name": f"Level {len(controls) + 1}", "fields": {}, "unit": unit.get()})
        refresh_controls(len(controls) - 1)
        remember()

    def remove_control():
        if len(controls) > 1:
            index = selected_control[0]
            controls.pop(index)
            refresh_controls(min(index, len(controls) - 1))
            remember()

    def change_assay(_event):
        key = selected_key()
        if current[0] or key == prior_assay[0]:
            return
        if prior_assay[0]:
            saved = capture_editor()
            saved["snapshot"]["assay_key"] = prior_assay[0]
            saved["editor_key"] = "new:" + prior_assay[0]
            local_forms[saved["editor_key"]] = saved
            if on_draft_change:
                on_draft_change(saved)
        load_profile(assay_override=key, stash=False)

    def load_profile(_event=None, *, assay_override="", stash=True):
        if stash and editor_record[0] and controls and not loading[0]:
            remember()
        loading[0] = True
        record = profiles.get(choice.get())
        current[0] = record
        key = record["snapshot"]["assay_key"] if record else (assay_override or selected_assay_key or (assay_options[0][1] if len(assay_options) == 1 else ""))
        editor_key = record["profile_id"] if record else "new:" + key
        stored = local_forms.get(editor_key)
        if stored is None and editor and editor.get("snapshot", {}).get("assay_key") == key and (
                record and editor.get("profile_id") == record["profile_id"] or not record and not editor.get("base_version_id")):
            stored = copy.deepcopy(editor)
        value = copy.deepcopy(stored["snapshot"] if stored else record["snapshot"] if record else {
            "profile_schema_version": 2, "profile_id": f"profile-{uuid4().hex}", "assay_key": key,
            "name": f"{assay_names.get(key) or 'Assay'} – QK", "numeric_grammar": "auto", "enabled_rules": []})
        editor_record[0] = {"editor_key": stored.get("editor_key", editor_key) if stored else editor_key, "draft_id": stored["draft_id"] if stored else "draft-" + uuid4().hex,
            "profile_id": value["profile_id"], "base_version_id": stored["base_version_id"] if stored else record["version_id"] if record else 0,
            "draft_version_id": stored.get("draft_version_id", 0) if stored else 0}
        draft[0] = value
        name.set(value.get("name", ""))
        identifier = value.get("device_id", "")
        if identifier and identifier not in available.values():
            available[f"{devices.get(identifier, {}).get('display_name') or 'Bisheriges Gerät'} (Gerät prüfen)"] = identifier
            device_widget.configure(values=tuple(available))
        device.set(next((label for label, key in available.items() if key == identifier), ""))
        key = value.get("assay_key", key)
        if key and key not in {identifier for _, identifier in assay_options}:
            assay_options.append(("Assay nicht aktiv", key))
            assay_widget.configure(values=[f"{label} [{identifier}]" for label, identifier in assay_options])
        index = next((index for index, (_, identifier) in enumerate(assay_options) if identifier == key), -1)
        assay_widget.current(index) if index >= 0 else assay.set("")
        prior_assay[0] = key
        device_scope.set(bool(identifier))
        scope_widget.configure(state="disabled" if record else "normal")
        device_widget.configure(state="disabled" if record or not identifier else "readonly")
        inline_button.configure(state="disabled" if record else "normal")
        assay_widget.configure(state="disabled" if record else "readonly")
        date_field.set(value.get("measurement_date_field", ""))
        modern = value.get("profile_schema_version") == 2
        dimensionless.set(value.get("dimensionless", False))
        date_format.set(value.get("measurement_date_format", "" if modern else "%d.%m.%Y"))
        time_field.set(value.get("measurement_time_field", ""))
        time_format.set(value.get("measurement_time_format", ""))
        grammar.set("Automatisch" if value.get("numeric_grammar") == "auto" else "Dezimalpunkt (42.5)" if value.get("numeric_grammar") == "decimal_dot" else "Dezimalkomma (42,5)")
        unit.set(value.get("unit", ""))
        grouping.set(value.get("run_grouping_field", ""))
        rili.set(value.get("rili_applicable", False))
        relative.set(value.get("relative_enabled", False))
        relative_limit.set(value.get("relative_limit_percent") if value.get("relative_limit_percent") is not None else "")
        reference.set(value.get("guideline_reference", ""))
        single_enabled.set(value.get("single_value_limits_enabled", False))
        single_percent.set(value.get("single_value_limit_percent") if value.get("single_value_limit_percent") is not None else "")
        for rule, variable in rule_vars.items():
            variable.set(rule in value.get("enabled_rules", ()))
        controls[:] = copy.deepcopy(value.get("controls") or [{"control_id": f"control-{uuid4().hex}", "name": "Level 1", "fields": {}}])
        selected_control[0] = None
        loading[0] = False
        refresh_controls(min(int(value.get("_ui_selected_control", 0)), len(controls) - 1))
        notebook.select(min(int(value.get("_ui_tab", 0)), 1))
        baseline_form[0] = {} if stored and not stored.get("draft_version_id") else capture_editor()["snapshot"]
        if record and editor_record[0]["base_version_id"] != record["version_id"]:
            feedback.configure(text="Die gespeicherte Profilfassung wurde inzwischen geändert. Ihr Entwurf bleibt erhalten; vor dem Veröffentlichen den Konflikt klären.")
        if not record:
            feedback.configure(text="Level benennen und IST wählen. Gerät, Datum, Grenzen und Westgard sind optionale Ergänzungen.")

    def capture_editor():
        stash_control()
        value = copy.deepcopy(draft[0])
        value.update(name=name.get(), device_id=available.get(device.get(), "") if device_scope.get() else "", assay_key=selected_key(),
            measurement_date_field=date_field.get(), measurement_date_format=date_format.get(),
            numeric_grammar="auto" if grammar.get() == "Automatisch" else "decimal_dot" if grammar.get().startswith("Dezimalpunkt") else "decimal_comma", unit=unit.get(),
            rili_applicable=rili.get(), relative_enabled=relative.get(), relative_limit_percent=relative_limit.get(),
            single_value_limits_enabled=single_enabled.get(), single_value_limit_percent=single_percent.get() if single_enabled.get() else None,
            guideline_reference=reference.get(), qc_profile="classic-six-v1", enabled_rules=[rule for rule, variable in rule_vars.items() if variable.get()],
            run_grouping_field=grouping.get(), controls=copy.deepcopy(controls), _ui_selected_control=selected_control[0] or 0,
            _ui_tab=notebook.index(notebook.select()))
        value.update(profile_schema_version=2, dimensionless=dimensionless.get())
        for key in ("measurement_time_field", "measurement_time_format"):
            value.pop(key, None)
        if time_field.get() or time_format.get():
            value.update(measurement_time_field=time_field.get(), measurement_time_format=time_format.get())
        return {**copy.deepcopy(editor_record[0]), "snapshot": value}

    def remember(*_args):
        if loading[0] or editor_record[0] is None:
            return
        value = capture_editor()
        local_forms[value["editor_key"]] = value
        if on_draft_change:
            on_draft_change(value)

    def inline_device():
        remember()
        if on_add_device:
            on_add_device(dialog, device_added)

    def device_added(updated_state, identifier):
        dialog.qc_state = updated_state
        available.clear()
        available.update(_qc_device_options([row for row in updated_state.inventory["snapshot"]["devices"] if row["active"] and row.get("display_name")]))
        device_widget.configure(values=tuple(available))
        device_scope.set(True)
        device.set(next((label for label, key in available.items() if key == identifier), ""))
        dialog.grab_set()
        remember()

    def submit():
        remember()
        problems = mapping_feedback()
        if problems:
            notebook.select(basic)
            feedback.configure(text="Feldzuordnung prüfen: " + "; ".join(problems))
            return
        if single_enabled.get() and not single_percent.get().strip():
            notebook.select(basic)
            feedback.configure(text="Bitte die erlaubte Abweichung in % für die Einzelwertgrenzen angeben.")
            return
        captured = capture_editor()
        value = captured["snapshot"]
        value["_draft_id"] = captured["draft_id"]
        on_submit(value, captured["base_version_id"], "", dialog)

    def cancel_editor():
        remember()
        captured = capture_editor()
        comparable = lambda value: {key: item for key, item in value.items() if not key.startswith("_ui_")}
        if not on_retain or comparable(captured["snapshot"]) == comparable(baseline_form[0] or {}):
            return True
        decision = tk.Toplevel(dialog)
        decision.title("Profilentwurf schließen")
        decision.transient(dialog)
        decision.grab_set()
        ttk.Label(decision, text="Ihre Eingaben sind noch nicht als Profil gespeichert.", padding=12).pack()
        actions = ttk.Frame(decision, padding=12)
        actions.pack(fill="x")
        def choose(action):
            decision.destroy()
            dialog.grab_set()
            action(captured, dialog)
        ttk.Button(actions, text="Entwurf behalten", command=lambda: choose(on_retain)).pack(side="left", padx=4)
        ttk.Button(actions, text="Verwerfen", command=lambda: choose(on_discard)).pack(side="left", padx=4)
        def back():
            decision.destroy()
            dialog.grab_set()
        ttk.Button(actions, text="Weiter bearbeiten", command=back).pack(side="left", padx=4)
        decision.protocol("WM_DELETE_WINDOW", back)
        return False

    def toggle_percent(*_args):
        single_widget.configure(state="normal" if single_enabled.get() else "disabled")

    chooser.bind("<<ComboboxSelected>>", load_profile)
    assay_widget.bind("<<ComboboxSelected>>", change_assay)
    controls_tree.bind("<<TreeviewSelect>>", select_control)
    ttk.Button(level_actions, text="Level hinzufügen", command=add_control).pack(side="left")
    remove_button = ttk.Button(level_actions, text="Level entfernen", command=remove_control)
    remove_button.pack(side="left", padx=8)
    for variable in (control_name, control_unit, unit_field, sd_mode, sd_value, sd_reference, *field_vars.values()):
        variable.trace_add("write", edit_control)
    single_enabled.trace_add("write", toggle_percent)
    def scope_changed(*_args):
        device_widget.configure(state="disabled" if current[0] or not device_scope.get() else "readonly")
        remember()
    device_scope.trace_add("write", scope_changed)
    for variable in (name, device, date_field, date_format, time_field, time_format, grammar, unit, grouping,
                     rili, relative, relative_limit, reference, single_enabled, single_percent, dimensionless, *rule_vars.values()):
        variable.trace_add("write", remember)
    _qc_actions(dialog, footer, submit)
    dialog.on_cancel = cancel_editor
    if selected_profile_id:
        choice.set(next((label for label, record in profiles.items() if record["profile_id"] == selected_profile_id), "Neues Prüfprofil"))
    load_profile()
    toggle_percent()
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


def show_qc_close_dialog(parent, detail: QCLotDetail, *, initials, on_submit, on_cancel=None):
    dialog, body, footer = _qc_form(parent, "Chargenabschluss prüfen", width=920, height=760)
    dialog.on_cancel = on_cancel
    dialog.prepared_preview = None
    operator = [None]
    def submit():
        if dialog.prepared_preview is not None and not dialog._qc_busy and not dialog.prepared_preview.block_reason:
            on_submit(dialog.prepared_preview, operator[0].get(), dialog)
    _qc_actions(dialog, footer, submit)
    dialog._qc_can_submit = False
    dialog.set_busy(False)
    dialog.cancel_button.configure(text="Später")
    dialog.save_button.configure(text="Charge abschließen und Bericht erzeugen")
    heading = ttk.Label(body, text="Nutzungsnachweis, alle QK-Level und PDF werden vorbereitet. Es wird noch nichts gespeichert.", wraplength=820)
    heading.pack(anchor="w", pady=8)
    def render_error(message):
        heading.configure(text=message)
    dialog.render_error = render_error
    def render(preview):
        for child in body.winfo_children():
            if child is not heading:
                child.destroy()
        heading.configure(text="Vorbereiteter Abschluss. Es wurde noch nichts gespeichert.")
        dialog.prepared_preview = preview
        model = preview.analysis.model
        source, profile = model["source_manifest"], model["source_manifest"]["profile_snapshot"]
        case = preview.detail.case
        def paragraph(value):
            ttk.Label(body, text=value, wraplength=820, justify="left").pack(anchor="w", pady=5)
        def unavailable(reason):
            return {"eligible_values_missing": "keine geeigneten Werte", "target_or_unit_conflict": "SOLL-/Einheitenkonflikt",
                "sd_reference_missing": "keine SD-Referenz", "sd_origin_unavailable": "SD-Herkunft nicht belegt",
                "sd_unit_incompatible": "SD gehört zu einer anderen Einheit", "sd_parameter_incompatible": "SD gehört zu einer anderen Messwertdefinition",
                "percentage_limits_reversed": "SOLL × (1 ± Prozent / 100) ergibt vertauschte Grenzen",
                "manufacturer_min_conflict": "unterschiedliche Hersteller-MIN-Werte", "manufacturer_max_conflict": "unterschiedliche Hersteller-MAX-Werte",
                "manufacturer_limits_reversed": "Hersteller-MIN ist größer als MAX", "not_configured": "nicht konfiguriert",
                "positive_target_required": "positiver SOLL erforderlich"}.get(reason, "Nachweis klären")
        paragraph(f"{case.device_name} · Gerät-ID {case.device_id} · {case.assay_name or 'Assayname fehlt'} · Assay-ID {case.assay_key} · exakte Kit-Charge: {case.kit_lot}")
        paragraph(case.close_reason)
        usage = json.loads(preview.chronology_json)
        own = next(row for row in usage["lots"] if row["kit_lot"] == case.kit_lot)
        paragraph("Belegte spätere Nutzungen: " + "; ".join(dict.fromkeys(f"{row['kit_lot']} · {row['interval']['display']} · Messung {row['run_id']}" for row in own["witnesses"])))
        unclear = [row["kit_lot"] for row in usage["lots"] if not row["last_usage_reliable"]]
        if unclear:
            paragraph("Weitere zeitlich ungeklärte Chargen: " + ", ".join(unclear) + ". Der konkrete spätere Nutzungsnachweis bestimmt keine global neueste Charge.")
        paragraph(f"Profil: {profile['name']} · Fassung {source['profile_version_id']} · Zeitraum ab {source['start_date'].split('T')[0] if source['start_date'] else 'nicht bestimmbar'} · {source['population_count']} Quellen · {model['counts']['analysis_included']} berücksichtigte / {model['counts']['analysis_excluded']} ausgeschlossene Kontrollwerte.")
        paragraph(f"Datumsfeld: {profile['measurement_date_field']} ({profile['measurement_date_format']}); Zeitfeld: {profile.get('measurement_time_field') or 'nicht zugeordnet (nur Datum)'}; Zahlenschreibweise: {profile['numeric_grammar']}.")
        for control in profile["controls"]:
            series = next(row for row in model["computed_series"] if row["control_id"] == control["control_id"])
            qmma, sd = series["qmma"], series["sd"]
            shown = f"{Decimal(qmma['value']):.6g} {series['unit']}" if qmma["available"] else "nicht verfügbar: " + unavailable(qmma["reason"])
            relative = f"{Decimal(qmma['relative_percent']):.6g} %" if qmma["relative_percent"] is not None else "nicht verfügbar: " + unavailable(qmma["relative_reason"])
            paragraph(f"Level {control['name']} · ID {control['control_id']} · " + ", ".join(f"{role}={field}" for role, field in control["fields"].items()) +
                f"\nQMMA {shown}; relativ {relative}; n={qmma['n']}; SD " + (f"{Decimal(sd['sd']):.6g}" if sd["available"] else "nicht verfügbar: " + unavailable(sd["reason"])))
            states = {"exceeded": "Grenze überschritten", "within_limit": "Innerhalb der Grenze", "not_applicable": "Nicht anwendbar",
                "not_configured": "Nicht konfiguriert", "unavailable": "Nicht verfügbar", "reject": "Ablehnungsbefund", "warning": "Warnung",
                "pass": "Kein Befund", "not_triggered": "Prüfsignal nicht ausgelöst", "disabled": "Nicht ausgewählt"}
            paragraph(f"QMMA-Grenze (relativ): {str(profile.get('relative_limit_percent')) + ' %' if profile.get('relative_limit_percent') is not None else 'nicht konfiguriert'}; QMMA-Bewertung: {states[qmma['limit_status']]}.")
            keys = set(series["point_keys"])
            findings = list(dict.fromkeys(f"{finding['rule']}: {states[finding['status']]}" for run in model["analytical_runs"]
                if keys.intersection(run["point_keys"]) for finding in run["findings"] if finding["rule"] in profile["enabled_rules"]))
            paragraph("Westgard: " + ("; ".join(findings) if findings else "keine Regeln ausgewählt oder keine geeigneten Messpunkte"))
            if "limits" in series:
                paragraph("; ".join(f"{label}: " + (f"{limit['lower']} bis {limit['upper']} {series['unit']}" if limit["available"] else "nicht verfügbar: " + unavailable(limit["reason"]))
                    for kind, label in (("manufacturer", "Herstellergrenzen"), ("single_value", "Einzelwert-Prozentgrenzen")) if (limit := series["limits"][kind])))
        paragraph("Quellen und Klärungsgründe (die menschliche Validierung bleibt von statistischen Befunden getrennt):")
        frame, tree = create_scrollable_tree(body, ("run", "level", "actual", "reason"),
            ("Messung", "Level", "IST", "Eignung / Klärungsgrund"), height=6)
        for key, width in (("run", 75), ("level", 140), ("actual", 90), ("reason", 460)):
            tree.column(key, width=width, minwidth=60)
        frame.pack(fill="x", pady=5)
        reason_labels = {"validation_missing": "Menschliche Validierung fehlt", "result_choice_pending": "Ergebnisauswahl offen",
            "measurement_date_invalid": "Messdatum unlesbar", "measurement_time_missing": "Extrahierte Messzeit fehlt",
            "measurement_time_invalid": "Extrahierte Messzeit ungültig", "manufacturer_min_conflict": "Unterschiedliche Hersteller-MIN-Werte",
            "manufacturer_max_conflict": "Unterschiedliche Hersteller-MAX-Werte", "manufacturer_limits_reversed": "Hersteller-MIN ist größer als MAX",
            "target_conflict": "Unterschiedliche SOLL-Werte", "unit_conflict": "Einheitenkonflikt", "target_or_unit_conflict": "SOLL-/Einheitenkonflikt"}
        for point in model["points"]:
            reasons = "; ".join(reason_labels.get(reason, f"{reason[:-8].upper()}-Wert unlesbar" if reason.endswith("_invalid") else "Nachweis klären") for reason in point["reasons"])
            alerts = [label + " überschritten" for kind, label in (("manufacturer", "Herstellergrenze"), ("single_value", "Einzelwert-Prozentgrenze"))
                if point.get("limit_findings", {}).get(kind, {}).get("status") == "exceeded"]
            if alerts:
                reasons = (reasons or "Berücksichtigt") + "; " + "; ".join(alerts)
            tree.insert("", "end", values=(point["run_id"], point["control_name"], point["raw"].get("IST"), reasons or "Berücksichtigt"))
        paragraph(f"Vorbereitete PDF: {preview.page_count} Seiten · Modell SHA-256 {preview.analysis.model_sha256} · PDF SHA-256 {preview.pdf_sha256}")
        if preview.block_reason:
            paragraph("Abschluss gesperrt: " + preview.block_reason)
        paragraph("Erst die Bestätigung speichert den Abschluss und genau diese PDF gemeinsam. Später oder Abbrechen verwirft die Vorbereitung ohne Chargenänderung.")
        operator[0], _ = _qc_field(body, "Operator-Initialen", initials)
        dialog._qc_can_submit = not bool(preview.block_reason)
        dialog.set_busy(False)
    dialog.render_preview = render
    return dialog
