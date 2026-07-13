from interfaces.tk.watch_scan import InAppWatchScanner, list_watch_pdf_paths


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


def test_watch_scan_recursive_false_finds_only_top_level_pdfs(tmp_path):
    top = tmp_path / "top.pdf"
    nested = tmp_path / "2026" / "nested.pdf"
    nested.parent.mkdir(parents=True)
    top.write_bytes(b"a")
    nested.write_bytes(b"b")

    result = InAppWatchScanner().scan(tmp_path, set(), stable_window_s=0, now=10.0, recursive=False)

    assert result.stable_new_paths == [str(top.resolve())]
    assert result.observed_count == 1


def test_watch_scan_recursive_true_finds_nested_pdfs(tmp_path):
    top = tmp_path / "top.pdf"
    nested = tmp_path / "2026" / "01" / "nested.pdf"
    nested.parent.mkdir(parents=True)
    top.write_bytes(b"a")
    nested.write_bytes(b"b")

    result = InAppWatchScanner().scan(tmp_path, set(), stable_window_s=0, now=10.0, recursive=True)

    assert sorted(result.stable_new_paths) == sorted([str(top.resolve()), str(nested.resolve())])
    assert result.observed_count == 2


def test_watch_scan_recursive_skips_excluded_dirs_case_insensitive(tmp_path):
    allowed = tmp_path / "2026" / "allowed.pdf"
    blocked = tmp_path / "processed" / "blocked.pdf"
    blocked_upper = tmp_path / "processed" / "nested" / "blocked_upper.pdf"
    allowed.parent.mkdir(parents=True)
    blocked.parent.mkdir(parents=True)
    blocked_upper.parent.mkdir(parents=True)
    allowed.write_bytes(b"a")
    blocked.write_bytes(b"b")
    blocked_upper.write_bytes(b"c")

    result = InAppWatchScanner().scan(tmp_path, set(), stable_window_s=0, now=10.0, recursive=True)

    assert result.stable_new_paths == [str(allowed.resolve())]
    assert result.observed_count == 1


def test_watch_scan_recursive_stability_window_works_in_subdirs(tmp_path):
    nested = tmp_path / "2026" / "sample.pdf"
    nested.parent.mkdir(parents=True)
    nested.write_bytes(b"a")
    scanner = InAppWatchScanner()

    first = scanner.scan(tmp_path, set(), stable_window_s=1.0, now=10.0, recursive=True)
    second = scanner.scan(tmp_path, set(), stable_window_s=1.0, now=11.0, recursive=True)

    assert first.stable_new_paths == []
    assert second.stable_new_paths == [str(nested.resolve())]


def test_list_watch_pdf_paths_returns_empty_for_missing_dir(tmp_path):
    missing = tmp_path / "missing"

    assert list_watch_pdf_paths(missing) == []
    assert list_watch_pdf_paths(missing, recursive=True) == []


def test_list_watch_pdf_paths_recursive_collects_nested_pdfs(tmp_path):
    nested = tmp_path / "2026" / "01" / "nested.pdf"
    nested.parent.mkdir(parents=True)
    nested.write_bytes(b"a")

    paths = list_watch_pdf_paths(tmp_path, recursive=True)

    assert paths == [str(nested.resolve(strict=False))]


def test_list_watch_pdf_paths_does_not_mutate_scanner_observations(tmp_path):
    nested = tmp_path / "2026" / "nested.pdf"
    nested.parent.mkdir(parents=True)
    nested.write_bytes(b"a")
    scanner = InAppWatchScanner()

    assert list_watch_pdf_paths(tmp_path, recursive=True) == [str(nested.resolve(strict=False))]
    assert scanner._observations == {}


def test_watch_scan_recursive_skips_symlink_directories(tmp_path):
    try:
        real_dir = tmp_path / "real"
        real_dir.mkdir()
        real_pdf = real_dir / "inside.pdf"
        real_pdf.write_bytes(b"a")
        link_dir = tmp_path / "linked"
        link_dir.symlink_to(real_dir, target_is_directory=True)
        top_pdf = tmp_path / "top.pdf"
        top_pdf.write_bytes(b"b")
    except (OSError, NotImplementedError) as e:
        import pytest

        pytest.skip(f"Symlink setup not supported: {e}")

    result = InAppWatchScanner().scan(tmp_path, set(), stable_window_s=0, now=10.0, recursive=True)

    assert sorted(result.stable_new_paths) == sorted([str(top_pdf.resolve()), str(real_pdf.resolve())])
    assert result.observed_count == 2
