from __future__ import annotations

import importlib.util
import json
from pathlib import Path


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
