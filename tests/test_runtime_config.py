from pathlib import Path

from src.runtime.api import load_runtime_config


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
