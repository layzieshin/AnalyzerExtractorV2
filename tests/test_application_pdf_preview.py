from __future__ import annotations

import json
import multiprocessing
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import fitz
import pytest

from src.application import pdf_preview
from src.application.api import DesktopSettings, PdfPreviewError, ReportPdfPage, ResultsController


def _pdf(path: Path, sizes: tuple[tuple[int, int], ...] = ((200, 300), (300, 200))) -> None:
    with fitz.open() as document:
        for index, (width, height) in enumerate(sizes):
            page = document.new_page(width=width, height=height)
            page.insert_text((10, 25), f"Page {index + 1}")
        document.save(path)


def test_spawned_render_from_worker_thread_has_page_count_index_and_bounded_zoom(tmp_path, monkeypatch) -> None:
    path = tmp_path / "multi.pdf"
    _pdf(path)
    parent_thread = threading.get_ident()
    original = fitz.open

    def only_main_thread(*args, **kwargs):
        assert threading.get_ident() == parent_thread, "MuPDF must never run in the application worker thread"
        return original(*args, **kwargs)

    monkeypatch.setattr(fitz, "open", only_main_thread)
    with ThreadPoolExecutor(max_workers=1) as pool:
        page = pool.submit(pdf_preview.render_pdf_page, "report-a", str(path), page_index=1, zoom=20).result(timeout=15)
    assert isinstance(page, ReportPdfPage)
    assert (page.report_id, page.page_index, page.page_count) == ("report-a", 1, 2)
    assert (page.width, page.height, page.zoom) == (900, 600, 3.0)
    assert page.image_data.startswith(b"P6\n900 600\n255\n")


def test_large_pdf_page_is_capped_before_render_allocation(tmp_path) -> None:
    path = tmp_path / "large.pdf"
    _pdf(path, ((10000, 10000),))
    page = pdf_preview.render_pdf_page("large", str(path), page_index=0, zoom=3)
    assert page.width <= pdf_preview.MAX_DIMENSION
    assert page.height <= pdf_preview.MAX_DIMENSION
    assert page.width * page.height <= pdf_preview.MAX_PIXELS
    assert len(page.image_data) <= pdf_preview.MAX_IMAGE_BYTES
    assert 0 < page.zoom < 0.25
    fitted = pdf_preview.render_pdf_page("large", str(path), page_index=0, zoom=page.zoom * 404 / page.width)
    assert fitted.width <= 406
    assert 0 < fitted.zoom < page.zoom
    assert fitted.width * fitted.height <= pdf_preview.MAX_PIXELS
    assert len(fitted.image_data) <= pdf_preview.MAX_IMAGE_BYTES


def test_automatic_fit_zoom_below_manual_floor_is_preserved(tmp_path) -> None:
    path = tmp_path / "wide.pdf"
    _pdf(path, ((2000, 1000),))
    page = pdf_preview.render_pdf_page("wide", str(path), page_index=0, zoom=0.203)
    assert page.zoom == pytest.approx(0.203)
    assert 0 < page.width <= 406
    assert page.width * page.height <= pdf_preview.MAX_PIXELS
    assert len(page.image_data) <= pdf_preview.MAX_IMAGE_BYTES


@pytest.mark.parametrize("page_index,zoom", [(-1, 1), (True, 1), (1000, 1), (1.5, 1), (0, 0), (0, -0.1), (0, float("nan")), (0, float("inf")), (0, "bad")])
def test_invalid_preview_request_fails_before_spawn(tmp_path, monkeypatch, page_index, zoom) -> None:
    monkeypatch.setattr(pdf_preview.multiprocessing, "get_context", lambda *_: pytest.fail("must not spawn"))
    with pytest.raises(PdfPreviewError):
        pdf_preview.render_pdf_page("bad", str(tmp_path / "none.pdf"), page_index=page_index, zoom=zoom)


def test_missing_corrupt_and_nonexistent_page_fail_visibly(tmp_path) -> None:
    path = tmp_path / "bad.pdf"
    with pytest.raises(PdfPreviewError, match="Quelle fehlt"):
        pdf_preview.render_pdf_page("bad", str(path), page_index=0, zoom=1)
    path.write_bytes(b"not a PDF")
    with pytest.raises(PdfPreviewError, match="beschaedigt"):
        pdf_preview.render_pdf_page("bad", str(path), page_index=0, zoom=1)
    _pdf(tmp_path / "good.pdf")
    with pytest.raises(PdfPreviewError, match="nicht vorhanden"):
        pdf_preview.render_pdf_page("bad", str(tmp_path / "good.pdf"), page_index=2, zoom=1)


def test_actual_spawn_timeout_terminates_child_and_releases_slot(tmp_path, monkeypatch) -> None:
    path = tmp_path / "timeout.pdf"
    _pdf(path)
    previous = {child.pid for child in multiprocessing.active_children()}
    monkeypatch.setattr(pdf_preview, "RENDER_TIMEOUT_S", 0.001)
    with pytest.raises(PdfPreviewError, match="Zeitlimit"):
        pdf_preview.render_pdf_page("timeout", str(path), page_index=0, zoom=1)
    assert {child.pid for child in multiprocessing.active_children()} <= previous
    assert pdf_preview._RENDER_LOCK.acquire(blocking=False)
    pdf_preview._RENDER_LOCK.release()


def test_busy_render_slot_has_bounded_wait(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(pdf_preview, "RENDER_TIMEOUT_S", 0.001)
    with pdf_preview._RENDER_LOCK:
        with pytest.raises(PdfPreviewError, match="Zeitlimit"):
            pdf_preview.render_pdf_page("busy", str(tmp_path / "unused"), page_index=0, zoom=1)


def test_pdf_size_bound_rejects_before_spawn(tmp_path, monkeypatch) -> None:
    path = tmp_path / "oversized.pdf"
    with path.open("wb") as stream:
        stream.truncate(pdf_preview.MAX_PDF_BYTES + 1)
    monkeypatch.setattr(pdf_preview.multiprocessing, "get_context", lambda *_: pytest.fail("must not spawn"))
    with pytest.raises(PdfPreviewError, match="zu gross"):
        pdf_preview.render_pdf_page("large", str(path), page_index=0, zoom=1)


class _Process:
    def __init__(self, *, target, args, daemon, mode="timeout"):
        self.args = args
        self.mode = mode
        self.alive = False
        self.exitcode = 0
        self.terminated = False
        self.closed = False

    def start(self):
        self.alive = self.mode == "timeout"
        if self.mode == "crash":
            self.exitcode = 7
        if self.mode == "invalid":
            (Path(self.args[3]) / "result.json").write_text("{}", encoding="utf-8")

    def join(self, timeout=None):
        assert timeout is not None and 0 <= timeout <= pdf_preview.RENDER_TIMEOUT_S

    def is_alive(self):
        return self.alive

    def terminate(self):
        self.terminated = True
        self.alive = False

    def kill(self):
        self.alive = False

    def close(self):
        self.closed = True


@pytest.mark.parametrize("mode,message", [("timeout", "Zeitlimit"), ("crash", "unerwartet"), ("invalid", "nicht geladen")])
def test_process_timeout_crash_or_invalid_result_fails_closed(tmp_path, monkeypatch, mode, message) -> None:
    path = tmp_path / "file.pdf"
    path.write_bytes(b"dummy")
    created = []

    def factory(**kwargs):
        process = _Process(**kwargs, mode=mode)
        created.append(process)
        return process

    monkeypatch.setattr(pdf_preview.multiprocessing, "get_context", lambda method: SimpleNamespace(Process=factory) if method == "spawn" else pytest.fail("spawn required"))
    with pytest.raises(PdfPreviewError, match=message):
        pdf_preview.render_pdf_page("report", str(path), page_index=0, zoom=1)
    assert created[0].closed
    assert created[0].terminated == (mode == "timeout")
    assert not Path(created[0].args[3]).exists()
    assert pdf_preview._RENDER_LOCK.acquire(blocking=False)
    pdf_preview._RENDER_LOCK.release()


def test_worker_empty_pdf_and_page_count_limit_fail_without_rendering(tmp_path, monkeypatch) -> None:
    for count, message in ((0, "keine Seiten"), (1001, "zu viele Seiten")):
        class Document:
            is_pdf = True
            needs_pass = False
            is_repaired = False
            page_count = count

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return None

            def load_page(self, *_):
                pytest.fail("must not load a page")

        monkeypatch.setattr(fitz, "open", lambda *_: Document())
        pdf_preview._render_pdf_worker("none", 0, 1, str(tmp_path))
        assert message in json.loads((tmp_path / "result.json").read_text())["error"]


@pytest.mark.parametrize("path_status,present,message", [("ambiguous", True, "nicht eindeutig"), ("resolved", False, "nicht gefunden")])
def test_controller_rejects_missing_or_ambiguous_report_pdf(tmp_path, monkeypatch, path_status, present, message) -> None:
    path = tmp_path / "file.pdf"
    if present:
        path.write_bytes(b"dummy")
    controller = ResultsController(tmp_path, settings_provider=lambda: DesktopSettings("both", ""))
    monkeypatch.setattr(controller, "get_report_detail", lambda _: SimpleNamespace(report_id="r", path_status=path_status, current_pdf_path=str(path), pdf_path=""))
    with pytest.raises(PdfPreviewError, match=message):
        controller.render_report_pdf_page("r")


def test_controller_uses_current_archived_path_for_every_page(tmp_path, monkeypatch) -> None:
    from src.application import results_controller

    archived = tmp_path / "archive.pdf"
    archived.write_bytes(b"dummy")
    controller = ResultsController(tmp_path, settings_provider=lambda: DesktopSettings("both", ""))
    calls = []
    monkeypatch.setattr(controller, "get_report_detail", lambda _: SimpleNamespace(report_id="r", path_status="resolved", current_pdf_path=str(archived), pdf_path="missing-original.pdf"))
    monkeypatch.setattr(results_controller, "render_pdf_page", lambda *args, **kwargs: calls.append((args, kwargs)) or "page")
    assert controller.render_report_pdf_page("r", page_index=1, zoom=1.5) == "page"
    assert calls == [(("r", str(archived)), {"page_index": 1, "zoom": 1.5})]
