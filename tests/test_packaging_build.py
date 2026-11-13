from __future__ import annotations

import importlib.util
import json
import hashlib
import subprocess
from types import SimpleNamespace
import runpy
from pathlib import Path

import pytest


def _load_build_onedir():
    module_path = Path(__file__).resolve().parents[1] / "packaging" / "build_onedir.py"
    spec = importlib.util.spec_from_file_location("build_onedir", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_onedir_entry_point_is_test_app_main() -> None:
    build = _load_build_onedir()
    assert build.ENTRY_POINT.name == "test_app_main.py"


def test_frozen_child_dispatch_happens_before_ui_import(monkeypatch) -> None:
    import builtins
    import multiprocessing

    entry = Path(__file__).resolve().parents[1] / "test_app_main.py"
    original_import = builtins.__import__
    ui_imported = []

    def import_checked(name, *args, **kwargs):
        if name == "interfaces.tk.test_app":
            ui_imported.append(name)
        return original_import(name, *args, **kwargs)

    def child_dispatch():
        raise SystemExit(0)

    monkeypatch.setattr(builtins, "__import__", import_checked)
    monkeypatch.setattr(multiprocessing, "freeze_support", child_dispatch)
    with pytest.raises(SystemExit) as stopped:
        runpy.run_path(str(entry), run_name="__main__")
    assert stopped.value.code == 0
    assert ui_imported == []


def test_build_onedir_required_imports_include_test_app_modules() -> None:
    build = _load_build_onedir()
    required = set(build.REQUIRED_IMPORTS)
    assert "interfaces.tk.test_app" in required
    assert "rule_editor_main" in required
    assert "src.assaycandidate.api" in required
    assert "src.jobqueue.api" in required
    assert "src.testui.api" in required
    assert "src.rulesuite.api" in required
    assert "gui_min_ext" not in required


def test_build_onedir_desktop_runtime_manifest_is_preflight_required() -> None:
    build = _load_build_onedir()
    required = set(build.REQUIRED_IMPORTS)
    for module_name in build.DESKTOP_RUNTIME_IMPORTS:
        assert module_name in required


def test_build_onedir_desktop_runtime_manifest_is_pyinstaller_hidden_import() -> None:
    build = _load_build_onedir()
    hidden = set(build.PYINSTALLER_HIDDEN_IMPORTS)
    for module_name in build.DESKTOP_RUNTIME_IMPORTS:
        assert module_name in hidden
    assert "rule_editor_main" in hidden
    assert "fitz" in hidden
    assert "pymupdf" in hidden
    assert "openpyxl" in hidden


def test_build_onedir_desktop_runtime_imports_are_importable() -> None:
    build = _load_build_onedir()
    for module_name in build.DESKTOP_RUNTIME_IMPORTS:
        importlib.import_module(module_name)


def test_build_onedir_rules_copy_excludes_drafts(tmp_path: Path) -> None:
    build = _load_build_onedir()
    project = tmp_path / "proj"
    rules = project / "rules"
    drafts = rules / "drafts"
    drafts.mkdir(parents=True)
    (rules / "index.json").write_text(json.dumps({"assays": []}), encoding="utf-8")
    (drafts / "sample.draft.json").write_text("{}", encoding="utf-8")

    app_dir = tmp_path / "dist" / build.APP_NAME
    app_dir.mkdir(parents=True)
    build.APP_DIR = app_dir
    build.RULES_SOURCE = rules
    build._prepare_runtime_tree()

    assert (app_dir / "rules" / "index.json").is_file()
    assert not (app_dir / "rules" / "drafts").exists()


def _synthetic_project(tmp_path):
    build = _load_build_onedir()
    build.PROJECT_ROOT = tmp_path
    build.ENTRY_POINT = tmp_path / "test_app_main.py"
    build.RULES_SOURCE = tmp_path / "rules"
    build.DIST_ROOT = tmp_path / "packaging" / "dist_output"
    build.WORK_ROOT = tmp_path / "packaging" / "build_work"
    build.APP_DIR = build.DIST_ROOT / build.APP_NAME
    build.ZIP_PATH = build.DIST_ROOT / f"{build.APP_NAME}.zip"
    for path, raw in {
        "pyproject.toml": b'[project]\nversion="2.0.0"\n', "README.md": b"synthetic project\n",
        "test_app_main.py": b"# synthetic entry\r\n", "src/owner/api.py": b"# synthetic code\r\n",
        "packaging/build_onedir.py": b"# synthetic builder\r\n", "rules/index.json": b'{"assays":[]}',
        "rules/runtime.json": b"{}", "rules/drafts/private.json": b"{}", "jobs/private.json": b"{}",
    }.items():
        destination = tmp_path / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)
    return build


def test_qc_spawn_modules_are_in_both_canonical_import_manifests():
    build = _load_build_onedir()
    for name in ("src.qualitycontrol.api", "src.qualitycontrol.pdf_report"):
        assert name in build.REQUIRED_IMPORTS and name in build.PYINSTALLER_HIDDEN_IMPORTS


def test_fingerprint_covers_raw_code_and_runtime_rules_not_private_data(tmp_path):
    build = _synthetic_project(tmp_path)
    before = build._product_inputs()
    paths = {item["path"] for item in before}
    assert {"src/owner/api.py", "packaging/build_onedir.py", "pyproject.toml", "rules/runtime.json"}.issubset(paths)
    assert "jobs/private.json" not in paths and "rules/drafts/private.json" not in paths
    entry = next(item for item in before if item["path"] == "src/owner/api.py")
    assert entry["sha256"] == hashlib.sha256(b"# synthetic code\r\n").hexdigest()
    assert entry["sha256"] != hashlib.sha256(b"# synthetic code\n").hexdigest()
    (tmp_path / "jobs" / "private.json").write_bytes(b"private changed")
    assert build._fingerprint(build._product_inputs()) == build._fingerprint(before)
    (tmp_path / "src" / "new.py").write_bytes(b"# new untracked product code")
    assert build._fingerprint(build._product_inputs()) != build._fingerprint(before)


def test_nested_runtime_directories_are_not_inputs_but_code_assets_and_rules_are(tmp_path):
    build = _synthetic_project(tmp_path)
    runtime = []
    for index, folder in enumerate(("src/owner/jobs", "interfaces/tk/JOBS", "rule_editor/work/locks",
            "src/owner/input", "interfaces/tk/output", "rule_editor/storage", "src/owner/__pycache__",
            "interfaces/tk/.tmp", "rule_editor/.pytest_cache", "src/owner/build", "interfaces/tk/dist")):
        path = tmp_path / folder / f"local-{index}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"local runtime data")
        runtime.append(path)
    product = [tmp_path / relative for relative in ("src/runtime/api.py", "src/owner/jobs.py",
        "interfaces/tk/assets/theme.json", "rule_editor/assets/help.md", "rules/runtime.json")]
    for path in product:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"static product input")
    preserved = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in runtime}
    initial = build._product_inputs()
    selected = {item["path"] for item in initial}
    assert not {path.relative_to(tmp_path).as_posix() for path in runtime}.intersection(selected)
    assert {path.relative_to(tmp_path).as_posix() for path in product}.issubset(selected)
    assert {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in runtime} == preserved
    for path in runtime:
        path.write_bytes(b"changed local runtime data")
    changed_runtime = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in runtime}
    assert build._fingerprint(build._product_inputs()) == build._fingerprint(initial)
    assert {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in runtime} == changed_runtime
    for path in product:
        previous = build._fingerprint(build._product_inputs())
        path.write_bytes(path.read_bytes() + b" changed")
        assert build._fingerprint(build._product_inputs()) != previous
    previous = build._fingerprint(build._product_inputs())
    fresh = tmp_path / "interfaces/tk/new_untracked_view.py"
    fresh.write_bytes(b"# new product code without a Git index")
    assert build._fingerprint(build._product_inputs()) != previous


def test_product_input_escape_is_rejected_before_external_payload_read(tmp_path, monkeypatch):
    build = _synthetic_project(tmp_path / "project")
    link = build.PROJECT_ROOT / "src/owner/escape.py"
    link.write_bytes(b"# product link placeholder")
    outside = tmp_path / "outside.py"
    outside.write_bytes(b"private outside payload")
    resolve, read = Path.resolve, Path.read_bytes
    # Exercise the result of a Windows symlink/junction without requiring the
    # optional machine privilege to create links in this unit-test process.
    monkeypatch.setattr(Path, "resolve", lambda path, *args, **kwargs:
        outside if path == link else resolve(path, *args, **kwargs))
    def checked_read(path):
        assert path != outside, "An escaped input must be rejected before reading"
        return read(path)
    monkeypatch.setattr(Path, "read_bytes", checked_read)
    with pytest.raises(SystemExit, match="escapes the project root"):
        build._product_inputs()


def test_manifest_records_real_base_dirty_inputs_and_no_local_paths(tmp_path, monkeypatch):
    build = _synthetic_project(tmp_path)
    monkeypatch.setattr(build, "_git_identity", lambda: ("5" * 40, True))
    monkeypatch.setattr(build.importlib.metadata, "version", lambda _name: "synthetic-dependency")
    inputs = build._product_inputs()
    info = build._make_build_info(inputs)
    assert info["version"] == "2.0.0" and info["base_commit"] == "5" * 40
    assert info["dirty_snapshot"] and info["source_identity"] == "dirty-snapshot"
    assert info["source_tree_fingerprint"] == build._fingerprint(inputs)
    assert str(tmp_path) not in json.dumps(info) and all(not Path(item["path"]).is_absolute() for item in info["inputs"])
    build.APP_DIR.mkdir(parents=True)
    build._write_build_info(info)
    assert json.loads((build.APP_DIR / "build-info.json").read_text(encoding="utf-8")) == info


def test_failed_canonical_pytest_prevents_every_cleanup_and_build(tmp_path, monkeypatch):
    build = _synthetic_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(build, "_parse_args", lambda: SimpleNamespace(diet_experiment=False))
    monkeypatch.setattr(build, "REQUIRED_IMPORTS", [])
    import src.ruleresolver.api as rules
    monkeypatch.setattr(rules, "validate_rules_integrity", lambda *_args: {})
    events = []
    def failed_tests(command, **kwargs):
        assert command[1:4] == ["-m", "pytest", "tests"]
        assert "faulthandler_timeout=60" in command
        raise subprocess.CalledProcessError(1, command)
    monkeypatch.setattr(build, "_run", failed_tests)
    monkeypatch.setattr(build, "_clean_outputs", lambda: events.append("cleanup"))
    monkeypatch.setattr(build, "_run_pyinstaller", lambda **kwargs: events.append("build"))
    with pytest.raises(subprocess.CalledProcessError):
        build.main()
    assert events == []


def test_cleanup_is_limited_to_three_exact_targets_and_preserves_deploy_smoke(tmp_path):
    build = _synthetic_project(tmp_path)
    for target in (build.WORK_ROOT, build.APP_DIR):
        target.mkdir(parents=True)
        (target / "old.dat").write_bytes(b"old output")
    build.ZIP_PATH.write_bytes(b"old zip")
    smoke = tmp_path / "packaging" / "deploy_smoke" / "keep.dat"
    smoke.parent.mkdir(parents=True)
    smoke.write_bytes(b"preserve")
    build._clean_outputs()
    assert smoke.read_bytes() == b"preserve"
    assert build.WORK_ROOT.is_dir() and not list(build.WORK_ROOT.iterdir())
    assert not build.APP_DIR.exists() and not build.ZIP_PATH.exists()
    build.WORK_ROOT = tmp_path / "unexpected"
    with pytest.raises(SystemExit, match="three authorized"):
        build._clean_outputs()
