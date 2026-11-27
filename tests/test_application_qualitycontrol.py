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


@pytest.mark.parametrize("width,height,scale", [(1420, 930, 1.0), (960, 620, 1.25)])
def test_settings_native_four_tabs_real_inventory_and_unchanged_draft(tmp_path, monkeypatch, width, height, scale):
    import tkinter.font as tkfont
    from interfaces.tk.test_app import AnalyzerDesktopApp
    from interfaces.tk import desktop_theme
    from test_desktop_ui_v21 import _fake_services
    spec, profile = fixture(tmp_path)
    services = services_for(tmp_path, spec)
    state, inventory = services.settings.get_qc_configuration(), services.settings.get_device_inventory()
    persisted = replace(services.settings.load(), watch_input_path=r"C:\Labor\Eingang", watch_backup_path=r"C:\Labor\Archiv", operator_initials="MK")
    fake = _fake_services()
    fake.settings.load = lambda: persisted
    fake.settings.get_device_inventory = lambda: inventory
    original_theme = desktop_theme.configure_desktop_theme
    scaling_state = []
    def scaled_theme(root):
        scaling_state.append((root, float(root.tk.call("tk", "scaling"))))
        root.tk.call("tk", "scaling", (4 / 3) * scale)
        return original_theme(root)
    monkeypatch.setattr(desktop_theme, "configure_desktop_theme", scaled_theme)
    before = Path(spec["path"]).read_bytes()
    try:
        app = AnalyzerDesktopApp(project_root=tmp_path, services=fake)
    except BaseException as exc:
        if scaling_state:
            failed_root, previous_scaling = scaling_state[0]
            try:
                failed_root.tk.call("tk", "scaling", previous_scaling)
            except tk.TclError:
                pass
            try:
                failed_root.destroy()
            except tk.TclError:
                pass
        if isinstance(exc, tk.TclError):
            pytest.skip(f"Tk unavailable: {exc}")
        raise
    try:
        app._task_runner.shutdown_runner()
        app.tk.call("tk", "scaling", (4 / 3) * scale)
        app.geometry(f"{width}x{height}")
        app.show_view("settings", refresh=False)
        view = app._views["settings"]
        view.render_settings(persisted, devices=inventory.devices, timing=services.settings.get_watch_timing())
        view.render_qc_configuration(state, assay_names={"A": "ANA Screen IgG"})
        intents = []
        view._on_manage_devices = lambda: intents.append(("devices", view.take_qc_editor_intent("devices")))
        view._on_manage_profiles = lambda: intents.append(("profiles", view.take_qc_editor_intent("profiles")))
        for _ in range(5):
            app.update()
        assert tuple(view._tabs.tab(tab, "text") for tab in view._tabs.tabs()) == ("Import", "Geräte", "Prüfprofile", "Erweitert")
        style = ttk.Style(app)
        for tab_state in ("selected", "!selected"):
            assert tuple(map(int, app.tk.splitlist(style.lookup("Settings.TNotebook.Tab", "padding", (tab_state,))))) == (12, 8, 12, 8)
        assert view._card._rounded and not view.is_dirty()
        assert view.collect_settings(device_id_map={item.choice_label: item.device_id for item in inventory.devices}) == persisted
        if width == 1420:
            assert view._input_entry.winfo_rooty() == view._backup_entry.winfo_rooty()
            assert abs(view._input_entry.winfo_width() - view._backup_entry.winfo_width()) <= 2
            assert view._card.winfo_rooty() + view._card.winfo_height() < app.winfo_rooty() + height - 80
            assert view._settings_canvas.yview() == (0.0, 1.0)
        else:
            assert view._backup_entry.winfo_rooty() > view._input_entry.winfo_rooty()
        assert view._input_pick.winfo_width() >= tkfont.Font(app, font=("Segoe UI", 9)).measure("Eingabeordner auswählen")
        assert view._btn_output.winfo_manager()
        for key in ("devices", "profiles", "advanced"):
            view._tabs.select(view._panels[key])
            for _ in range(5):
                app.update()
            assert not view._btn_output.winfo_manager()
            assert bool(view._btn_save.winfo_manager()) is (key != "profiles")
            assert view._card.winfo_rooty() + view._card.winfo_height() <= app.winfo_rooty() + height
            panel = view._panels[key]
            if panel.body.winfo_reqheight() <= panel._canvas.winfo_height():
                assert panel._canvas.yview() == (0.0, 1.0)
            if key in ("devices", "profiles"):
                tree = view._device_tree if key == "devices" else view._profile_tree
                assert tree.xview() == tree.yview() == (0.0, 1.0)
                font = tkfont.Font(app, font=ttk.Style(app).lookup("Settings.Treeview.Heading", "font"))
                for column in tree.cget("columns"):
                    assert tree.column(column, "width") >= font.measure(tree.heading(column, "text")) + 24
                row = tree.get_children()[0]
                tree.selection_set(row)
                app.update()
                (view._edit_device if key == "devices" else view._edit_profile).invoke()
                assert intents[-1] == (key, (False, row, state.store_path))
                (view._new_device if key == "devices" else view._new_profile).invoke()
                assert intents[-1] == (key, (True, None, state.store_path))
                box = tree.bbox(row)
                assert box and tree.winfo_rooty() + box[1] + box[3] <= app.winfo_rooty() + height
            if key == "advanced":
                assert view._sqlite_entry.winfo_rooty() == view._sqlite_pick.winfo_rooty()
                assert view._sqlite_entry.winfo_height() == view._sqlite_pick.winfo_height()
        assert not view.is_dirty()
        assert view._device_status.cget("text").startswith("1 Gerät im ")
        assert view._profile_tree.item(str(profile["version_id"]), "values")[1] == "ANA Screen IgG"
        view.render_qc_configuration(state, assay_names={})
        assert view._profile_tree.item(str(profile["version_id"]), "values")[1] == "Assayname fehlt"
        view.render_qc_configuration(state, assay_names={"A": "ANA Screen IgG"})
        view._tabs.select(view._panels["profiles"])
        view._var_operator_initials.set("RF")
        for _ in range(3):
            app.update()
        assert view.is_dirty() and view._btn_save.cget("text") == "Allgemeine Änderungen speichern"
        assert view._btn_save.winfo_manager() and not view._btn_output.winfo_manager()
        assert view.collect_settings(device_id_map={item.choice_label: item.device_id for item in inventory.devices}).operator_initials == "RF"
        view._tabs.select(view._panels["import"])
        view._backup_clear.invoke()
        assert view._var_watch_backup.get() == "" and view.is_dirty()
        assert "erforderlich" in view._archive_hint.cget("text") and Path(spec["path"]).read_bytes() == before
        view.invalidate_qc_configuration()
        assert not view._device_tree.get_children() and not view._profile_tree.get_children()
        assert str(view._new_device.cget("state")) == str(view._edit_profile.cget("state")) == "disabled"
    finally:
        try:
            if scaling_state:
                app.tk.call("tk", "scaling", scaling_state[0][1])
        finally:
            app.destroy()


@pytest.mark.parametrize("kind", ["devices", "profiles", "migrate"])
def test_settings_qc_open_dialog_rejects_store_aba_before_write(tmp_path, monkeypatch, kind):
    spec, _ = fixture(tmp_path)
    services = services_for(tmp_path, spec)
    state = replace(services.settings.get_qc_configuration(), legacy_source_sha256="synthetic-source")
    services.settings.get_qc_configuration = lambda: state
    services.rules.list_inventory = lambda kind="all": [SimpleNamespace(assay_key="A", assay_name="ANA Screen IgG")]
    services.rules.list_fields = lambda _key: ["DATE", "I1", "S1", "N1", "X1"]
    app = _make_app_stub(current_view="settings", services=services)
    app._qc_configuration_generation = 0
    opened, errors = [], []
    app._show_error_dialog = lambda *_args: errors.append(_args[-1])
    dialog = SimpleNamespace(save_button=SimpleNamespace(configure=lambda **_kwargs: None))
    def show(_parent, _state=None, **kwargs):
        opened.append(kwargs["on_submit"])
    monkeypatch.setattr(dialogs, "show_qc_inventory_dialog", show)
    monkeypatch.setattr(dialogs, "show_qc_profile_dialog", show)
    monkeypatch.setattr(dialogs, "show_qc_initials_dialog", show)
    app._open_qc_configuration(kind)
    app._task_runner.invoke_success()
    assert len(opened) == 1
    before = Path(spec["path"]).read_bytes()
    app._store_generation += 2  # A -> B -> A; same path and IDs, different authority.
    if kind == "devices":
        opened[0](state.inventory["snapshot"], "RR", dialog)
    elif kind == "profiles":
        opened[0](state.profiles[0]["snapshot"], state.profiles[0]["version_id"], "RR", dialog)
    else:
        opened[0]("RR", "", dialog)
    assert errors and "gewechselt" in errors[-1]
    assert len(app._task_runner.submissions) == 1
    assert Path(spec["path"]).read_bytes() == before


@pytest.mark.parametrize("kind", ["devices", "profiles"])
def test_settings_stale_editor_target_never_falls_back_to_another_record(tmp_path, monkeypatch, kind):
    spec, _ = fixture(tmp_path)
    services = services_for(tmp_path, spec)
    services.rules.list_inventory = lambda kind="all": [SimpleNamespace(assay_key="A", assay_name="ANA Screen IgG")]
    services.rules.list_fields = lambda _key: ["DATE", "I1", "S1", "N1", "X1"]
    app = _make_app_stub(current_view="settings", services=services)
    app._qc_configuration_generation = 0
    app._views["settings"].take_qc_editor_intent = lambda _kind: (False, "stale-stable-id", str(Path(spec["path"]).resolve()))
    opened = []
    monkeypatch.setattr(dialogs, "show_qc_inventory_dialog", lambda *_args, **_kwargs: opened.append("devices"))
    monkeypatch.setattr(dialogs, "show_qc_profile_dialog", lambda *_args, **_kwargs: opened.append("profiles"))
    app._open_qc_configuration(kind)
    app._task_runner.invoke_success()
    assert not opened and app._info_shown
    assert len(app._task_runner.submissions) == 1


@pytest.mark.parametrize("width,height,scale", [(1420, 930, 1.0), (960, 620, 1.25)])
def test_settings_dialogs_edit_exact_initial_identity_and_new_is_unsaved(tmp_path, width, height, scale):
    spec, profile = fixture(tmp_path)
    services = services_for(tmp_path, spec)
    state = services.settings.get_qc_configuration()
    changed_inventory = copy.deepcopy(state.inventory)
    changed_inventory["snapshot"]["devices"].insert(0, {"device_id": "other", "display_name": "Anderes Gerät", "serial_number": "OTHER", "active": True, "incomplete": False})
    state = replace(state, inventory=changed_inventory)
    before = Path(spec["path"]).read_bytes()
    root = _root()
    previous_scaling = None
    def field(parent, label):
        children = parent.winfo_children()
        if any(isinstance(child, ttk.Label) and child.cget("text") == label for child in children):
            return next(child for child in children if isinstance(child, (ttk.Entry, ttk.Combobox)))
        return next((found for child in children if (found := field(child, label)) is not None), None)
    try:
        previous_scaling = float(root.tk.call("tk", "scaling"))
        root.tk.call("tk", "scaling", (4 / 3) * scale)
        root.geometry(f"{width}x{height}")
        submissions = []
        for create in (False, True):
            dialog = dialogs.show_qc_inventory_dialog(root, state, initials="RR", initial_device_id=None if create else "dev", create_new=create,
                on_submit=lambda *args: submissions.append(args))
            dialog.geometry(f"{min(820, width - 80)}x{min(650, height - 80)}")
            root.update()
            assert field(dialog, "Gerätename").get() == ("" if create else "Laborgerät")
            assert dialog.save_button.winfo_rooty() + dialog.save_button.winfo_height() <= dialog.winfo_rooty() + dialog.winfo_height()
            dialog.save_button.invoke()
            expected = submissions[-1][0]
            assert len(expected["devices"]) == (3 if create else 2)
            assert next(row for row in expected["devices"] if row["device_id"] == "dev")["display_name"] == "Laborgerät"
            dialog.destroy()
            dialog = dialogs.show_qc_profile_dialog(root, state, initials="RR", assays={"ANA Screen IgG": "A"}, field_choices={"A": ["DATE", "I1", "S1", "N1", "X1"]},
                initial_version_id=None if create else profile["version_id"], on_submit=lambda *args: submissions.append(args))
            dialog.geometry(f"{min(940, width - 80)}x{min(790, height - 80)}")
            root.update()
            assert field(dialog, "Profilname").get() == ("" if create else profile["snapshot"]["name"])
            assert field(dialog, "Prüfprofil").get() == ("Neues Prüfprofil" if create else f"{profile['snapshot']['name']} · Fassung {profile['version_id']}")
            assert dialog.save_button.winfo_rooty() + dialog.save_button.winfo_height() <= dialog.winfo_rooty() + dialog.winfo_height()
            dialog.save_button.invoke()
            assert submissions[-1][1] == (0 if create else profile["version_id"])
            dialog.destroy()
        assert Path(spec["path"]).read_bytes() == before
    finally:
        try:
            if previous_scaling is not None:
                root.tk.call("tk", "scaling", previous_scaling)
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


@pytest.mark.parametrize("width,height,scale", [(1420, 930, 1.0), (960, 620, 1.25)])
def test_statistics_mockup_native_layout_keeps_bound_qc_and_reachable_sections(tmp_path: Path, width, height, scale):
    import tkinter.font as tkfont
    from interfaces.tk.test_app import AnalyzerDesktopApp
    from test_desktop_ui_v21 import _fake_services
    from src.application.api import QCReportVersion

    spec, _ = fixture(tmp_path)
    services = services_for(tmp_path, spec)
    detail = _open_controller_lot(services)
    case = replace(detail.case, assay_name="ANA Screen IgG", device_name="Analyzer 1")
    detail = replace(detail, case=case)
    analysis = replace(services.results.get_qc_analysis(detail), case=case)
    original_model = analysis.model_json, analysis.model_sha256
    try:
        app = AnalyzerDesktopApp(project_root=tmp_path, services=_fake_services())
    except tk.TclError as exc:
        pytest.skip(f"Tk unavailable: {exc}")
    previous_scaling = None
    try:
        app._task_runner.shutdown_runner()
        previous_scaling = float(app.tk.call("tk", "scaling"))
        app.tk.call("tk", "scaling", (4 / 3) * scale)
        app.geometry(f"{width}x{height}")
        app.show_view("statistics", refresh=False)
        view = app._views["statistics"]
        view._on_qc_selected = lambda: None
        for _ in range(5):
            app.update()
        assert int(view._qc_tree.cget("height")) == 1
        assert view._qc_panel._canvas.yview() == (0.0, 1.0)
        hint_font = tkfont.Font(app, font=ttk.Style(app).lookup("Statistics.Muted.TLabel", "font"))
        assert view._empty_hint.winfo_reqheight() <= hint_font.metrics("linespace") + 4
        style = ttk.Style(app)
        assert style.lookup("Statistics.TCombobox", "fieldbackground", ("readonly",)) == "#ffffff"
        assert style.lookup("Statistics.TCombobox", "fieldbackground", ("disabled",)) == "#edf1f5"
        cases = (case, replace(case, lot_key="second", kit_lot="ANA-2411"),
            replace(case, lot_key="third", kit_lot="MPO-2411", assay_name="Anti-MPO IgG", state="unconfigured"),
            replace(case, lot_key="fourth", kit_lot="VD-5912", device_name="Analyzer 2", assay_name="25-OH Vitamin D", state="closed"))
        view.render_qc_lots(cases)
        assert not view._detail_card.winfo_manager() and not view._reports_card.winfo_manager()
        assert view._empty_card.winfo_manager()
        view._qc_tree.selection_set(case.lot_key)
        for _ in range(3):
            app.update()
        view.render_qc_detail(detail)
        view.render_qc_analysis(analysis, ())
        for _ in range(5):
            app.update()
        assert all(card._rounded for card in (view._lots_card, view._detail_card, view._reports_card))
        assert view._qc_tree.item(case.lot_key, "values")[1] == "ANA Screen IgG"
        assert tuple(view._qc_tree.cget("displaycolumns")) == ("lot", "assay", "device", "state")
        assert view._qc_tree.xview() == view._qc_tree.yview() == (0.0, 1.0)
        heading_font = tkfont.Font(app, font=ttk.Style(app).lookup("Statistics.Treeview.Heading", "font"))
        for column in view._qc_tree.cget("columns"):
            assert view._qc_tree.column(column, "width") >= heading_font.measure(view._qc_tree.heading(column, "text")) + 24
        if width == 1420:
            assert view._qc_tree.column("assay", "width") < view._qc_tree.winfo_width() * .55
            for column in ("lot", "device", "state"):
                assert view._qc_tree.column(column, "width") > view._qc_tree.winfo_width() * .13
        for item in view._qc_tree.get_children():
            box = view._qc_tree.bbox(item)
            assert box and box[1] + box[3] <= view._qc_tree.winfo_height()
        assert len({widget.winfo_rooty() for widget in view._filters.values()}) == 1
        assert len({widget.winfo_height() for widget in view._filters.values()}) == 1
        assert view._qc_profile_combo.winfo_rooty() == view._qc_sources_button.winfo_rooty()
        assert view._qc_profile_combo.winfo_height() == view._qc_sources_button.winfo_height()
        assert view._qc_profile_combo.winfo_width() >= 180
        assert view._qc_control_combo.winfo_rootx() == view._qc_profile_combo.winfo_rootx()
        assert view._qc_control_combo.winfo_width() == view._qc_profile_combo.winfo_width()
        assert view.selected_qc_case() == case and view.selected_qc_profile_version() == case.profile_version_id
        assert view.selected_qc_detail() is detail and view.selected_qc_analysis() is analysis
        view.set_qc_loading()
        assert view.selected_qc_profile_version() == case.profile_version_id
        assert view.selected_qc_report_version() is None and view.selected_qc_analysis() is None
        view.render_qc_detail(detail)
        view.render_qc_analysis(analysis, ())
        for _ in range(3):
            app.update()
        assert case.kit_lot in view._qc_title.cget("text") and case.assay_name in view._qc_title.cget("text")
        assert len(view._qc_chart_hits) == 2

        def show_section(widget):
            top = widget.winfo_rooty() - view._qc_panel.body.winfo_rooty()
            view._qc_panel._canvas.yview_moveto(top / view._qc_panel.body.winfo_reqheight())
            for _ in range(3):
                app.update()

        show_section(view._qc_tabs)
        view._qc_tabs.select(view._qc_values_tab)
        for _ in range(3):
            app.update()
        assert view._qc_source_tree.xview() == view._qc_source_tree.yview() == (0.0, 1.0)
        first = view._qc_source_tree.bbox(view._qc_source_tree.get_children()[0])
        assert first and view._qc_source_tree.winfo_rooty() + first[1] + first[3] <= app.winfo_rooty() + height
        view._qc_tabs.select(view._qc_westgard_tab)
        app.update()
        assert view._qc_findings.get_children() and view._qc_findings.xview() == (0.0, 1.0)
        view._qc_tabs.select(view._qc_chart_tab)
        app.update()
        assert view._qc_canvas.winfo_width() <= view._detail_card.body.winfo_width()
        view._qc_panel._canvas.yview_moveto(1)
        app.update()
        for button in (view._qc_configure, view._qc_reopen, view._qc_close, view._qc_export):
            assert button.winfo_rootx() >= app.winfo_rootx()
            assert button.winfo_rootx() + button.winfo_width() <= app.winfo_rootx() + width
            assert button.winfo_rooty() + button.winfo_height() <= app.winfo_rooty() + height
        assert view._qc_version_combo.winfo_rooty() == view._qc_export.winfo_rooty()
        assert view._qc_version_combo.winfo_height() == view._qc_export.winfo_height()
        assert view._qc_include_explanations.get() is False and view.selected_qc_report_version() is None
        archived = replace(analysis, case=replace(case, state="closed"), evidence_lot_version_id=9)
        version = QCReportVersion(case.store_path, case.lot_key, 9, "2026-11-25T12:00:00Z", case.profile_version_id,
            analysis.model_sha256, "synthetic-pdf-hash", detail.source_manifest["included_count"])
        view.render_qc_analysis(archived, (version,))
        assert view.selected_qc_report_version() == 9 and str(view._qc_export.cget("state")) == "normal"
        assert str(view._qc_close.cget("state")) == "disabled"
        assert (analysis.model_json, analysis.model_sha256) == original_model
        view._filters["assay"].select_values(("Anti-MPO IgG",))
        view._apply_qc_filters()
        assert view._qc_tree.get_children() == ("third",) and view.selected_qc_case() is None
        assert not view._detail_card.winfo_manager() and not view._reports_card.winfo_manager()
        assert view._empty_card.winfo_manager()
        assert view._qc_control.get() == view._qc_version.get() == ""
        assert view.selected_qc_report_version() is None and view.selected_qc_analysis() is None
        view._reset_qc_filters()
        assert len(view._qc_tree.get_children()) == 4
    finally:
        try:
            if previous_scaling is not None:
                app.tk.call("tk", "scaling", previous_scaling)
        finally:
            app.destroy()


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
        view._qc_panel._canvas.yview_moveto(1)
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
