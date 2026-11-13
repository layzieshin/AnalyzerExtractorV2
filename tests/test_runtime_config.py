from pathlib import Path

import pytest

from src.processing.api import ProcessingConfig
from src.runtime.api import RuntimeConfig, load_runtime_config


@pytest.mark.parametrize("mode", ["both", "excel", "sqlite", "invalid", ""])
def test_all_runtime_and_worker_modes_are_effectively_sqlite(tmp_path: Path, monkeypatch, mode: str):
    monkeypatch.setenv("ARE_OUTPUT_MODE", mode)
    runtime = load_runtime_config(tmp_path)
    for cfg in (runtime, RuntimeConfig(output_mode=mode), ProcessingConfig(output_mode=mode)):
        assert cfg.output_mode == "sqlite"
    assert runtime.enable_excel is False
    assert runtime.enable_sqlite is True


def test_runtime_config_reads_device_id_and_watch_stable_window(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ARE_DEVICE_ID", "analyzer_i_1")
    monkeypatch.setenv("ARE_WATCH_STABLE_WINDOW_S", "2.5")

    cfg = load_runtime_config(tmp_path)

    assert cfg.device_id == "analyzer_i_1"
    assert cfg.watch_stable_window_s == 2.5


def test_runtime_config_empty_device_and_invalid_stable_window_fall_back(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ARE_DEVICE_ID", " ")
    monkeypatch.setenv("ARE_WATCH_STABLE_WINDOW_S", "bad")

    cfg = load_runtime_config(tmp_path)

    assert cfg.device_id is None
    assert cfg.watch_stable_window_s == 1.0


def test_source_build_version_belongs_to_code_not_are_home(tmp_path: Path, monkeypatch):
    import src.runtime.config as owner
    from src.runtime.api import get_build_info

    code, data = tmp_path / "code", tmp_path / "data"
    (code / "src" / "runtime").mkdir(parents=True)
    data.mkdir()
    (code / "pyproject.toml").write_text('[project]\nversion="2.0.0"\n', encoding="utf-8")
    (data / "pyproject.toml").write_text('[project]\nversion="99.0.0"\n', encoding="utf-8")
    monkeypatch.setattr(owner, "__file__", str(code / "src" / "runtime" / "config.py"))
    monkeypatch.setattr(owner.sys, "frozen", False, raising=False)
    monkeypatch.setenv("ARE_HOME", str(data))
    result = get_build_info()
    assert result["version"] == "2.0.0" and result["mode"] == "source"
    assert result["base_commit"] == "UNAVAILABLE" and result["source_tree_fingerprint"] == ""
    assert not (data / "build-info.json").exists()


def test_frozen_build_info_is_beside_exe_even_with_external_data_root(tmp_path: Path, monkeypatch):
    import json
    import src.runtime.config as owner
    from src.runtime.api import get_build_info

    program, data = tmp_path / "program", tmp_path / "data"
    program.mkdir()
    data.mkdir()
    (program / "build-info.json").write_text(json.dumps({"version": "2.0.0", "source_tree_fingerprint": "captured-source", "dirty_snapshot": True}), encoding="utf-8")
    (data / "build-info.json").write_text('{"version":"99.0.0"}', encoding="utf-8")
    monkeypatch.setattr(owner.sys, "frozen", True, raising=False)
    monkeypatch.setattr(owner.sys, "executable", str(program / "AnalyzerResultExtractorV2.exe"))
    monkeypatch.setenv("ARE_HOME", str(data))
    result = get_build_info()
    assert result["version"] == "2.0.0" and result["mode"] == "frozen" and result["source_tree_fingerprint"] == "captured-source"
    (program / "build-info.json").unlink()
    result = get_build_info()
    assert result["version"] == "UNKNOWN" and result["status"] == "unavailable"
