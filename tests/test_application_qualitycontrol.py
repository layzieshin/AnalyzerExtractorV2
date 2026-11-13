"""P4 application and mapped Tk acceptance with synthetic stores."""
from __future__ import annotations

import copy
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
    services = create_desktop_services(root)
    services.settings.save(DesktopSettings("sqlite", spec["path"], "", "dev", operator_initials="RR"))
    return services


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
    witness = services.results.list_qc_close_witnesses(detail)[0]
    rule_path.write_text(json.dumps({"assay_key": "A", "assay_name": "Neuer Katalogname"}), encoding="utf-8")
    with pytest.raises(QualityControlApplicationError, match="veraltet"):
        services.results.close_qc_lot(detail, analysis, witness, operator_initials="RR", request_id="stale-name")
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
    spec, _ = fixture(tmp_path)
    services = services_for(tmp_path, spec)
    io, shown = [], []
    services.rules.list_inventory = lambda kind="all": io.append(("inventory", kind)) or [SimpleNamespace(assay_key="A", assay_name="Assay A")]
    services.rules.list_fields = lambda key: io.append(key) or ["I1", "S1", "N1", "X1", "DATE"]
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
        assert payload[1] == [("Assay A", "A")] and payload[2] == {"A": keys}
        app._task_runner.invoke_success(result=payload)
        assert len(opened) == 1
        dialog, kwargs = opened[0]
        chooser = field(dialog, "Prüfprofil")
        chooser.set(f"{profile['snapshot']['name']} · Fassung {profile['version_id']}")
        chooser.event_generate("<<ComboboxSelected>>")
        root.update()
        assert dialog.winfo_viewable() and field(dialog, "Assay").get() == "Assay A"
        assert field(dialog, "Messdatumsfeld").get() == "DATE"
        assert field(dialog, "Gemessener Wert (IST)").get() == "I1"
        assert "TIME" in field(dialog, "Messzeitfeld (optional)").cget("values")
        assert kwargs["field_choices"] == {"A": keys}
        dialog.destroy()
        index["assays"][0]["ruleset_file"] = "missing-active.json"
        (rules / "index.json").write_text(json.dumps(index), encoding="utf-8")
        app._open_qc_configuration("profiles")
        with pytest.raises(RuleResolverError, match="RuleSet file not found"):
            app._task_runner.submissions[-1][1]()
        assert len(opened) == 1
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
            profile_combo.set(f"{record['snapshot']['name']} · Fassung {record['version_id']}")
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
    spec, _ = fixture(tmp_path)
    services = services_for(tmp_path, spec)
    state = services.settings.get_qc_configuration()
    root, submitted = _root(), []
    try:
        dialog = dialogs.show_qc_profile_dialog(root, state, initials="RR", assays=[("Gleicher Vollname", "A"), ("Gleicher Vollname", "B")],
            field_choices={"A": ["DATE", "I1"], "B": ["OTHER"]}, on_submit=lambda *args: submitted.append(args))
        def field(parent, label):
            children = parent.winfo_children()
            if any(isinstance(child, ttk.Label) and child.cget("text") == label for child in children):
                return next((child for child in children if isinstance(child, ttk.Combobox)), None)
            return next((value for child in children if (value := field(child, label)) is not None), None)
        chooser, assay = field(dialog, "Prüfprofil"), field(dialog, "Assay")
        chooser.current(1)
        chooser.event_generate("<<ComboboxSelected>>")
        root.update()
        assert assay.current() == 0 and assay.get() == "Gleicher Vollname"
        dialog.save_button.invoke()
        assert submitted[-1][0]["assay_key"] == "A"
        assay.current(1)
        assay.event_generate("<<ComboboxSelected>>")
        root.update()
        assert field(dialog, "Messdatumsfeld").cget("values") == ("", "OTHER")
        dialog.save_button.invoke()
        assert submitted[-1][0]["assay_key"] == "B" and assay.get() == "Gleicher Vollname"
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
        assert str(view._qc_close.cget("state")) == "disabled" and view._qc_close.cget("text") == "Mit PDF abschließen"
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
        chooser.set(f"{old['snapshot']['name']} · Fassung {old['version_id']}")
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
        chooser.set(f"{saved['snapshot']['name']} · Fassung {saved['version_id']}")
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


def test_archived_v1_model_and_pdf_remain_exact_after_sd_semantics_change(tmp_path: Path, monkeypatch):
    import src.application.results_controller as owner
    from src.qualitycontrol.api import (QCAnalysis, MutationContext, analyze_lot, close_lot, get_lot_sources,
        get_report_evidence, get_sd_reference_context, render_analysis_pdf, save_profile)
    from test_qualitycontrol_profiles_lots import sd_origin_fixture
    spec, profile, opened = sd_origin_fixture(tmp_path, "confirmed_baseline")
    source = get_lot_sources(spec, profile_version_id=profile["version_id"], kit_lot="L1")
    origin = get_sd_reference_context(spec, lot_key=opened["lot_key"], expected_version_id=opened["version_id"])
    old_model = analyze_lot(source, opened["snapshot"]["sd_references"], sd_reference_context=origin).to_dict()
    old_model.pop("sd_reference_context")
    old_model["algorithm_id"] = "arev2-qc-analysis-v1"
    legacy = QCAnalysis.freeze(old_model)
    report = render_analysis_pdf(legacy)
    add_run(spec, 4, lot="L2", data=payload("2026-02-01", I1="94", S1="100"))
    witness = get_lot_sources(spec, profile_version_id=profile["version_id"], kit_lot="L2")
    closed = close_lot(spec, opened["lot_key"], expected_version_id=opened["version_id"], expected_source_token=source["source_token"],
        witness_kit_lot="L2", expected_witness_source_token=witness["source_token"], analysis_model=old_model,
        pdf_bytes=report.pdf_bytes, pdf_sha256=report.pdf_sha256, algorithm_id=old_model["algorithm_id"], renderer_id=report.renderer_id,
        context=MutationContext("RR", "legacy-v1-close"))
    before = get_report_evidence(spec, lot_version_id=closed["version_id"])
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
    assert "sd_reference_context" not in archived.model
    destination = tmp_path / "legacy-v1-export.pdf"
    services.results.export_qc_report(detail.case, evidence_lot_version_id=closed["version_id"], destination=destination)
    assert destination.read_bytes() == before["pdf_bytes"] == report.pdf_bytes
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
    closed = services.results.close_qc_lot(detail, analysis, witnesses[0], operator_initials="RR", request_id="real-close")
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
        services.results.close_qc_lot(detail, analysis, witness, operator_initials="RR", request_id="failed-render")
    assert get_lot(spec, detail.case.lot_key) == original
    def racing_renderer(_analysis):
        with sqlite3.connect(spec["path"]) as conn:
            conn.execute("UPDATE runs SET payload_json=? WHERE id=1", (json.dumps(payload(I1="43")),))
        raw = b"%PDF-1.4\nsynthetic render result\n%%EOF"
        return QCPdfReport(raw, hashlib.sha256(raw).hexdigest(), _analysis.model_sha256, _analysis.to_dict()["renderer_id"], 1)
    monkeypatch.setattr(owner, "render_analysis_pdf", racing_renderer)
    with pytest.raises(QualityControlApplicationError, match="geändert|anderen Quellen"):
        services.results.close_qc_lot(detail, analysis, witness, operator_initials="RR", request_id="race-render")
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
    assert model["algorithm_id"] == "arev2-qc-analysis-v2" and series["qmma"]["limit_status"] == "exceeded"
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
        assert "QMMA-Bewertung: Grenze überschritten" in readable and "Diagrammlegende" not in readable
        spans = json.loads(geometry.read_text(encoding="utf-8"))
        raw_column = "".join(span["text"] for span in spans if abs(span["bbox"][0] - 39) < 0.5)
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
        assert str(view._qc_close.cget("state")) == "normal" and str(view._qc_export.cget("state")) == "disabled"
        assert view._qc_close.winfo_viewable() and view._qc_close.winfo_height() > 10
        assert view._qc_close.winfo_rooty() + view._qc_close.winfo_height() <= root.winfo_rooty() + root.winfo_height()
        assert len(view._qc_chart_hits) == 2 and "QMMA: 2" in view._qc_statistics.cget("text")
        def axis_labels():
            items = sorted(view._qc_canvas.find_withtag("qc-x-axis"), key=lambda item: view._qc_canvas.coords(item)[0])
            return tuple(view._qc_canvas.itemcget(item, "text") for item in items)
        def expected_labels():
            base = datetime(2026, 1, 1)
            return tuple((base + timedelta(seconds=round((bound - base.toordinal()) * 86400))).strftime("%d.%m.%Y %H:%M")
                         for bound in view._qc_chart_range[:2])
        initial_labels = axis_labels()
        assert initial_labels == ("31.12.2025 22:48", "02.01.2026 01:12") == expected_labels()
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
        assert axis_labels() != zoomed_labels and axis_labels() == expected_labels()
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


def test_close_shell_defers_witness_reads_and_pdf_work_and_keeps_explicit_choice(tmp_path: Path, monkeypatch):
    spec, _ = fixture(tmp_path)
    services = services_for(tmp_path, spec)
    detail = _open_controller_lot(services)
    analysis = services.results.get_qc_analysis(detail)
    add_run(spec, 3, lot="L2", data=payload("2026-02-01"))
    app = _make_app_stub(services=services)
    app._qc_source_generation, app._qc_source_latest = 0, None
    shown, reads, closes = [], [], []
    app._views["statistics"] = SimpleNamespace(selected_qc_detail=lambda: detail, selected_qc_analysis=lambda: analysis, selected_qc_case=lambda: detail.case)
    original = services.results.list_qc_close_witnesses
    services.results.list_qc_close_witnesses = lambda value: reads.append(value) or original(value)
    services.results.close_qc_lot = lambda *args, **kwargs: closes.append((args, kwargs)) or {}
    monkeypatch.setattr(dialogs, "show_qc_close_dialog", lambda *args, **kwargs: shown.append((args, kwargs)))
    app._close_qc_lot()
    assert not reads and not closes and not shown
    app._task_runner.invoke_success()
    assert len(reads) == len(shown) == 1 and not closes
    witnesses = shown[0][0][2]
    assert witnesses[0].case.kit_lot == "L2"
    dialog = SimpleNamespace(save_button=SimpleNamespace(configure=lambda **kwargs: None))
    shown[0][1]["on_submit"](witnesses[0], "RR", dialog)
    assert not closes and app._task_runner.submissions[-1][0] == "qc-write"
    app._task_runner.submissions[-1][1]()
    assert closes[0][0] == (detail, analysis, witnesses[0])
    assert closes[0][1]["operator_initials"] == "RR" and closes[0][1]["request_id"]


def test_export_shell_captures_archived_version_and_defers_io(tmp_path: Path, monkeypatch):
    from interfaces.tk import test_app

    spec, _ = fixture(tmp_path)
    services = services_for(tmp_path, spec)
    detail = _open_controller_lot(services)
    analysis = replace(services.results.get_qc_analysis(detail), evidence_lot_version_id=123)
    app = _make_app_stub(services=services)
    app._qc_source_generation = 7
    flag = [False]
    app._views["statistics"] = SimpleNamespace(selected_qc_analysis=lambda: analysis,
        _qc_include_explanations=SimpleNamespace(get=lambda: flag[0]))
    destination = str(tmp_path / "selected.pdf")
    monkeypatch.setattr(test_app.filedialog, "asksaveasfilename", lambda **kwargs: destination)
    exports = []
    services.results.export_qc_report = lambda *args, **kwargs: exports.append((args, kwargs)) or {}
    app._export_qc_report()
    flag[0] = True
    assert not exports and app._task_runner.submissions[-1][0] == "qc-export"
    app._task_runner.submissions[-1][1]()
    assert exports == [((analysis.case,), {"evidence_lot_version_id": 123, "destination": destination, "include_explanations": False})]
    assert not Path(destination).exists()
