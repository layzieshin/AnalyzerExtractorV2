from interfaces.tk.watch_scan import InAppWatchScanner


def test_watch_scan_observes_before_stable_window(tmp_path):
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"a")
    scanner = InAppWatchScanner()

    first = scanner.scan(tmp_path, set(), stable_window_s=1.0, now=10.0)
    second = scanner.scan(tmp_path, set(), stable_window_s=1.0, now=10.5)
    third = scanner.scan(tmp_path, set(), stable_window_s=1.0, now=11.0)

    assert first.stable_new_paths == []
    assert second.stable_new_paths == []
    assert third.stable_new_paths == [str(pdf.resolve())]


def test_watch_scan_size_or_mtime_change_resets_observation(tmp_path):
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"a")
    scanner = InAppWatchScanner()

    assert scanner.scan(tmp_path, set(), stable_window_s=1.0, now=10.0).stable_new_paths == []
    pdf.write_bytes(b"ab")
    assert scanner.scan(tmp_path, set(), stable_window_s=1.0, now=12.0).stable_new_paths == []
    assert scanner.scan(tmp_path, set(), stable_window_s=1.0, now=13.0).stable_new_paths == [str(pdf.resolve())]


def test_watch_scan_zero_stable_window_accepts_immediately(tmp_path):
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"a")

    result = InAppWatchScanner().scan(tmp_path, set(), stable_window_s=0, now=10.0)

    assert result.stable_new_paths == [str(pdf.resolve())]
    assert result.observed_count == 1


def test_watch_scan_skips_known_paths_with_normalized_key(tmp_path):
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"a")
    known = {str(tmp_path / "." / "sample.pdf")}

    result = InAppWatchScanner().scan(tmp_path, known, stable_window_s=0, now=10.0)

    assert result.stable_new_paths == []
    assert result.known_count == 1
    assert result.observed_count == 1


def test_watch_scan_ignores_non_pdfs_and_accepts_uppercase_suffix(tmp_path):
    pdf = tmp_path / "sample.PDF"
    txt = tmp_path / "sample.txt"
    pdf.write_bytes(b"a")
    txt.write_text("ignore", encoding="utf-8")

    result = InAppWatchScanner().scan(tmp_path, set(), stable_window_s=0, now=10.0)

    assert result.stable_new_paths == [str(pdf.resolve())]
    assert result.observed_count == 1


def test_watch_scan_removes_observation_for_disappeared_file(tmp_path):
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"a")
    scanner = InAppWatchScanner()

    scanner.scan(tmp_path, set(), stable_window_s=1.0, now=10.0)
    assert scanner._observations
    pdf.unlink()
    result = scanner.scan(tmp_path, set(), stable_window_s=1.0, now=11.0)

    assert result.stable_new_paths == []
    assert scanner._observations == {}


def test_watch_scan_missing_watch_dir_returns_warning(tmp_path):
    missing = tmp_path / "missing"

    result = InAppWatchScanner().scan(missing, set(), stable_window_s=1.0, now=10.0)

    assert result.stable_new_paths == []
    assert result.observed_count == 0
    assert result.warning.startswith("watch_dir_missing:")
