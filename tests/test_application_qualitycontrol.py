"""P4 application and mapped Tk acceptance with synthetic stores."""
from __future__ import annotations

import copy
import json
import sqlite3
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import tkinter as tk
from tkinter import ttk

import pytest

from src.application.api import DesktopSettings, QualityControlApplicationError, create_desktop_services
from src.qualitycontrol.api import get_inventory, list_lots
from interfaces.tk.desktop_theme import configure_desktop_theme
from interfaces.tk.views.statistics_view import StatisticsView
from interfaces.tk.views.settings_view import SettingsView
from interfaces.tk.widgets import dialogs
from test_desktop_ui_v21 import _make_app_stub
from test_qualitycontrol_profiles_lots import fixture, add_run, payload


def services_for(root: Path, spec: dict):
    rules = root / "rules"
    if not (rules / "index.json").exists():
        write_synthetic_catalog(root, {"A": ("Assay A", ["DATE", "TIME", "ZEIT", "I1", "S1", "N1", "X1", "UNIT"])})
    services = create_desktop_services(root)
    services.settings.save(DesktopSettings("sqlite", spec["path"], "", "dev", operator_initials="RR"))
    return services


def write_synthetic_catalog(root: Path, assays):
    rules = root / "rules"
    rules.mkdir(exist_ok=True)
    index = []
    for key, (name, keys) in assays.items():
        filename = f"{key}.json"
        rule = {"assay_key": key, "assay_name": name, "lot_rule": {"regex": r"Lot: (\w+)"},
                "extract_rules": {"fields": [{"key": field, "regex": rf"{field}: (.+)", "required": True} for field in keys]},
                "excel_rules": {"excel_filename_template": "{assay_name}.xlsx", "sheetname_template": "{lot_id}"}}
        (rules / filename).write_text(json.dumps(rule), encoding="utf-8")
        index.append({"assay_key": key, "ruleset_file": filename})
    (rules / "index.json").write_text(json.dumps({"assays": index}), encoding="utf-8")


def test_assay_overview_keeps_duplicate_names_profiles_and_unconfigured_assays_separate(tmp_path):
    from src.qualitycontrol.api import MutationContext, save_profile
    spec, old = fixture(tmp_path, count=0)
    second = {**copy.deepcopy(old["snapshot"]), "profile_id": "p2"}
    save_profile(spec, second, expected_version_id=0, expected_inventory_version_id=1, context=MutationContext("RR", "second-profile"))
    keys = ["DATE", "I1", "S1", "N1", "X1"]
    write_synthetic_catalog(tmp_path, {"A": ("Gleicher Anzeigename", keys), "B": ("Gleicher Anzeigename", ["B1", "B2", "B3", "B4"])})
    services = services_for(tmp_path, spec)
    before = Path(spec["path"]).read_bytes()
    state = services.settings.get_qc_assay_configuration()
    assert len(state.assay_rows) == 3
    configured = [row for row in state.assay_rows if row.assay_key == "A"]
    assert {row.profile_id for row in configured} == {"p1", "p2"}
    assert all(row.status == "Eingerichtet" for row in configured)
    unconfigured = next(row for row in state.assay_rows if row.assay_key == "B")
    assert not unconfigured.profile_id and unconfigured.status == "QK noch nicht eingerichtet"
    assert len(state.assays) == 2 and state.field_choices["B"] == ("B1", "B2", "B3", "B4")
    assert Path(spec["path"]).read_bytes() == before


def test_settings_profile_save_uses_fresh_fields_and_never_falls_back_on_catalog_error(tmp_path):
    from src.qualitycontrol.api import get_profile, list_profiles
    spec, old = fixture(tmp_path, count=0)
    services = services_for(tmp_path, spec)
    state = services.settings.get_qc_assay_configuration()
    write_synthetic_catalog(tmp_path, {"A": ("Assay A", ["I1", "S1", "N1", "NEW_MAX"]), "B": ("Other", ["X1"])})
    before = Path(spec["path"]).read_bytes()
    with pytest.raises(QualityControlApplicationError, match="X1"):
        services.settings.save_qc_profile(state, old["snapshot"], expected_version_id=old["version_id"], operator_initials="RR", request_id="removed-current-field")
    current = services.settings.get_qc_assay_configuration()
    assert current.assay_rows[0].status == "Feldzuordnung prüfen" and "X1" in current.assay_rows[0].issues[0]
    (tmp_path / "rules" / "A.json").unlink()
    with pytest.raises(QualityControlApplicationError, match="nicht geladen"):
        services.settings.save_qc_profile(state, old["snapshot"], expected_version_id=old["version_id"], operator_initials="RR", request_id="missing-current-rule")
    assert get_profile(spec, old["version_id"]) == old and len(list_profiles(spec, include_history=True)) == 1
    assert Path(spec["path"]).read_bytes() == before


@pytest.mark.parametrize("damage", ["missing", "invalid"])
def test_catalog_failure_keeps_general_settings_readable_and_profile_save_blocked(tmp_path, damage):
    spec, old = fixture(tmp_path, count=0)
    services = services_for(tmp_path, spec)
    previous = services.settings.get_qc_assay_configuration()
    settings = services.settings.load()
    devices = services.settings.get_device_inventory()
    index = tmp_path / "rules" / "index.json"
    index.unlink() if damage == "missing" else index.write_text("{broken", encoding="utf-8")
    before = Path(spec["path"]).read_bytes()
    failed = services.settings.get_qc_assay_configuration()
    assert failed.catalog_error and "Regelkatalog" in failed.catalog_error
    assert not failed.assays and not failed.field_choices and not failed.assay_rows
    assert failed.profiles == previous.profiles
    app = _make_app_stub(current_view="settings", services=services)
    payload = app._load_view_payload("settings")
    assert payload["settings"] == settings and payload["devices"] == devices
    assert payload["qc_configuration"].catalog_error == failed.catalog_error
    with pytest.raises(QualityControlApplicationError, match="nicht geladen"):
        services.settings.save_qc_profile(previous, old["snapshot"], expected_version_id=old["version_id"],
            operator_initials="RR", request_id="broken-index-save")
    assert Path(spec["path"]).read_bytes() == before


def test_settings_mutations_reject_displayed_store_after_switch_with_same_ids(tmp_path: Path):
    first_root, second_root = tmp_path / "one", tmp_path / "two"
    first_root.mkdir()
    second_root.mkdir()
    first, _ = fixture(first_root)
    second, _ = fixture(second_root)
    services = services_for(tmp_path, first)
    state = services.settings.get_qc_configuration()
    services.settings.save(replace(services.settings.load(), sqlite_path=second["path"]))
    before = {path: (Path(path).read_bytes(), Path(path).stat().st_mtime_ns) for path in (first["path"], second["path"])}
    with pytest.raises(QualityControlApplicationError, match="gewechselt"):
        services.settings.save_qc_inventory(state, state.inventory["snapshot"], "RR", "stale-inventory")
    with pytest.raises(QualityControlApplicationError, match="gewechselt"):
        services.settings.save_qc_profile(state, state.profiles[0]["snapshot"], expected_version_id=1, operator_initials="RR", request_id="stale-profile")
    with pytest.raises(QualityControlApplicationError, match="gewechselt"):
        services.settings.migrate_qc_devices(state, "RR", "stale-migration")
    for path, expected in before.items():
        assert (Path(path).read_bytes(), Path(path).stat().st_mtime_ns) == expected


def test_results_lot_work_uses_bound_store_and_keeps_four_services(tmp_path: Path):
    first_root, second_root = tmp_path / "one", tmp_path / "two"
    first_root.mkdir()
    second_root.mkdir()
    first, _ = fixture(first_root)
    second, _ = fixture(second_root)
    services = services_for(tmp_path, first)
    case = services.results.list_qc_lots()[0]
    detail = services.results.get_qc_lot_detail(case)
    assert case.store_path == str(Path(first["path"]).resolve())
    services.settings.save(replace(services.settings.load(), sqlite_path=second["path"]))
    with pytest.raises(QualityControlApplicationError, match="gewechselt"):
        services.results.save_qc_lot(detail, {}, operator_initials="RR", request_id="stale-lot")
    assert not list_lots(first) and not list_lots(second)
    assert set(services.__dataclass_fields__) == {"extraction", "results", "rules", "settings"}


def test_normal_controller_work_revisions_optional_sd_and_profile_history(tmp_path: Path):
    spec, _ = fixture(tmp_path)
    services = services_for(tmp_path, spec)
    state = services.settings.get_qc_configuration()
    updated = copy.deepcopy(state.profiles[0]["snapshot"])
    updated["name"] = "Geändertes Profil"
    services.settings.save_qc_profile(state, updated, expected_version_id=1, operator_initials="RR", request_id="edit-profile")
    case = services.results.list_qc_lots()[0]
    detail = services.results.get_qc_lot_detail(case)
    stored = services.results.save_qc_lot(detail, {}, operator_initials="RR", request_id="open-controller")
    assert stored["state"] == "open" and stored["snapshot"]["sd_references"] == {}
    assert get_inventory(spec)["snapshot"]["devices"][0]["serial_number"] == "SYNTHETIC-SN"


def test_qc_assay_presentation_is_frozen_separately_and_changed_names_are_stale(tmp_path):
    import json
    from src.qualitycontrol.api import get_lot_sources
    spec, profile = fixture(tmp_path)
    rules = tmp_path / "rules"
    rules.mkdir()
    rule_path = rules / "A.json"
    rule_path.write_text(json.dumps({"assay_key": "A", "assay_name": "Vollständiger Katalogname"}), encoding="utf-8")
    (rules / "index.json").write_text(json.dumps({"assays": [{"assay_key": "A", "ruleset_file": "A.json"}]}), encoding="utf-8")
    add_run(spec, 3, lot="L2", data=payload("2026-02-01"))
    services = services_for(tmp_path, spec)
    detail = _open_controller_lot(services)
    original_source = get_lot_sources(spec, profile_version_id=profile["version_id"], kit_lot="L1")
    analysis = services.results.get_qc_analysis(detail)
    assert analysis.model["presentation"] == {"assay_name": "Vollständiger Katalogname", "run_assay_names": {"1": "Vollständiger Katalogname", "2": "Vollständiger Katalogname"}}
    assert analysis.model["source_manifest"] == original_source and analysis.model["sd_references"] == detail.sd_references
    preview = services.results.prepare_qc_lot_close(detail)
    rule_path.write_text(json.dumps({"assay_key": "A", "assay_name": "Neuer Katalogname"}), encoding="utf-8")
    with pytest.raises(QualityControlApplicationError, match="veraltet"):
        services.results.close_qc_lot(preview, operator_initials="RR", request_id="stale-name")
    assert analysis.model["presentation"]["assay_name"] == "Vollständiger Katalogname"
    assert get_lot_sources(spec, profile_version_id=profile["version_id"], kit_lot="L1") == original_source


def test_historical_id_arriving_after_setup_is_visible_draft_until_explicit_save(tmp_path: Path):
    spec, _ = fixture(tmp_path)
    services = services_for(tmp_path, spec)
    with sqlite3.connect(spec["path"]) as conn:
        conn.execute("UPDATE runs SET device_id='imported-later' WHERE id=1")
    before = Path(spec["path"]).read_bytes(), Path(spec["path"]).stat().st_mtime_ns
    state = services.settings.get_qc_configuration()
    draft = next(device for device in state.inventory["snapshot"]["devices"] if device["device_id"] == "imported-later")
    assert draft["incomplete"] and draft["display_name"] == ""
    assert all(device["device_id"] != "imported-later" for device in get_inventory(spec)["snapshot"]["devices"])
    assert (Path(spec["path"]).read_bytes(), Path(spec["path"]).stat().st_mtime_ns) == before
    draft.update(display_name="Historisches Gerät", eva="EVA-LATER")
    services.settings.save_qc_inventory(state, state.inventory["snapshot"], "RR", "complete-late-id")
    stored = next(device for device in get_inventory(spec)["snapshot"]["devices"] if device["device_id"] == "imported-later")
    assert not stored["incomplete"] and stored["eva"] == "EVA-LATER"
    with sqlite3.connect(spec["path"]) as conn:
        assert conn.execute("SELECT device_id FROM runs WHERE id=1").fetchone()[0] == "imported-later"


def test_source_selection_defers_io_and_discards_old_completion(tmp_path: Path):
    spec, _ = fixture(tmp_path)
    services = services_for(tmp_path, spec)
    add_run(spec, 3, lot="L2", data=payload("2026-02-01"))
    first, second = services.results.list_qc_lots()
    app = _make_app_stub(services=services)
    app._qc_source_generation, app._qc_source_latest = 0, None
    selection, rendered, io = [first], [], []
    app._views["statistics"] = SimpleNamespace(selected_qc_case=lambda: selection[0], selected_qc_profile_version=lambda: selection[0].profile_version_id,
        set_qc_loading=lambda: None, render_qc_detail=rendered.append, render_qc_analysis=lambda *_args: None)
    original = services.results.get_qc_lot_detail
    services.results.get_qc_lot_detail = lambda *args, **kwargs: io.append(args[0].kit_lot) or original(*args, **kwargs)
    app._load_qc_lot()
    assert io == []
    first_work = app._task_runner.submissions[0][1]()
    selection[0] = second
    app._load_qc_lot()
    app._task_runner.invoke_success(0, first_work)
    assert rendered == [] and len(app._task_runner.submissions) == 2
    app._task_runner.invoke_success()
    assert [detail.case.kit_lot for detail in rendered] == ["L2"]
    app._load_qc_lot()
    pending = app._task_runner.submissions[-1][1]()
    app._settings = replace(app._settings, sqlite_path=str(tmp_path / "other.sqlite3"))
    app._task_runner.invoke_success(result=pending)
    assert len(rendered) == 1


def test_configuration_rule_fields_load_in_worker_and_stale_dialog_is_discarded(tmp_path: Path, monkeypatch):
    from src.application.settings_controller import RuleSuiteController
    spec, _ = fixture(tmp_path)
    services = services_for(tmp_path, spec)
    io, shown = [], []
    monkeypatch.setattr(RuleSuiteController, "list_inventory", lambda _self, kind="all": io.append(("inventory", kind)) or [SimpleNamespace(assay_key="A", assay_name="Assay A")])
    monkeypatch.setattr(RuleSuiteController, "list_fields", lambda _self, key: io.append(key) or ["I1", "S1", "N1", "X1", "DATE"])
    app = _make_app_stub(services=services)
    app._qc_configuration_generation = 0
    monkeypatch.setattr(dialogs, "show_qc_profile_dialog", lambda *args, **kwargs: shown.append(kwargs))
    app._open_qc_configuration("profiles")
    assert io == [] and shown == []
    result = app._task_runner.submissions[-1][1]()
    assert io == [("inventory", "active"), "A"]
    app._settings = replace(app._settings, sqlite_path=str(tmp_path / "other.sqlite3"))
    app._task_runner.invoke_success(result=result)
    assert shown == []


def test_profile_configuration_callback_uses_active_fields_without_touching_archives(tmp_path: Path, monkeypatch):
    import json
    from src.ruleresolver.api import RuleResolverError
    spec, profile = fixture(tmp_path)
    rules = tmp_path / "rules"
    rules.mkdir()
    keys = ["DATE", "TIME", "I1", "S1", "N1", "X1", "UNIT"]
    rule = {"assay_key": "A", "assay_name": "Assay A", "lot_rule": {"regex": r"Lot: (\w+)"},
        "extract_rules": {"fields": [{"key": key, "regex": rf"{key}: (.+)", "required": True} for key in keys]},
        "excel_rules": {"excel_filename_template": "{assay_name}.xlsx", "sheetname_template": "{lot_id}"}}
    (rules / "A.json").write_text(json.dumps(rule), encoding="utf-8")
    index = {"assays": [{"assay_key": "A", "ruleset_file": "A.json"}]}
    (rules / "index.json").write_text(json.dumps(index), encoding="utf-8")
    archives = []
    for folder, filename, key in (("drafts", "old.draft.json", "(1111)"), ("inactive", "old.json", "(2222)"),
                                  ("history", "old.json", "(0437)"), ("trash", "old.json", "(5f03)")):
        path = rules / folder / filename
        path.parent.mkdir()
        path.write_text(json.dumps({**rule, "assay_key": key, "assay_name": f"Unindexed {folder}"}), encoding="utf-8")
        archives.append(path)
    before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in archives}
    services = services_for(tmp_path, spec)
    assert {row.kind for row in services.rules.list_inventory()} == {"active", "draft", "inactive", "history", "trash"}
    app = _make_app_stub(services=services)
    app._qc_configuration_generation = 0
    root, opened = _root(), []
    original = dialogs.show_qc_profile_dialog
    def show(_parent, state, **kwargs):
        dialog = original(root, state, **kwargs)
        opened.append((dialog, kwargs))
        return dialog
    def field(parent, label):
        children = parent.winfo_children()
        if any(isinstance(child, ttk.Label) and child.cget("text") == label for child in children):
            return next(child for child in children if isinstance(child, (ttk.Entry, ttk.Combobox)))
        return next((value for child in children if (value := field(child, label)) is not None), None)
    monkeypatch.setattr(dialogs, "show_qc_profile_dialog", show)
    try:
        app._open_qc_configuration("profiles")
        assert not opened
        payload = app._task_runner.submissions[-1][1]()
        assert payload[1] == (("Assay A", "A"),) and payload[2] == {"A": tuple(keys)}
        app._task_runner.invoke_success(result=payload)
        assert len(opened) == 1
        dialog, kwargs = opened[0]
        chooser = field(dialog, "Prüfprofil")
        chooser.set(next(label for label in chooser.cget("values") if label.endswith(f"· Fassung {profile['version_id']}")))
        chooser.event_generate("<<ComboboxSelected>>")
        root.update()
        assert dialog.winfo_viewable() and field(dialog, "Assay").get() == "Assay A [A]"
        assert field(dialog, "Messdatumsfeld").get() == "DATE"
        assert field(dialog, "Gemessener Wert (IST)").get() == "I1"
        assert "TIME" in field(dialog, "Messzeitfeld (optional)").cget("values")
        assert kwargs["field_choices"] == {"A": tuple(keys)}
        dialog.destroy()
        index["assays"][0]["ruleset_file"] = "missing-active.json"
        (rules / "index.json").write_text(json.dumps(index), encoding="utf-8")
        app._open_qc_configuration("profiles")
        broken = app._task_runner.submissions[-1][1]()
        assert broken[2]["A"] == () and "nicht verfügbar" in broken[0].assay_rows[0].issues[0]
        app._task_runner.invoke_success(result=broken)
        assert len(opened) == 2
        assert {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in archives} == before
    finally:
        root.destroy()


def _root():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk unavailable: {exc}")
    root.geometry("960x620")
    configure_desktop_theme(root)
    return root


def qc_widget(parent, kind, *, label=None, text=None):
    children = parent.winfo_children()
    if label is not None and any(isinstance(child, ttk.Label) and child.cget("text") == label for child in children):
        return next(child for child in children if isinstance(child, kind))
    for child in children:
        if label is None and isinstance(child, kind) and (text is None or child.cget("text") == text):
            return child
        found = qc_widget(child, kind, label=label, text=text)
        if found is not None:
            return found
    return None


def edit_qc_field(dialog, label, value):
    widget = qc_widget(dialog, (ttk.Entry, ttk.Combobox), label=label)
    if isinstance(widget, ttk.Combobox):
        widget.set(value)
    else:
        widget.delete(0, "end")
        widget.insert(0, value)
    return widget


@pytest.mark.parametrize("damage", ["missing", "invalid"])
def test_catalog_error_clears_stale_qc_rows_and_keeps_general_settings_and_devices_visible(tmp_path, monkeypatch, damage):
    spec, old = fixture(tmp_path, count=0)
    services = services_for(tmp_path, spec)
    state = services.settings.get_qc_assay_configuration()
    settings = services.settings.load()
    root, opened = _root(), []
    app = _make_app_stub(current_view="settings", services=services)
    app._validation_badge = None
    app._qc_configuration_generation = 0
    try:
        view = SettingsView(root, on_save=lambda: None, on_pick_watch_input=lambda: None, on_pick_watch_backup=lambda: None,
            on_pick_sqlite=lambda: None, on_reload_devices=lambda: None, on_open_output_folder=lambda: None)
        app._views["settings"] = view
        view.pack(fill="both", expand=True)
        view.render_settings(settings, devices=services.settings.get_device_inventory().devices, timing=services.settings.get_watch_timing())
        view.render_qc_configuration(state)
        assert view._qc_tree.get_children() and str(view._qc_new.cget("state")) == "normal"
        index = tmp_path / "rules" / "index.json"
        index.unlink() if damage == "missing" else index.write_text("{broken", encoding="utf-8")
        app._apply_view_payload("settings", app._load_view_payload("settings"))
        root.update()
        assert view._var_sqlite.get() == settings.sqlite_path
        assert view._var_operator_initials.get() == settings.operator_initials
        assert view._device_combo.cget("values")
        assert not view._qc_tree.get_children() and view.selected_qc_configuration() is None
        assert "Regelkatalog konnte nicht geladen" in view._qc_detail.cget("text")
        assert str(view._qc_edit.cget("state")) == str(view._qc_new.cget("state")) == "disabled"
        assert view._btn_save.winfo_viewable()
        app._reload_devices()
        app._task_runner.invoke_success()
        assert not view._qc_tree.get_children() and view._device_combo.cget("values")
        monkeypatch.setattr(dialogs, "show_qc_profile_dialog", lambda *args, **kwargs: opened.append(kwargs))
        app._open_qc_configuration("profiles")
        app._task_runner.invoke_success()
        assert not opened and app._error_shown
        before = Path(spec["path"]).read_bytes()
        with pytest.raises(QualityControlApplicationError, match="nicht geladen"):
            services.settings.save_qc_profile(state, old["snapshot"], expected_version_id=old["version_id"], operator_initials="RR", request_id="native-broken-index-save")
        assert Path(spec["path"]).read_bytes() == before
    finally:
        root.destroy()


def test_profile_qk_editor_roundtrip_preserves_advanced_controls_and_separates_percent(tmp_path):
    from src.qualitycontrol.api import MutationContext, get_profile, save_profile
    spec, first = fixture(tmp_path, count=0)
    value = copy.deepcopy(first["snapshot"])
    value.update(measurement_time_field="TIME", measurement_time_format="%H:%M", numeric_grammar="decimal_comma",
                 guideline_reference="SYNTHETIC-REFERENCE", relative_limit_percent=None, enabled_rules=["1_3s"], run_grouping_field="RUN")
    value["controls"][0].update(unit="U1", sd_reference={"kind": "manual", "value": "2.5", "reference": "SYNTHETIC-ORIGIN"})
    value["controls"].append({"control_id": "c2", "name": "Pcq2", "fields": {"MIN": "N2", "MAX": "X2", "SOLL": "S2", "IST": "I2"},
                              "unit": "U2", "unit_field": "UNIT2", "sd_reference": {"kind": "confirmed_baseline", "confirmed": True}})
    old = save_profile(spec, value, expected_version_id=first["version_id"], expected_inventory_version_id=1, context=MutationContext("RR", "advanced-profile"))
    keys = ["DATE", "TIME", "RUN", "UNIT", "UNIT2", "I1", "S1", "N1", "X1", "I2", "S2", "N2", "X2"]
    write_synthetic_catalog(tmp_path, {"A": ("Assay A", keys)})
    services = services_for(tmp_path, spec)
    state = services.settings.get_qc_assay_configuration()
    root, submitted = _root(), []
    try:
        dialog = dialogs.show_qc_profile_dialog(root, state, initials="RR", assays=state.assays, field_choices=state.field_choices,
            selected_profile_id=old["profile_id"], on_submit=lambda *args: submitted.append(args))
        root.update()
        assert str(qc_widget(dialog, ttk.Combobox, label="Gerät").cget("state")) == "disabled"
        assert str(qc_widget(dialog, ttk.Combobox, label="Assay").cget("state")) == "disabled"
        for label in ("Untergrenze (MIN)", "Obergrenze (MAX)", "Zielwert (SOLL)", "Gemessener Wert (IST)"):
            widget = qc_widget(dialog, ttk.Combobox, label=label)
            assert str(widget.cget("state")) == "readonly" and tuple(widget.cget("values")) == tuple(keys)
        percent = qc_widget(dialog, ttk.Entry, label="Erlaubte Abweichung %")
        assert str(percent.cget("state")) == "disabled" and percent.get() == ""
        qc_widget(dialog, ttk.Checkbutton, text="RiliBÄK-Grenzen vorhanden").invoke()
        assert str(percent.cget("state")) == "normal"
        dialog.save_button.invoke()
        assert not submitted
        edit_qc_field(dialog, "Erlaubte Abweichung %", "12,5")
        edit_qc_field(dialog, "Levelname", "Pcq1")
        tree = qc_widget(dialog, ttk.Treeview)
        assert tree.item("0", "values")[0] == "Pcq1"
        tree.selection_set("1")
        root.update()
        assert qc_widget(dialog, ttk.Entry, label="Level-Einheit").get() == "U2"
        assert qc_widget(dialog, ttk.Combobox, label="SD-Referenz").get() == "Bestehende Referenz behalten"
        dialog.save_button.invoke()
        snapshot, expected, initials, _ = submitted[-1]
        saved = services.settings.save_qc_profile(state, snapshot, expected_version_id=expected, operator_initials=initials, request_id="roundtrip-edit")
        expected_snapshot = copy.deepcopy(old["snapshot"])
        expected_snapshot["controls"][0]["name"] = "Pcq1"
        expected_snapshot.update(single_value_limits_enabled=True, single_value_limit_percent="12.5")
        assert saved["snapshot"] == expected_snapshot
        assert get_profile(spec, old["version_id"]) == old
        qc_widget(dialog, ttk.Checkbutton, text="RiliBÄK-Grenzen vorhanden").invoke()
        assert str(percent.cget("state")) == "disabled"
        dialog.save_button.invoke()
        assert submitted[-1][0]["single_value_limit_percent"] is None
    finally:
        root.destroy()


def test_level_add_remove_and_rename_keep_ids_and_previous_revision(tmp_path):
    from src.qualitycontrol.api import get_profile
    spec, old = fixture(tmp_path, count=0)
    services = services_for(tmp_path, spec)
    state = services.settings.get_qc_assay_configuration()
    root, submitted = _root(), []
    try:
        dialog = dialogs.show_qc_profile_dialog(root, state, initials="RR", assays=state.assays, field_choices=state.field_choices,
            selected_profile_id=old["profile_id"], on_submit=lambda *args: submitted.append(args))
        qc_widget(dialog, ttk.Button, text="Level hinzufügen").invoke()
        edit_qc_field(dialog, "Levelname", "Freier Levelname")
        for label, key in (("Untergrenze (MIN)", "N1"), ("Obergrenze (MAX)", "X1"), ("Zielwert (SOLL)", "S1"), ("Gemessener Wert (IST)", "I1")):
            edit_qc_field(dialog, label, key)
        dialog.save_button.invoke()
        added = submitted[-1][0]
        assert added["controls"][0]["control_id"] == "c1"
        new_id = added["controls"][1]["control_id"]
        assert new_id != "c1" and added["controls"][1]["name"] == "Freier Levelname"
        tree = qc_widget(dialog, ttk.Treeview)
        tree.selection_set("0")
        root.update()
        qc_widget(dialog, ttk.Button, text="Level entfernen").invoke()
        root.update()
        dialog.save_button.invoke()
        snapshot, expected, initials, _ = submitted[-1]
        assert len(snapshot["controls"]) == 1 and snapshot["controls"][0]["control_id"] == new_id
        saved = services.settings.save_qc_profile(state, snapshot, expected_version_id=expected, operator_initials=initials, request_id="remove-old-level")
        assert saved["predecessor_id"] == old["version_id"] and get_profile(spec, old["version_id"]) == old
        assert str(qc_widget(dialog, ttk.Button, text="Level entfernen").cget("state")) == "disabled"
    finally:
        root.destroy()


def test_new_profile_assay_change_clears_foreign_mappings_and_old_invalid_key_stays_visible(tmp_path):
    spec, old = fixture(tmp_path, count=0)
    services = services_for(tmp_path, spec)
    state = services.settings.get_qc_configuration()
    choices = {"A": ["I1", "S1", "N1", "X1"], "B": ["BI", "BS", "BN", "BX"]}
    root, submitted = _root(), []
    try:
        dialog = dialogs.show_qc_profile_dialog(root, state, initials="RR", assays=[("Gleich", "A"), ("Gleich", "B")],
            field_choices=choices, selected_assay_key="A", on_submit=lambda *args: submitted.append(args))
        for label, key in (("Untergrenze (MIN)", "N1"), ("Obergrenze (MAX)", "X1"), ("Zielwert (SOLL)", "S1"), ("Gemessener Wert (IST)", "I1")):
            edit_qc_field(dialog, label, key)
        assay = qc_widget(dialog, ttk.Combobox, label="Assay")
        assay.current(1)
        assay.event_generate("<<ComboboxSelected>>")
        root.update()
        for label in ("Untergrenze (MIN)", "Obergrenze (MAX)", "Zielwert (SOLL)", "Gemessener Wert (IST)"):
            field = qc_widget(dialog, ttk.Combobox, label=label)
            assert field.get() == "" and tuple(field.cget("values")) == tuple(choices["B"])
        dialog.save_button.invoke()
        assert not submitted
        dialog.destroy()
        dialog = dialogs.show_qc_profile_dialog(root, state, initials="RR", assays=[("A", "A")], field_choices={"A": ["I1", "S1", "N1"]},
            selected_profile_id=old["profile_id"], on_submit=lambda *args: submitted.append(args))
        old_max = qc_widget(dialog, ttk.Combobox, label="Obergrenze (MAX)")
        assert old_max.get() == "X1" and "X1" not in old_max.cget("values")
        assert any("X1" in child.cget("text") for child in _all_widgets(dialog) if isinstance(child, ttk.Label))
        dialog.save_button.invoke()
        assert not submitted
    finally:
        root.destroy()


def _all_widgets(parent):
    for child in parent.winfo_children():
        yield child
        yield from _all_widgets(child)


def test_settings_assay_tab_routes_the_selected_profile_and_keeps_actions_reachable(tmp_path, monkeypatch):
    from src.qualitycontrol.api import MutationContext, save_profile
    spec, old = fixture(tmp_path, count=0)
    save_profile(spec, {**copy.deepcopy(old["snapshot"]), "profile_id": "p2"}, expected_version_id=0,
                 expected_inventory_version_id=1, context=MutationContext("RR", "another-profile"))
    services = services_for(tmp_path, spec)
    write_synthetic_catalog(tmp_path, {"A": ("Same", ["I1", "S1", "N1", "X1"]), "B": ("Same", ["BI", "BS", "BN", "BX"])})
    state = services.settings.get_qc_assay_configuration()
    root, opened = _root(), []
    app = _make_app_stub(services=services)
    app._qc_configuration_generation = 0
    try:
        view = SettingsView(root, on_save=lambda: None, on_pick_watch_input=lambda: None, on_pick_watch_backup=lambda: None,
            on_pick_sqlite=lambda: None, on_reload_devices=lambda: None, on_open_output_folder=lambda: None,
            on_manage_profiles=lambda: app._open_qc_configuration("profiles"))
        app._views["settings"] = view
        view.pack(fill="both", expand=True)
        view.render_qc_configuration(state)
        view._notebook.select(1)
        root.geometry("700x420")
        root.update()
        assert len(view._qc_tree.get_children()) == 3 and view._qc_edit.winfo_viewable()
        assert view._qc_edit.winfo_rooty() + view._qc_edit.winfo_height() <= root.winfo_rooty() + root.winfo_height()
        monkeypatch.setattr(dialogs, "show_qc_profile_dialog", lambda *args, **kwargs: opened.append(kwargs))
        for identifier, row in view._qc_rows.items():
            view._qc_tree.selection_set(identifier)
            root.update()
            view._qc_edit.invoke()
            app._task_runner.invoke_success()
            assert opened[-1]["selected_assay_key"] == row.assay_key
            assert opened[-1]["selected_profile_id"] == row.profile_id
        app._open_qc_configuration("profiles", new_profile=True)
        app._task_runner.invoke_success()
        assert opened[-1]["selected_assay_key"] == "B" and opened[-1]["selected_profile_id"] == ""
    finally:
        root.destroy()


@pytest.mark.parametrize("kind", ["inventory", "profile", "lot", "reopen"])
def test_qc_form_save_is_visible_at_small_mapped_size(tmp_path: Path, kind):
    spec, _ = fixture(tmp_path)
    services = services_for(tmp_path, spec)
    state = services.settings.get_qc_configuration()
    detail = services.results.get_qc_lot_detail(services.results.list_qc_lots()[0])
    root = _root()
    try:
        if kind == "inventory":
            dialog = dialogs.show_qc_inventory_dialog(root, state, initials="RR", on_submit=lambda *_args: None)
        elif kind == "profile":
            dialog = dialogs.show_qc_profile_dialog(root, state, initials="RR", assays={"Assay A": "A"}, field_choices={"A": ["DATE", "I1", "S1", "N1", "X1"]}, on_submit=lambda *_args: None)
        elif kind == "lot":
            dialog = dialogs.show_qc_lot_dialog(root, detail, initials="RR", on_submit=lambda *_args: None)
        else:
            dialog = dialogs.show_qc_initials_dialog(root, title="Charge wieder öffnen", message="Nachweise bleiben erhalten", initials="RR", require_reason=True, on_submit=lambda *_args: None)
        dialog.geometry("640x420")
        root.update()
        assert dialog.winfo_viewable() and dialog.save_button.winfo_viewable()
        assert dialog.save_button.winfo_rooty() + dialog.save_button.winfo_height() <= dialog.winfo_rooty() + dialog.winfo_height()
        assert dialog.save_button.winfo_height() > 10
    finally:
        root.destroy()


def test_existing_settings_save_and_qc_actions_fit_minimum_window():
    root = _root()
    try:
        view = SettingsView(root, on_save=lambda: None, on_pick_watch_input=lambda: None, on_pick_watch_backup=lambda: None,
            on_pick_sqlite=lambda: None, on_reload_devices=lambda: None, on_open_output_folder=lambda: None)
        view.pack(fill="both", expand=True)
        root.update()
        assert view._btn_save.winfo_viewable() and view._btn_save.winfo_height() > 10
        assert view._btn_save.winfo_rooty() + view._btn_save.winfo_height() <= root.winfo_rooty() + root.winfo_height()
        view._settings_canvas.yview_moveto(1)
        root.update()
        assert view._var_sqlite.get() == ""
    finally:
        root.destroy()


def test_profile_device_options_keep_alias_ids_with_identical_name_and_serial(tmp_path: Path):
    spec, _ = fixture(tmp_path)
    services = services_for(tmp_path, spec)
    state = services.settings.get_qc_configuration()
    inventory = copy.deepcopy(state.inventory["snapshot"])
    alias = {**inventory["devices"][0], "device_id": "historical-alias"}
    inventory["devices"].append(alias)
    services.settings.save_qc_inventory(state, inventory, "RR", "add-alias")
    state = services.settings.get_qc_configuration()
    alias_profile = {**copy.deepcopy(state.profiles[0]["snapshot"]), "profile_id": "alias-profile", "name": "Aliasprofil", "device_id": "historical-alias"}
    services.settings.save_qc_profile(state, alias_profile, expected_version_id=0, operator_initials="RR", request_id="alias-profile")
    state = services.settings.get_qc_configuration()
    root = _root()
    submitted = []
    try:
        dialog = dialogs.show_qc_profile_dialog(root, state, initials="RR", assays={"Assay A": "A"},
            field_choices={"A": ["DATE", "I1", "S1", "N1", "X1"]}, on_submit=lambda *args: submitted.append(args))

        def find_combo(parent, label):
            children = parent.winfo_children()
            if any(isinstance(child, ttk.Label) and child.cget("text") == label for child in children):
                matches = [child for child in children if isinstance(child, ttk.Combobox)]
                if matches:
                    return matches[0]
            for child in children:
                found = find_combo(child, label)
                if found is not None:
                    return found
            return None

        profile_combo, device_combo = find_combo(dialog, "Prüfprofil"), find_combo(dialog, "Gerät")
        options = tuple(device_combo.cget("values"))
        assert len(options) == len(set(options)) == 2
        assert any("historical-alias" in label for label in options)
        for record in state.profiles:
            profile_combo.set(next(label for label in profile_combo.cget("values") if label.endswith(f"· Fassung {record['version_id']}")))
            profile_combo.event_generate("<<ComboboxSelected>>")
            root.update()
            assert device_combo.get() in options
            device_combo.current(options.index(device_combo.get()))
            dialog.save_button.invoke()
            assert submitted[-1][0]["device_id"] == record["snapshot"]["device_id"]
            assert submitted[-1][1] == record["version_id"]
    finally:
        root.destroy()
    for snapshot, expected, initials, _dialog in submitted:
        saved = services.settings.save_qc_profile(state, snapshot, expected_version_id=expected,
            operator_initials=initials, request_id=f"save-{snapshot['device_id']}")
        assert saved["snapshot"]["device_id"] == snapshot["device_id"]
    assert {row["device_id"] for row in get_inventory(spec)["snapshot"]["devices"]} == {"dev", "historical-alias"}


def test_profile_same_assay_names_bind_stable_keys_by_option_index(tmp_path):
    spec, old = fixture(tmp_path)
    services = services_for(tmp_path, spec)
    state = services.settings.get_qc_configuration()
    root, submitted = _root(), []
    choices = {"A": ["DATE", "I1", "S1", "N1", "X1"], "B": ["OTHER_DATE", "BI", "BS", "BN", "BX"]}
    try:
        dialog = dialogs.show_qc_profile_dialog(root, state, initials="RR", assays=[("Gleicher Vollname", "A"), ("Gleicher Vollname", "B")],
            field_choices=choices, selected_profile_id=old["profile_id"], on_submit=lambda *args: submitted.append(args))
        chooser = qc_widget(dialog, ttk.Combobox, label="Prüfprofil")
        assay = qc_widget(dialog, ttk.Combobox, label="Assay")
        assert assay.current() == 0 and assay.get() == "Gleicher Vollname [A]"
        assert str(assay.cget("state")) == "disabled"
        dialog.save_button.invoke()
        assert submitted[-1][0]["assay_key"] == "A" and submitted[-1][0]["profile_id"] == old["profile_id"]
        assert submitted[-1][0]["controls"][0]["fields"] == old["snapshot"]["controls"][0]["fields"]
        chooser.current(0)
        chooser.event_generate("<<ComboboxSelected>>")
        root.update()
        assert str(assay.cget("state")) == "readonly"
        assay.current(0)
        assay.event_generate("<<ComboboxSelected>>")
        root.update()
        edit_qc_field(dialog, "Levelname", "Freier Name")
        for label, key in (("Untergrenze (MIN)", "N1"), ("Obergrenze (MAX)", "X1"), ("Zielwert (SOLL)", "S1"), ("Gemessener Wert (IST)", "I1")):
            edit_qc_field(dialog, label, key)
        edit_qc_field(dialog, "SD-Referenz", "Manuelle SD")
        edit_qc_field(dialog, "Manuelle SD (optional, Punkt)", "2")
        dialog.save_button.invoke()
        created_id = submitted[-1][0]["profile_id"]
        control_id = submitted[-1][0]["controls"][0]["control_id"]
        assert created_id != old["profile_id"] and submitted[-1][0]["assay_key"] == "A"
        assay.current(1)
        assay.event_generate("<<ComboboxSelected>>")
        root.update()
        assert assay.get() == "Gleicher Vollname [B]" and assay.current() == 1
        assert qc_widget(dialog, ttk.Combobox, label="Messdatumsfeld").cget("values") == ("", *choices["B"])
        for label in ("Untergrenze (MIN)", "Obergrenze (MAX)", "Zielwert (SOLL)", "Gemessener Wert (IST)"):
            widget = qc_widget(dialog, ttk.Combobox, label=label)
            assert widget.get() == "" and widget.cget("values") == tuple(choices["B"])
        assert qc_widget(dialog, ttk.Combobox, label="SD-Referenz").get() == "Keine SD"
        for label, key in (("Untergrenze (MIN)", "BN"), ("Obergrenze (MAX)", "BX"), ("Zielwert (SOLL)", "BS"), ("Gemessener Wert (IST)", "BI")):
            edit_qc_field(dialog, label, key)
        dialog.save_button.invoke()
        assert submitted[-1][0]["assay_key"] == "B" and submitted[-1][1] == 0
        assert submitted[-1][0]["profile_id"] == created_id
        assert submitted[-1][0]["controls"][0]["control_id"] == control_id
        assert submitted[-1][0]["controls"][0]["sd_reference"] is None
    finally:
        root.destroy()


def test_qc_results_actions_are_state_aware_and_close_is_honest(tmp_path: Path):
    spec, _ = fixture(tmp_path)
    services = services_for(tmp_path, spec)
    case = services.results.list_qc_lots()[0]
    detail = services.results.get_qc_lot_detail(case)
    root = _root()
    try:
        view = StatisticsView(root, on_refresh=lambda: None)
        view.pack(fill="both", expand=True)
        view.render_qc_lots((case,))
        view.render_qc_detail(detail)
        root.update()
        assert str(view._qc_configure.cget("state")) == "normal"
        assert str(view._qc_reopen.cget("state")) == "disabled"
        assert str(view._qc_close.cget("state")) == "disabled" and view._qc_close.cget("text") == "Abschluss prüfen"
        view.render_qc_detail(replace(detail, case=replace(case, state="closed")))
        assert str(view._qc_configure.cget("state")) == "disabled"
        assert str(view._qc_reopen.cget("state")) == "normal"
        assert view._qc_close.winfo_viewable() and view._qc_close.winfo_height() > 10
        assert view._qc_panel.winfo_viewable() and not hasattr(view, "_list_panel")
    finally:
        root.destroy()


def test_optional_time_dialog_is_explicit_preserves_values_and_sources_have_german_reasons(tmp_path: Path):
    spec, old = fixture(tmp_path)
    services = services_for(tmp_path, spec)
    submitted = []
    root = _root()
    def field(parent, label):
        children = parent.winfo_children()
        if any(isinstance(child, ttk.Label) and child.cget("text") == label for child in children):
            return next(child for child in children if isinstance(child, (ttk.Entry, ttk.Combobox)))
        for child in children:
            found = field(child, label)
            if found is not None:
                return found
        return None
    def show(state):
        return dialogs.show_qc_profile_dialog(root, state, initials="RR", assays={"Assay A": "A"},
            field_choices={"A": ["DATE", "TIME", "ZEIT", "I1", "S1", "N1", "X1", "UNIT"]},
            on_submit=lambda *args: submitted.append(args))
    try:
        state = services.settings.get_qc_configuration()
        dialog = show(state)
        clock, clock_format = field(dialog, "Messzeitfeld (optional)"), field(dialog, "Zeitformat (optional, z. B. %H:%M:%S)")
        assert clock.get() == clock_format.get() == ""
        chooser = field(dialog, "Prüfprofil")
        chooser.set(next(label for label in chooser.cget("values") if label.endswith(f"· Fassung {old['version_id']}")))
        chooser.event_generate("<<ComboboxSelected>>")
        root.update()
        assert clock.get() == clock_format.get() == "" and "TIME" in clock.cget("values")
        clock.set("TIME")
        clock_format.insert(0, "%H:%M")
        dialog.geometry("640x420")
        root.update()
        assert dialog.save_button.winfo_rooty() + dialog.save_button.winfo_height() <= dialog.winfo_rooty() + dialog.winfo_height()
        dialog.save_button.invoke()
        value, expected, initials, _ = submitted[-1]
        saved = services.settings.save_qc_profile(state, value, expected_version_id=expected, operator_initials=initials, request_id="time-dialog-save")
        assert saved["snapshot"]["measurement_time_field"] == "TIME" and saved["snapshot"]["measurement_time_format"] == "%H:%M"
        dialog.destroy()
        dialog = show(services.settings.get_qc_configuration())
        chooser = field(dialog, "Prüfprofil")
        chooser.set(next(label for label in chooser.cget("values") if label.endswith(f"· Fassung {saved['version_id']}")))
        chooser.event_generate("<<ComboboxSelected>>")
        root.update()
        clock, clock_format = field(dialog, "Messzeitfeld (optional)"), field(dialog, "Zeitformat (optional, z. B. %H:%M:%S)")
        assert clock.get() == "TIME" and clock_format.get() == "%H:%M"
        clock.set("")
        clock_format.delete(0, "end")
        dialog.save_button.invoke()
        assert "measurement_time_field" not in submitted[-1][0] and "measurement_time_format" not in submitted[-1][0]
        dialog.destroy()
        add_run(spec, 3, data=payload("2026-01-03", TIME="24:00"))
        detail = services.results.get_qc_lot_detail(services.results.list_qc_lots()[0])
        view = StatisticsView(root, on_refresh=lambda: None)
        view.pack(fill="both", expand=True)
        view.render_qc_detail(detail)
        reasons = [view._qc_source_tree.item(item, "values")[-1] for item in view._qc_source_tree.get_children()]
        assert any("Extrahierte Messzeit fehlt" in text for text in reasons)
        assert any("Messzeit passt nicht zum festgelegten Format" in text for text in reasons)
    finally:
        root.destroy()


def _open_controller_lot(services):
    case = next(case for case in services.results.list_qc_lots() if case.kit_lot == "L1")
    detail = services.results.get_qc_lot_detail(case)
    services.results.save_qc_lot(detail, {}, operator_initials="RR", request_id="open-for-analysis")
    case = next(case for case in services.results.list_qc_lots() if case.kit_lot == "L1")
    return services.results.get_qc_lot_detail(case)


@pytest.mark.parametrize("kind", ["manual", "confirmed_baseline"])
def test_results_sd_origin_blocks_unit_change_and_rejects_other_store_with_same_ids(tmp_path: Path, kind):
    from src.qualitycontrol.api import get_profile, save_profile, MutationContext
    from test_qualitycontrol_profiles_lots import sd_origin_fixture
    first, second = tmp_path / "one", tmp_path / "two"
    first.mkdir()
    second.mkdir()
    spec, old, opened = sd_origin_fixture(first, kind)
    other, other_old, _ = sd_origin_fixture(second, kind)
    services = services_for(tmp_path, spec)
    original_model = services.results.get_qc_analysis(services.results.get_qc_lot_detail(services.results.list_qc_lots()[0]))
    refs = copy.deepcopy(opened["snapshot"]["sd_references"])
    for target, old_profile in ((spec, old), (other, other_old)):
        changed = copy.deepcopy(old_profile["snapshot"])
        changed["unit"] = changed["controls"][0]["unit"] = "B"
        revised = save_profile(target, changed, expected_version_id=old_profile["version_id"], expected_inventory_version_id=1,
            context=MutationContext("RR", "change-to-B"))
    case = services.results.list_qc_lots()[0]
    detail = services.results.get_qc_lot_detail(case, profile_version_id=revised["version_id"])
    services.results.save_qc_lot(detail, refs, operator_initials="RR", request_id="keep-old-sd")
    detail = services.results.get_qc_lot_detail(services.results.list_qc_lots()[0])
    current = services.results.get_qc_analysis(detail)
    assert current.model["source_manifest"]["excluded_count"] == 0
    assert current.model["computed_series"][0]["sd"] == {"available": False, "reason": "sd_unit_incompatible"}
    assert current.model["computed_series"][0]["qmma"]["available"]
    assert original_model.model["computed_series"][0]["sd"]["available"]
    assert get_profile(spec, old["version_id"]) == old and current.model["sd_references"] == refs
    services.settings.save(replace(services.settings.load(), sqlite_path=other["path"]))
    with pytest.raises(QualityControlApplicationError, match="gewechselt"):
        services.results.get_qc_analysis(detail)


def test_genuine_pre_p2_model_and_pdf_remain_exact_after_sd_semantics_change(tmp_path: Path, monkeypatch):
    import src.application.results_controller as owner
    from src.qualitycontrol.api import QCAnalysis, MutationContext, get_profile, get_report_evidence, save_profile
    import hashlib
    fixture_data = json.loads((Path(__file__).parent / "fixtures" / "qc_pre_p2_sd_archive_schema1_v2.json").read_text(encoding="utf-8"))
    assert hashlib.sha256(fixture_data["sqlite_dump"].encode()).hexdigest() == fixture_data["sqlite_dump_sha256"]
    spec = {"driver": "sqlite", "path": str(tmp_path / "synthetic.sqlite3")}
    with sqlite3.connect(spec["path"]) as conn:
        conn.executescript(fixture_data["sqlite_dump"])
    closed = next(row for row in list_lots(spec, include_history=True) if row["state"] == "closed")
    profile = get_profile(spec, closed["snapshot"]["profile_version_id"])
    before = get_report_evidence(spec, lot_version_id=closed["version_id"])
    legacy = QCAnalysis.freeze(before["model"])
    assert legacy.model_sha256 == fixture_data["model_sha256"]
    assert before["pdf_sha256"] == fixture_data["pdf_sha256"]
    assert legacy.to_dict()["analysis_model_version"] == 1
    services = services_for(tmp_path, spec)
    changed = copy.deepcopy(profile["snapshot"])
    changed["unit"] = changed["controls"][0]["unit"] = "B"
    revised = save_profile(spec, changed, expected_version_id=profile["version_id"], expected_inventory_version_id=1,
        context=MutationContext("RR", "legacy-change-unit"))
    detail = services.results.get_qc_lot_detail(next(row for row in services.results.list_qc_lots() if row.kit_lot == "L1"))
    services.results.reopen_qc_lot(detail, operator_initials="RR", request_id="legacy-reopen", reason="Neue Einheit geprüft")
    case = next(row for row in services.results.list_qc_lots() if row.kit_lot == "L1")
    detail = services.results.get_qc_lot_detail(case, profile_version_id=revised["version_id"])
    services.results.save_qc_lot(detail, detail.sd_references, operator_initials="RR", request_id="legacy-unit-B")
    detail = services.results.get_qc_lot_detail(next(row for row in services.results.list_qc_lots() if row.kit_lot == "L1"))
    assert not services.results.get_qc_analysis(detail).model["computed_series"][0]["sd"]["available"]
    monkeypatch.setattr(owner, "analyze_lot", lambda *_args, **_kwargs: pytest.fail("historical evidence must not be recalculated"))
    archived = services.results.get_qc_analysis(detail, evidence_lot_version_id=closed["version_id"])
    assert archived.model_json == legacy.model_json and archived.model_sha256 == legacy.model_sha256
    assert archived.model["algorithm_id"] == "arev2-qc-analysis-v2"
    assert "reference_lines" not in archived.model["computed_series"][0]["chart"]
    destination = tmp_path / "legacy-v1-export.pdf"
    services.results.export_qc_report(detail.case, evidence_lot_version_id=closed["version_id"], destination=destination)
    assert destination.read_bytes() == before["pdf_bytes"]
    assert hashlib.sha256(destination.read_bytes()).hexdigest() == fixture_data["pdf_sha256"]
    assert get_report_evidence(spec, lot_version_id=closed["version_id"]) == before


def test_analysis_close_history_reopen_and_export_keep_frozen_evidence(tmp_path: Path, monkeypatch):
    import src.application.results_controller as owner
    from src.qualitycontrol.api import get_report_evidence

    spec, _ = fixture(tmp_path)
    services = services_for(tmp_path, spec)
    detail = _open_controller_lot(services)
    analysis = services.results.get_qc_analysis(detail)
    add_run(spec, 3, lot="L2", data=payload("2026-02-01"))
    witnesses = services.results.list_qc_close_witnesses(detail)
    assert len(witnesses) == 1 and witnesses[0].case.kit_lot == "L2"
    with sqlite3.connect(spec["path"]) as conn:
        original_rows = conn.execute("SELECT * FROM runs").fetchall(), conn.execute("SELECT * FROM run_validations").fetchall()
    preview = services.results.prepare_qc_lot_close(detail)
    closed = services.results.close_qc_lot(preview, operator_initials="RR", request_id="real-close")
    with sqlite3.connect(spec["path"]) as conn:
        assert (conn.execute("SELECT * FROM runs").fetchall(), conn.execute("SELECT * FROM run_validations").fetchall()) == original_rows
    case = next(case for case in services.results.list_qc_lots() if case.kit_lot == "L1")
    versions = services.results.list_qc_report_versions(case)
    assert versions[0].version_id == closed["version_id"] and versions[0].model_sha256 == analysis.model_sha256
    original_pdf = get_report_evidence(spec, lot_version_id=closed["version_id"])["pdf_bytes"]
    add_run(spec, 4, data=payload("2026-01-03"))
    late_detail = services.results.get_qc_lot_detail(case)
    assert late_detail.source_manifest["population_count"] == 3
    original_analyzer = owner.analyze_lot
    monkeypatch.setattr(owner, "analyze_lot", lambda *_args: pytest.fail("stored reports must never be recalculated"))
    archived = services.results.get_qc_analysis(late_detail)
    assert archived.model["source_manifest"]["population_count"] == 2 and archived.model_sha256 == analysis.model_sha256
    destination = tmp_path / "archived.pdf"
    services.results.export_qc_report(case, evidence_lot_version_id=closed["version_id"], destination=destination)
    assert destination.read_bytes() == original_pdf
    saved_evidence = get_report_evidence(spec, lot_version_id=closed["version_id"])
    database_before = Path(spec["path"]).read_bytes(), Path(spec["path"]).stat().st_mtime_ns
    derived = tmp_path / "archived-explained.pdf"
    services.results.export_qc_report(case, evidence_lot_version_id=closed["version_id"], destination=derived, include_explanations=True)
    assert derived.read_bytes() != original_pdf
    assert get_report_evidence(spec, lot_version_id=closed["version_id"]) == saved_evidence
    assert (Path(spec["path"]).read_bytes(), Path(spec["path"]).stat().st_mtime_ns) == database_before
    with pytest.raises(QualityControlApplicationError, match="existiert bereits"):
        services.results.export_qc_report(case, evidence_lot_version_id=closed["version_id"], destination=destination)
    with pytest.raises(QualityControlApplicationError, match="gehört nicht"):
        services.results.export_qc_report(witnesses[0].case, evidence_lot_version_id=closed["version_id"], destination=tmp_path / "wrong.pdf")
    services.results.reopen_qc_lot(late_detail, operator_initials="RR", request_id="late-reopen", reason="Später Messwert")
    reopened_case = next(case for case in services.results.list_qc_lots() if case.kit_lot == "L1")
    reopened_detail = services.results.get_qc_lot_detail(reopened_case)
    assert services.results.get_qc_analysis(reopened_detail, evidence_lot_version_id=closed["version_id"]).model_sha256 == analysis.model_sha256
    monkeypatch.setattr(owner, "analyze_lot", original_analyzer)
    assert services.results.get_qc_analysis(reopened_detail).model["source_manifest"]["population_count"] == 3
    services.settings.save(replace(services.settings.load(), sqlite_path=str(tmp_path / "other.sqlite3")))
    with pytest.raises(QualityControlApplicationError, match="gewechselt"):
        services.results.export_qc_report(case, evidence_lot_version_id=closed["version_id"], destination=tmp_path / "stale.pdf")
    assert not (tmp_path / "stale.pdf").exists()


def test_render_failure_and_change_during_render_leave_lot_open(tmp_path: Path, monkeypatch):
    import hashlib
    import json
    import src.application.results_controller as owner
    from src.qualitycontrol.api import QCPdfReport, QCReportError, get_lot

    spec, _ = fixture(tmp_path)
    services = services_for(tmp_path, spec)
    detail = _open_controller_lot(services)
    analysis = services.results.get_qc_analysis(detail)
    add_run(spec, 3, lot="L2", data=payload("2026-02-01"))
    witness = services.results.list_qc_close_witnesses(detail)[0]
    original = get_lot(spec, detail.case.lot_key)
    def fail(_analysis):
        raise QCReportError("synthetic renderer failure")
    monkeypatch.setattr(owner, "render_analysis_pdf", fail)
    with pytest.raises(QualityControlApplicationError, match="renderer failure"):
        services.results.prepare_qc_lot_close(detail)
    assert get_lot(spec, detail.case.lot_key) == original
    def racing_renderer(_analysis):
        with sqlite3.connect(spec["path"]) as conn:
            conn.execute("UPDATE runs SET payload_json=? WHERE id=1", (json.dumps(payload(I1="43")),))
        raw = b"%PDF-1.4\nsynthetic render result\n%%EOF"
        return QCPdfReport(raw, hashlib.sha256(raw).hexdigest(), _analysis.model_sha256, _analysis.to_dict()["renderer_id"], 1)
    monkeypatch.setattr(owner, "render_analysis_pdf", racing_renderer)
    with pytest.raises(QualityControlApplicationError, match="geändert|anderen Quellen"):
        services.results.prepare_qc_lot_close(detail)
    assert get_lot(spec, detail.case.lot_key) == original
    with sqlite3.connect(spec["path"]) as conn:
        assert conn.execute("SELECT count(*) FROM qc_report_evidence").fetchone()[0] == 0


def test_irrational_calculated_values_are_short_in_pdf_and_mapped_ui_without_rounding_model(tmp_path: Path):
    import json
    from src.application.api import QCAnalysisView, QCLotCase, QCLotDetail
    from src.qualitycontrol.api import analyze_lot, render_analysis_pdf
    from src.qualitycontrol.model import content_hash
    from test_qualitycontrol_analysis import manifest, reference_context
    from test_qualitycontrol_pdf import extract_text
    baseline = manifest(["90", "91", "93"], targets="100")
    source = manifest(["90.0000000000000001", "100", "110"], targets="100")
    source["profile_snapshot"]["relative_limit_percent"] = "8.16496"
    source["source_token"] = content_hash({key: value for key, value in source.items() if key != "source_token"})
    references = {"c1": {"kind": "confirmed_baseline", "confirmed": True, "profile_version_id": 1,
                         "reference_id": "synthetic-display-baseline", "measurements": baseline["included"]}}
    analysis = analyze_lot(source, references, sd_reference_context=reference_context(source, references, origin=baseline))
    original_json, original_hash = analysis.model_json, analysis.model_sha256
    model = analysis.to_dict()
    series = model["computed_series"][0]
    assert model["algorithm_id"] == "arev2-qc-analysis-v4" and series["qmma"]["limit_status"] == "exceeded"
    assert all(len(value) > 12 for value in (series["qmma"]["value"], series["sd"]["sd"], series["sd"]["center"]))
    case = QCLotCase(source["store_path"], "synthetic-display", "dev", "Laborgerät", "A", "L1", "open", 1, 1,
                     ((1, "Synthetisches Prüfprofil"),), source["start_date"])
    root = _root()
    try:
        view = StatisticsView(root, on_refresh=lambda: None)
        view.pack(fill="both", expand=True)
        view.render_qc_lots((case,))
        view.render_qc_detail(QCLotDetail(case, source, references))
        view.render_qc_analysis(QCAnalysisView(case, analysis.model_json, analysis.model_sha256), ())
        root.update()
        shown = view._qc_statistics.cget("text")
        assert "QMMA: 8.16497 U" in shown and "relativ: 8.16497 %" in shown
        assert "SD 1.52753" in shown and "Referenzmitte 91.3333" in shown
        point = series["chart"]["points"][0]
        view._show_qc_point(point)
        assert "90.0000000000000001" in view._qc_point_info.cget("text")
        assert "z -0.872872" in view._qc_point_info.cget("text")
        assert point["z"] not in view._qc_point_info.cget("text")
        report = render_analysis_pdf(analysis)
        path = tmp_path / "calculated-display-report.pdf"
        path.write_bytes(report.pdf_bytes)
        geometry = path.with_suffix(".geometry.json")
        text = extract_text(path, geometry_destination=geometry)
        readable = " ".join(text.split())
        assert "QMMA: 8.16497 U" in readable and "relativ: 8.16497 %" in readable
        assert "SD: 1.52753" in readable and "Mitte: 91.3333" in readable
        assert "QMMA-Bewertung: Grenze überschritten" in readable and "SD-Referenz" in readable
        spans = json.loads(geometry.read_text(encoding="utf-8"))
        raw_column = "".join(span["text"] for span in spans if abs(span["bbox"][0] - 208) < 0.5)
        assert "90.0000000000000001" in raw_column
        assert series["qmma"]["value"] not in "".join(text.split())
        assert analysis.model_json == original_json and analysis.model_sha256 == original_hash
        assert analysis.to_dict()["computed_series"][0]["qmma"]["limit_status"] == "exceeded"
    finally:
        root.destroy()


def test_qc_chart_uses_frozen_model_with_point_selection_zoom_pan_and_reachable_actions(tmp_path: Path):
    from datetime import datetime, timedelta
    spec, _ = fixture(tmp_path)
    services = services_for(tmp_path, spec)
    detail = _open_controller_lot(services)
    analysis = services.results.get_qc_analysis(detail)
    original_json = analysis.model_json
    root = _root()
    try:
        view = StatisticsView(root, on_refresh=lambda: None)
        view.pack(fill="both", expand=True)
        view.render_qc_lots((detail.case,))
        view.render_qc_detail(detail)
        view.render_qc_analysis(analysis, ())
        root.update()
        assert str(view._qc_close.cget("state")) == "disabled" and str(view._qc_export.cget("state")) == "disabled"
        assert view._qc_close.winfo_viewable() and view._qc_close.winfo_height() > 10
        assert view._qc_close.winfo_rooty() + view._qc_close.winfo_height() <= root.winfo_rooty() + root.winfo_height()
        assert len(view._qc_chart_hits) == 2 and "QMMA: 2" in view._qc_statistics.cget("text")
        def axis_labels():
            items = sorted(view._qc_canvas.find_withtag("qc-x-axis"), key=lambda item: view._qc_canvas.coords(item)[0])
            return tuple(view._qc_canvas.itemcget(item, "text") for item in items)
        def expected_labels():
            base = datetime(2026, 1, 1)
            return tuple((base + timedelta(seconds=round((bound - base.toordinal()) * 86400))).strftime("%d.%m.%Y")
                         for bound in view._qc_chart_range[:2])
        initial_labels = axis_labels()
        assert initial_labels == ("31.12.2025", "02.01.2026") == expected_labels()
        marker = next(iter(view._qc_chart_hits))
        x1, y1, x2, y2 = view._qc_canvas.coords(marker)
        event = SimpleNamespace(x=(x1 + x2) / 2, y=(y1 + y2) / 2, delta=120)
        view._begin_qc_pan(event)
        assert "Validierung" in view._qc_point_info.cget("text")
        initial_range = view._qc_chart_range
        view._zoom_qc_chart(event)
        assert view._qc_chart_range != initial_range
        zoomed_labels = axis_labels()
        assert zoomed_labels != initial_labels and zoomed_labels == expected_labels()
        view._begin_qc_pan(event)
        view._pan_qc_chart(SimpleNamespace(x=event.x + 15, y=event.y + 10))
        assert axis_labels() == expected_labels()
        assert analysis.model_json == original_json
        view._reset_qc_chart()
        assert view._qc_chart_range == initial_range and axis_labels() == initial_labels
        for bounds in ((0.95, 2.05), (datetime.max.toordinal() + 0.5, datetime.max.toordinal() + 1.05)):
            view._qc_chart_range = (*bounds, *initial_range[2:])
            view._draw_qc_chart()
            assert "Datum nicht darstellbar" in axis_labels()
        view._reset_qc_chart()
        assert axis_labels() == initial_labels and analysis.model_json == original_json
        from src.application.api import QCAnalysisView
        from src.qualitycontrol.api import analyze_lot
        from test_qualitycontrol_analysis import manifest
        empty = analyze_lot(manifest([], targets="40"), {})
        view.render_qc_analysis(QCAnalysisView(detail.case, empty.model_json, empty.model_sha256), ())
        assert not axis_labels() and analysis.model_json == original_json
    finally:
        root.destroy()


def test_history_callback_is_deferred_and_discarded_after_store_switch(tmp_path: Path):
    spec, _ = fixture(tmp_path)
    services = services_for(tmp_path, spec)
    detail = _open_controller_lot(services)
    app = _make_app_stub(services=services)
    app._qc_source_generation, app._qc_source_latest = 0, None
    rendered, io = [], []
    app._views["statistics"] = SimpleNamespace(selected_qc_detail=lambda: detail, selected_qc_report_version=lambda: None,
        selected_qc_case=lambda: detail.case, set_qc_analysis_loading=lambda: None, render_qc_analysis=lambda *args: rendered.append(args))
    original = services.results.get_qc_analysis
    services.results.get_qc_analysis = lambda *args, **kwargs: io.append(True) or original(*args, **kwargs)
    app._load_qc_report_version()
    assert not io
    pending = app._task_runner.submissions[-1][1]()
    app._settings = replace(app._settings, sqlite_path=str(tmp_path / "other.sqlite3"))
    app._task_runner.invoke_success(result=pending)
    assert not rendered


def test_close_shell_defers_read_only_preview_and_final_click_only_publishes(tmp_path: Path, monkeypatch):
    spec, _ = fixture(tmp_path)
    services = services_for(tmp_path, spec)
    detail = _open_controller_lot(services)
    analysis = services.results.get_qc_analysis(detail)
    add_run(spec, 3, lot="L2", data=payload("2026-02-01"))
    app = _make_app_stub(services=services)
    app._qc_source_generation, app._qc_source_latest = 0, None
    shown, reads, closes, rendered = [], [], [], []
    app._views["statistics"] = SimpleNamespace(selected_qc_detail=lambda: detail, selected_qc_analysis=lambda: analysis, selected_qc_case=lambda: detail.case)
    original = services.results.prepare_qc_lot_close
    services.results.prepare_qc_lot_close = lambda value: reads.append(value) or original(value)
    services.results.close_qc_lot = lambda *args, **kwargs: closes.append((args, kwargs)) or {}
    dialog = SimpleNamespace(save_button=SimpleNamespace(configure=lambda **kwargs: None), winfo_exists=lambda: True,
        render_preview=lambda value: rendered.append(value), render_error=lambda message: pytest.fail(message))
    def show(*args, **kwargs):
        shown.append((args, kwargs))
        return dialog
    monkeypatch.setattr(dialogs, "show_qc_close_dialog", show)
    app._close_qc_lot()
    assert not reads and not closes and len(shown) == 1
    app._task_runner.invoke_success()
    assert len(reads) == len(rendered) == 1 and not closes
    preview = rendered[0]
    assert preview.witness_kit_lot == "L2" and preview.pdf_bytes.startswith(b"%PDF-")
    assert list_lots(spec)[0]["state"] == "open"
    shown[0][1]["on_submit"](preview, "RR", dialog)
    assert not closes and app._task_runner.submissions[-1][0] == "qc-write"
    shown[0][1]["on_submit"](preview, "RR", dialog)
    assert len([item for item in app._task_runner.submissions if item[0] == "qc-write"]) == 1
    app._task_runner.submissions[-1][1]()
    assert closes[0][0] == (preview,)
    assert closes[0][1]["operator_initials"] == "RR" and closes[0][1]["request_id"]


def test_export_shell_captures_version_and_resets_optional_print_only_after_success(tmp_path: Path, monkeypatch):
    from interfaces.tk import test_app

    spec, _ = fixture(tmp_path)
    services = services_for(tmp_path, spec)
    detail = _open_controller_lot(services)
    analysis = replace(services.results.get_qc_analysis(detail), evidence_lot_version_id=123)
    app = _make_app_stub(services=services)
    app._qc_source_generation = 7
    flag = [False]
    app._views["statistics"] = SimpleNamespace(selected_qc_analysis=lambda: analysis,
        _qc_include_explanations=SimpleNamespace(get=lambda: flag[0], set=lambda value: flag.__setitem__(0, value)))
    messages, failures = [], []
    app._show_info_dialog = lambda *args: messages.append(args)
    app._show_qc_error = lambda error: failures.append(error)
    destination = str(tmp_path / "selected.pdf")
    monkeypatch.setattr(test_app.filedialog, "asksaveasfilename", lambda **kwargs: destination)
    exports = []
    services.results.export_qc_report = lambda *args, **kwargs: exports.append((args, kwargs)) or {}
    app._export_qc_report()
    flag[0] = True
    assert not exports and app._task_runner.submissions[-1][0] == "qc-export"
    app._task_runner.invoke_success()
    assert exports == [((analysis.case,), {"evidence_lot_version_id": 123, "destination": destination, "include_explanations": False})]
    assert flag[0] is False and len(messages) == 1
    flag[0] = True
    app._export_qc_report()
    app._task_runner.invoke_error()
    assert flag[0] is True and len(failures) == 1
    app._export_qc_report()
    app._task_runner.invoke_success()
    assert exports[-1][1]["include_explanations"] is True and flag[0] is False
    assert not Path(destination).exists()


def test_p2_statistics_draws_frozen_reference_values_and_keeps_independent_point_findings():
    from src.application.api import QCAnalysisView, QCLotCase, QCLotDetail
    from src.qualitycontrol.api import QCAnalysis, analyze_lot
    from test_qualitycontrol_limits import limit_manifest
    source = limit_manifest(["100", "100", "100", "112"], targets="100")
    analysis = analyze_lot(source, {})
    before = analysis.model_json, analysis.model_sha256
    case = QCLotCase(source["store_path"], "p2-limits", "dev", "Laborgerät", "A", "L1", "open", 1, 1,
        ((1, "Prüfprofil"),), source["start_date"])
    root = _root()
    root.geometry("1000x850")
    try:
        view = StatisticsView(root, on_refresh=lambda: None)
        view.pack(fill="both", expand=True)
        view.render_qc_lots((case,))
        view.render_qc_detail(QCLotDetail(case, source, {}))
        view.render_qc_analysis(QCAnalysisView(case, analysis.model_json, analysis.model_sha256), ())
        root.update()
        assert "QMMA: 6 U" in view._qc_statistics.cget("text") and "Keine SD-Referenz" in view._qc_statistics.cget("text")
        assert "QMMA-Grenze (relativ): 10 %" in view._qc_statistics.cget("text")
        assert "QMMA-Bewertung: Innerhalb der Grenze" in view._qc_statistics.cget("text")
        assert "Mittelwert 103" in view._qc_statistics.cget("text")
        assert "empirische SD (n-1) 6" in view._qc_statistics.cget("text")
        assert "VK 5.82524 %" in view._qc_statistics.cget("text")
        assert "Einzelwert MIN (10 %): 90 U" in view._qc_legend.cget("text")
        assert "Hersteller MAX: 120 U" in view._qc_legend.cget("text")
        canvas = view._qc_canvas
        lines = canvas.find_withtag("qc-reference-line")
        assert len(lines) == 6 and len(canvas.find_withtag("qc-limit-exceeded")) == 1
        xlo, xhi, ylo, yhi = view._qc_chart_range
        left, top, width, height = view._qc_plot_box
        frozen = analysis.to_dict()["computed_series"][0]["chart"]["reference_lines"]
        for marker, line in zip(lines, frozen):
            expected_y = top + height - (float(line["value"]) - ylo) / (yhi - ylo) * height
            assert canvas.coords(marker) == pytest.approx((left, expected_y, left + width, expected_y))
        point = analysis.to_dict()["computed_series"][0]["chart"]["points"][-1]
        view._show_qc_point(point)
        assert "Hersteller: Innerhalb der Grenzen" in view._qc_point_info.cget("text")
        assert "Einzelwert: Grenze überschritten" in view._qc_point_info.cget("text")
        assert "112" in view._qc_point_info.cget("text")
        assert view._qc_source_tree.item(view._qc_source_tree.get_children()[0], "values")[4:6] == ("80", "120")
        negative = analyze_lot(limit_manifest(["-100"], targets="-100", percent="0", minimum="-120", maximum="-80"), {})
        view.render_qc_analysis(QCAnalysisView(case, negative.model_json, negative.model_sha256), ())
        root.update()
        assert "Einzelwert MIN (0 %): -100 U" in view._qc_legend.cget("text")
        assert "Einzelwert MAX (0 %): -100 U" in view._qc_legend.cget("text")
        assert "Einzelwert: Innerhalb der Grenzen" in view._qc_point_info.cget("text")
        # A genuine historical model carries its original p-profile but no new lines.
        fixture_data = json.loads((Path(__file__).parent / "fixtures" / "qc_pre_p2_schema1_v2.json").read_text(encoding="utf-8"))
        old = QCAnalysis(fixture_data["model_json"], fixture_data["model_sha256"])
        view.render_qc_analysis(QCAnalysisView(case, old.model_json, old.model_sha256, 5, fixture_data["pdf_sha256"]), ())
        root.update()
        assert not canvas.find_withtag("qc-reference-line") and not canvas.find_withtag("qc-limit-exceeded")
        assert "Altmodell" in view._qc_legend.cget("text")
        assert "Einzelwert:" not in view._qc_point_info.cget("text")
        assert old.model_json == fixture_data["model_json"]
        legacy_v3 = json.loads((Path(__file__).parent / "fixtures" / "qc_pre_p4_schema2_v3.json").read_text(encoding="utf-8"))
        stored = QCAnalysis(legacy_v3["model_json"], legacy_v3["model_sha256"])
        view.render_qc_analysis(QCAnalysisView(case, stored.model_json, stored.model_sha256, 6, legacy_v3["pdf_sha256"]), ())
        root.update()
        assert len(canvas.find_withtag("qc-reference-manufacturer")) == 2
        assert not canvas.find_withtag("qc-reference-mean")
        assert "Messreihe: Mittelwert" not in view._qc_statistics.cget("text")
        assert stored.model_json == legacy_v3["model_json"]
        assert (analysis.model_json, analysis.model_sha256) == before
    finally:
        root.destroy()


def p3_usage_fixture(tmp_path, *, target_valid=True):
    spec, profile = fixture(tmp_path, count=0)
    for index, lot, date in ((1, "A", "2026-01-02"), (2, "A", "2026-01-03"), (3, "B", "2026-01-01"), (4, "B", "2026-01-04"), (5, "C", "unlesbar")):
        add_run(spec, index, lot=lot, data=payload(date, I1="unlesbar" if index == 4 else "42"),
            validated=target_valid if lot == "A" else index == 3)
    services = services_for(tmp_path, spec)
    case = next(row for row in services.results.list_qc_lots() if row.kit_lot == "A")
    return spec, profile, services, services.results.get_qc_lot_detail(case)


def p3_evidence_count(spec):
    with sqlite3.connect(spec["path"]) as conn:
        return conn.execute("SELECT count(*) FROM qc_report_evidence").fetchone()[0]


def test_p3_read_only_real_preview_cancel_direct_first_close_idempotency_and_archive(tmp_path, monkeypatch):
    import hashlib
    import src.application.results_controller as owner
    from src.qualitycontrol.api import get_report_evidence
    spec, profile, services, detail = p3_usage_fixture(tmp_path)
    assert detail.case.state == "unconfigured" and detail.case.close_available and detail.case.last_usage == "2026-01-03"
    before = Path(spec["path"]).read_bytes(), Path(spec["path"]).stat().st_mtime_ns
    preview = services.results.prepare_qc_lot_close(detail)
    assert (Path(spec["path"]).read_bytes(), Path(spec["path"]).stat().st_mtime_ns) == before
    assert not list_lots(spec) and p3_evidence_count(spec) == 0
    assert preview.analysis.model["source_manifest"] == detail.source_manifest
    assert hashlib.sha256(preview.pdf_bytes).hexdigest() == preview.pdf_sha256
    assert preview.witness_kit_lot == "B" and not preview.block_reason
    assert preview.analysis.model["computed_series"][0]["qmma"]["n"] == 2
    # Discarding the prepared value is a complete cancellation: no open revision.
    again = services.results.prepare_qc_lot_close(detail)
    assert again.analysis.model_sha256 == preview.analysis.model_sha256 and not list_lots(spec)
    monkeypatch.setattr(owner, "render_analysis_pdf", lambda *args, **kwargs: pytest.fail("final confirmation must publish prepared bytes"))
    closed = services.results.close_qc_lot(preview, operator_initials="RR", request_id="p3-direct-first")
    assert closed["predecessor_id"] == 0 and closed["state"] == "closed"
    assert len(list_lots(spec, include_history=True)) == 1
    assert closed["snapshot"]["successor_witness"]["witness_version"] == "qc-usage-witness-v1"
    assert services.results.close_qc_lot(preview, operator_initials="RR", request_id="p3-direct-first") == closed
    assert p3_evidence_count(spec) == 1
    stored = get_report_evidence(spec, lot_version_id=closed["version_id"])
    assert stored["pdf_bytes"] == preview.pdf_bytes and stored["model_sha256"] == preview.analysis.model_sha256
    add_run(spec, 6, lot="A", data=payload("2026-01-05"))
    case = next(row for row in services.results.list_qc_lots() if row.kit_lot == "A")
    current = services.results.get_qc_lot_detail(case)
    assert current.case.state == "closed" and current.source_changed and current.case.last_usage == "2026-01-05"
    archived = services.results.get_qc_analysis(current)
    assert archived.model_json == preview.analysis.model_json
    assert get_report_evidence(spec, lot_version_id=closed["version_id"]) == stored


def test_p3_empty_target_keeps_offer_and_real_preview_but_direct_store_publication_is_forbidden(tmp_path):
    from src.qualitycontrol.api import MutationContext, QCConfigurationError, close_lot
    spec, profile, services, detail = p3_usage_fixture(tmp_path, target_valid=False)
    assert detail.case.close_available and not detail.source_manifest["included"]
    preview = services.results.prepare_qc_lot_close(detail)
    assert preview.block_reason and preview.pdf_bytes.startswith(b"%PDF-")
    with pytest.raises(QualityControlApplicationError, match="validierten"):
        services.results.close_qc_lot(preview, operator_initials="RR", request_id="p3-empty-controller")
    model = preview.analysis.model
    with pytest.raises(QCConfigurationError, match="vollständigen.*validierten"):
        close_lot(spec, detail.case.lot_key, expected_version_id=0, profile_version_id=profile["version_id"],
            expected_source_token=detail.source_manifest["source_token"], witness_kit_lot=preview.witness_kit_lot,
            expected_witness_source_token=preview.witness_source_token, expected_chronology_token=preview.chronology_sha256,
            analysis_model=model, pdf_bytes=preview.pdf_bytes, pdf_sha256=preview.pdf_sha256,
            algorithm_id=model["algorithm_id"], renderer_id=preview.renderer_id, context=MutationContext("RR", "p3-empty-direct"))
    assert not list_lots(spec) and p3_evidence_count(spec) == 0


def p3_change_context(kind, spec, profile, services):
    from src.qualitycontrol.api import MutationContext, get_inventory, get_lot_sources, open_lot, save_inventory, save_profile
    from src.resultvalidation.api import correct_validation
    if kind == "value":
        with sqlite3.connect(spec["path"]) as conn:
            conn.execute("UPDATE runs SET payload_json=? WHERE id=1", (json.dumps(payload("2026-01-02", I1="43")),))
    elif kind == "validation":
        correct_validation(spec, 1, "ZZ", comment="Korrigierte Testvalidierung")
    elif kind in {"target_usage", "witness_usage", "third_usage"}:
        add_run(spec, 6, lot={"target_usage": "A", "witness_usage": "B", "third_usage": "D"}[kind], data=payload("2026-01-06"), validated=False)
    elif kind == "profile":
        changed = copy.deepcopy(profile["snapshot"])
        changed["name"] = "Geändertes Profil"
        save_profile(spec, changed, expected_version_id=profile["version_id"], expected_inventory_version_id=1, context=MutationContext("RR", "p3-race-profile"))
    elif kind == "inventory":
        inventory = get_inventory(spec)
        changed = copy.deepcopy(inventory["snapshot"])
        changed["devices"][0]["display_name"] = "Geändertes Gerät"
        save_inventory(spec, changed, expected_version_id=inventory["version_id"], context=MutationContext("RR", "p3-race-inventory"))
    elif kind == "lot_head":
        source = get_lot_sources(spec, profile_version_id=profile["version_id"], kit_lot="A")
        open_lot(spec, profile_version_id=profile["version_id"], kit_lot="A", expected_source_token=source["source_token"], sd_references={}, context=MutationContext("RR", "p3-race-open"))
    elif kind == "store":
        services.settings.save(replace(services.settings.load(), sqlite_path=str(Path(spec["path"]).with_name("other.sqlite3"))))
    else:
        raise AssertionError(kind)


@pytest.mark.parametrize("kind", ["value", "validation", "target_usage", "witness_usage", "third_usage", "profile", "inventory", "lot_head", "store"])
@pytest.mark.parametrize("stage", ["preparing", "publishing"])
def test_p3_complete_context_races_cannot_publish_stale_preview(tmp_path, monkeypatch, kind, stage):
    import src.application.results_controller as owner
    spec, profile, services, detail = p3_usage_fixture(tmp_path)
    if stage == "preparing":
        render = owner.render_analysis_pdf
        def racing_render(analysis):
            report = render(analysis)
            p3_change_context(kind, spec, profile, services)
            return report
        monkeypatch.setattr(owner, "render_analysis_pdf", racing_render)
        with pytest.raises(QualityControlApplicationError):
            services.results.prepare_qc_lot_close(detail)
    else:
        preview = services.results.prepare_qc_lot_close(detail)
        p3_change_context(kind, spec, profile, services)
        before = list_lots(spec, include_history=True)
        with pytest.raises(QualityControlApplicationError):
            services.results.close_qc_lot(preview, operator_initials="RR", request_id="p3-race-publish")
        assert list_lots(spec, include_history=True) == before
    assert not any(row["state"] == "closed" for row in list_lots(spec, include_history=True))
    assert p3_evidence_count(spec) == 0


def test_p3_prepared_pdf_tampering_and_pending_profile_reconfiguration_cannot_close(tmp_path):
    spec, profile, services, detail = p3_usage_fixture(tmp_path)
    preview = services.results.prepare_qc_lot_close(detail)
    with pytest.raises(QualityControlApplicationError, match="Prüfsumme"):
        services.results.close_qc_lot(replace(preview, pdf_bytes=preview.pdf_bytes+b"tampered"), operator_initials="RR", request_id="p3-tampered")
    assert not list_lots(spec) and p3_evidence_count(spec) == 0


@pytest.mark.parametrize("change", ["cancel", "store", "selection", "profile"])
def test_p3_late_prepare_callback_after_context_change_never_shows_or_writes(tmp_path, monkeypatch, change):
    spec, profile, services, detail = p3_usage_fixture(tmp_path)
    analysis = services.results.get_qc_analysis(detail)
    selected = [detail.case]
    app = _make_app_stub(services=services)
    app._qc_source_generation, app._qc_source_latest = 0, None
    rendered, shown = [], []
    app._views["statistics"] = SimpleNamespace(selected_qc_detail=lambda: detail, selected_qc_analysis=lambda: analysis, selected_qc_case=lambda: selected[0])
    dialog = SimpleNamespace(winfo_exists=lambda: True, render_preview=lambda value: rendered.append(value), render_error=lambda message: pytest.fail(message))
    def show(*args, **kwargs):
        shown.append(kwargs)
        return dialog
    monkeypatch.setattr(dialogs, "show_qc_close_dialog", show)
    app._close_qc_lot()
    if change == "cancel":
        shown[0]["on_cancel"]()
    elif change == "store":
        app._settings = replace(app._settings, sqlite_path=str(tmp_path / "other.sqlite3"))
    elif change == "selection":
        selected[0] = replace(detail.case, lot_key="different")
    else:
        app._qc_source_generation += 1
    app._task_runner.invoke_success(result=SimpleNamespace(prepared=True))
    assert not rendered and not list_lots(spec) and p3_evidence_count(spec) == 0
    assert not any(row[0] == "qc-write" for row in app._task_runner.submissions)


def test_p3_native_close_preview_shows_levels_and_stale_submit_is_visible_and_no_write(tmp_path):
    from src.qualitycontrol.api import MutationContext, save_profile
    spec, profile, services, detail = p3_usage_fixture(tmp_path)
    changed = copy.deepcopy(profile["snapshot"])
    second = copy.deepcopy(changed["controls"][0])
    second.update(control_id="c2", name="Zweites Level", fields={"IST": "I2", "SOLL": "S2", "MIN": "N2", "MAX": "X2"})
    changed["controls"].append(second)
    save_profile(spec, changed, expected_version_id=profile["version_id"], expected_inventory_version_id=1, context=MutationContext("RR", "p3-preview-levels"))
    case = next(row for row in services.results.list_qc_lots() if row.kit_lot == "A")
    detail = services.results.get_qc_lot_detail(case)
    analysis = services.results.get_qc_analysis(detail)
    preview = services.results.prepare_qc_lot_close(detail)
    app = _make_app_stub(services=services)
    app._qc_source_generation, app._qc_source_latest = 0, None
    app._views["statistics"] = SimpleNamespace(selected_qc_detail=lambda: detail, selected_qc_analysis=lambda: analysis, selected_qc_case=lambda: detail.case)
    root = _root()
    try:
        submitted, canceled = [], []
        dialog = dialogs.show_qc_close_dialog(root, detail, initials="RR", on_submit=lambda *args: submitted.append(args), on_cancel=lambda: canceled.append(True))
        dialog.render_preview(preview)
        dialog.geometry("640x420")
        root.update()
        def labels(parent):
            return [child.cget("text") for child in parent.winfo_children() if isinstance(child, ttk.Label)] + [text for child in parent.winfo_children() for text in labels(child)]
        shown = " ".join(labels(dialog))
        assert "Zweites Level" in shown and "SOLL=S2" in shown and "QMMA nicht verfügbar" in shown
        assert "QMMA-Grenze (relativ)" in shown and "Westgard:" in shown and "C" in shown
        assert dialog.save_button.winfo_rooty() + dialog.save_button.winfo_height() <= dialog.winfo_rooty() + dialog.winfo_height()
        dialog.render_error("Auswahl oder Ergebnisspeicher wurde geändert. Bitte den Abschluss neu prüfen.")
        root.update()
        assert "Bitte den Abschluss neu prüfen" in " ".join(labels(dialog))
        assert not list_lots(spec) and p3_evidence_count(spec) == 0
        dialog.save_button.invoke()
        assert len(submitted) == 1 and submitted[0][0] is preview
        dialog.set_busy(True)
        dialog.save_button.invoke()
        dialog.cancel_button.invoke()
        dialog.event_generate("<Escape>")
        root.update()
        assert dialog.winfo_exists() and not canceled and len(submitted) == 1
        assert str(dialog.cancel_button.cget("state")) == str(dialog.save_button.cget("state")) == "disabled"
        dialog.set_busy(False)
        dialog.cancel_button.invoke()
        assert canceled and not dialog.winfo_exists()
        assert not list_lots(spec) and p3_evidence_count(spec) == 0
    finally:
        root.destroy()


def test_p3_native_archive_change_hint_survives_frozen_analysis_and_date_only_axes(tmp_path):
    spec, profile, services, detail = p3_usage_fixture(tmp_path)
    preview = services.results.prepare_qc_lot_close(detail)
    closed = services.results.close_qc_lot(preview, operator_initials="RR", request_id="p3-hint-close")
    add_run(spec, 6, lot="A", data=payload("2026-01-05"))
    case = next(row for row in services.results.list_qc_lots() if row.kit_lot == "A")
    latest = services.results.get_qc_lot_detail(case)
    archived = services.results.get_qc_analysis(latest)
    root = _root()
    try:
        view = StatisticsView(root, on_refresh=lambda: None)
        view.pack(fill="both", expand=True)
        view.render_qc_lots((case,))
        view.render_qc_detail(latest)
        assert latest.source_changed and "weichen" in view._qc_change_hint.cget("text")
        view.render_qc_analysis(archived, services.results.list_qc_report_versions(case))
        root.update()
        assert "weichen" in view._qc_change_hint.cget("text") and "Gespeicherter Nachweis" in view._qc_summary.cget("text")
        assert "00:00" not in view._qc_point_info.cget("text")
        assert all(":" not in view._qc_canvas.itemcget(item, "text") for item in view._qc_canvas.find_withtag("qc-x-axis"))
        assert str(view._qc_close.cget("state")) == "disabled"
        assert list_lots(spec)[0]["state"] == "closed" and list_lots(spec)[0]["version_id"] == closed["version_id"]
    finally:
        root.destroy()


def test_p3_native_stale_submit_after_rendered_preview_shows_error_without_write(tmp_path, monkeypatch):
    spec, profile, services, detail = p3_usage_fixture(tmp_path)
    analysis = services.results.get_qc_analysis(detail)
    preview = services.results.prepare_qc_lot_close(detail)
    app = _make_app_stub(services=services)
    app._qc_source_generation, app._qc_source_latest = 0, None
    app._views["statistics"] = SimpleNamespace(selected_qc_detail=lambda: detail, selected_qc_analysis=lambda: analysis, selected_qc_case=lambda: detail.case)
    root = _root()
    try:
        opened = []
        real_show = dialogs.show_qc_close_dialog
        def show(_parent, *args, **kwargs):
            dialog = real_show(root, *args, **kwargs)
            opened.append(dialog)
            return dialog
        monkeypatch.setattr(dialogs, "show_qc_close_dialog", show)
        app._close_qc_lot()
        app._task_runner.invoke_success(result=preview)
        dialog = opened[0]
        root.update()
        app._qc_source_generation += 1
        dialog.save_button.invoke()
        root.update()
        def texts(parent):
            return [str(child.cget("text")) for child in parent.winfo_children() if isinstance(child, ttk.Label)] + [value for child in parent.winfo_children() for value in texts(child)]
        assert any("Auswahl oder Ergebnisspeicher wurde geändert" in text for text in texts(dialog))
        assert not any(item[0] == "qc-write" for item in app._task_runner.submissions)
        assert not list_lots(spec) and p3_evidence_count(spec) == 0
    finally:
        root.destroy()


def test_p3_unsaved_profile_change_must_be_bound_explicitly_before_close(tmp_path):
    from src.qualitycontrol.api import MutationContext, save_profile
    spec, profile, services, detail = p3_usage_fixture(tmp_path)
    opened = services.results.save_qc_lot(detail, {}, operator_initials="RR", request_id="p3-explicit-open")
    changed = copy.deepcopy(profile["snapshot"])
    changed["name"] = "Neue Profilfassung"
    revised = save_profile(spec, changed, expected_version_id=profile["version_id"], expected_inventory_version_id=1, context=MutationContext("RR", "p3-new-profile"))
    case = next(row for row in services.results.list_qc_lots() if row.kit_lot == "A")
    selected = services.results.get_qc_lot_detail(case, profile_version_id=revised["version_id"])
    with pytest.raises(QualityControlApplicationError, match="Profiländerung.*nicht gespeichert"):
        services.results.prepare_qc_lot_close(selected)
    assert list_lots(spec)[0]["version_id"] == opened["version_id"] and p3_evidence_count(spec) == 0


def test_p3_multiple_matching_profiles_require_explicit_context_without_new_mapping(tmp_path):
    from src.qualitycontrol.api import MutationContext, save_profile
    spec, profile, services, detail = p3_usage_fixture(tmp_path)
    other = copy.deepcopy(profile["snapshot"])
    other.update(profile_id="another", name="Zweites vorhandenes Profil")
    save_profile(spec, other, expected_version_id=0, expected_inventory_version_id=1, context=MutationContext("RR", "p3-second-profile"))
    case = next(row for row in services.results.list_qc_lots() if row.kit_lot == "A")
    assert case.profile_version_id == 0 and not case.close_available
    with pytest.raises(QualityControlApplicationError, match="Prüfprofil"):
        services.results.get_qc_lot_detail(case)
    explicit = services.results.get_qc_lot_detail(case, profile_version_id=profile["version_id"])
    assert explicit.case.close_available and explicit.case.profile_version_id == profile["version_id"]
    assert not list_lots(spec)


def test_p3_native_post_close_refresh_clears_selection_details_without_false_missing_profile(tmp_path):
    spec, profile, services, detail = p3_usage_fixture(tmp_path)
    preview = services.results.prepare_qc_lot_close(detail)
    services.results.close_qc_lot(preview, operator_initials="RR", request_id="p3-refresh-close")
    case = next(row for row in services.results.list_qc_lots() if row.kit_lot == "A")
    closed_detail = services.results.get_qc_lot_detail(case)
    analysis = services.results.get_qc_analysis(closed_detail)
    root = _root()
    try:
        view = StatisticsView(root, on_refresh=lambda: None)
        view.pack(fill="both", expand=True)
        view.render_qc_lots((case,))
        view._qc_tree.selection_set(case.lot_key)
        root.update()
        view.render_qc_detail(closed_detail)
        view.render_qc_analysis(analysis, services.results.list_qc_report_versions(case))
        root.update()
        assert view._qc_control.get() and "Messung" in view._qc_point_info.cget("text")
        view.render_qc_lots((case,))
        root.update()
        assert view.selected_qc_case() is None
        assert view._qc_summary.cget("text").startswith("Charge auswählen.")
        assert "zuerst ein Prüfprofil" not in view._qc_summary.cget("text")
        assert view.selected_qc_detail() is None and view.selected_qc_analysis() is None
        assert not view._qc_canvas.find_all() and not view._qc_chart_hits
        assert "Charge auswählen" in view._qc_point_info.cget("text") and "Messung" not in view._qc_point_info.cget("text")
        for variable, combo in ((view._qc_profile, view._qc_profile_combo), (view._qc_control, view._qc_control_combo), (view._qc_version, view._qc_version_combo)):
            assert variable.get() == "" and not combo.cget("values") and str(combo.cget("state")) == "disabled"
        missing = replace(case, profile_version_id=0, profile_options=(), state="unconfigured")
        view.render_qc_lots((missing,))
        view._qc_tree.selection_set(case.lot_key)
        root.update()
        assert "zuerst ein Prüfprofil" in view._qc_summary.cget("text")
    finally:
        root.destroy()
