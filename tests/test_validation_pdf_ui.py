from __future__ import annotations

import threading
import tkinter as tk
from types import SimpleNamespace

import pytest

from interfaces.tk.desktop_theme import configure_desktop_theme
from interfaces.tk.test_app import AnalyzerDesktopApp
from interfaces.tk.views.validation_view import ValidationView
from src.application import pdf_preview
from src.application.api import PdfPreviewError, ReportFieldValue, ReportPdfPage, ValidationQueueItem


def _item(report="a", run=1):
    return ValidationQueueItem(report, run, f"{report}.pdf", f"/{report}.pdf", "ASSAY", "LOT", "DEVICE", "", (ReportFieldValue("value", "42"),))


def _page(report="a", index=0, zoom=1.0):
    return ReportPdfPage(report, index, 3, zoom, 2, 3, b"P6\n2 3\n255\n" + b"\xff" * 18)


def _write_pdf(path, *, width=2000, height=1000, pages=1):
    import fitz

    with fitz.open() as document:
        for _ in range(pages):
            document.new_page(width=width, height=height)
        document.save(path)


@pytest.fixture
def opened_view():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk not available: {exc}")
    root.withdraw()
    configure_desktop_theme(root)
    requests = []
    view = ValidationView(root, on_refresh=lambda: None, on_save=lambda: None, on_open_pdf=lambda: None, on_preview=requests.append)
    yield root, view, requests
    root.destroy()


def test_embedded_pdf_navigation_zoom_and_loading_clear_previous_image(opened_view, monkeypatch):
    _root, view, requests = opened_view
    ui_thread = threading.get_ident()
    photo_image = tk.PhotoImage

    def ui_photo(*args, **kwargs):
        assert threading.get_ident() == ui_thread
        return photo_image(*args, **kwargs)

    monkeypatch.setattr(tk, "PhotoImage", ui_photo)
    view.render_cases((_item(),))
    assert "geladen" in view._lbl_pdf_status.cget("text")
    view.render_pdf_page(requests[-1], _page())
    assert view._pdf_photo is not None
    assert view._lbl_pdf_page.cget("text") == "Seite 1 / 3"
    assert str(view._btn_pdf_previous.cget("state")) == "disabled"
    view._change_pdf_page(1)
    assert view._pdf_photo is None
    assert requests[-1][3] == 1
    view.render_pdf_page(requests[-1], _page(index=1))
    view._set_pdf_zoom(100)
    assert requests[-1][3:] == (1, 3.0)
    view.render_pdf_page(requests[-1], _page(index=1, zoom=3))
    assert str(view._btn_pdf_zoom_in.cget("state")) == "disabled"
    view._set_pdf_zoom(0.01)
    assert requests[-1][4] == 0.25
    view.render_pdf_page(requests[-1], _page(index=1, zoom=0.25))
    assert str(view._btn_pdf_zoom_out.cget("state")) == "disabled"
    view._change_pdf_page(-1)
    assert requests[-1][3] == 0


def test_fast_selection_and_refresh_reject_stale_page_and_error(opened_view):
    _root, view, requests = opened_view
    view.render_cases((_item(), _item("b", 2)))
    request_a = requests[-1]
    view._tree.selection_set("2")
    view._on_select(None)
    request_b = requests[-1]
    assert request_b[1:3] == ("b", 2)
    view.render_pdf_page(request_a, _page())
    view.render_pdf_error(request_a, "stale error")
    assert view._pdf_photo is None
    assert "geladen" in view._lbl_pdf_status.cget("text")
    view.render_pdf_page(request_b, _page("b"))
    assert view._pdf_photo is not None
    view.render_cases((_item(), _item("b", 2)))
    refreshed = requests[-1]
    assert refreshed != request_b and refreshed[1:3] == ("b", 2)
    view.render_pdf_page(request_b, _page("b"))
    assert view._pdf_photo is None
    view.render_pdf_error(refreshed, "Die PDF-Quelle fehlt.")
    assert view._lbl_pdf_status.cget("text") == "Die PDF-Quelle fehlt."
    assert str(view._btn_pdf_next.cget("state")) == "disabled"
    view.render_cases(())
    assert view.pdf_request() is None
    assert view._pdf_photo is None
    assert "Keine offenen" in view._lbl_pdf_status.cget("text")


def test_same_report_different_run_and_hidden_view_reject_inflight_preview(opened_view):
    _root, view, requests = opened_view
    view.render_cases((_item(), _item(run=2)))
    first_run = requests[-1]
    view._tree.selection_set("2")
    view._on_select(None)
    second_run = requests[-1]
    view.render_pdf_page(first_run, _page())
    assert view._pdf_photo is None
    view.suspend_pdf_preview()
    view.render_pdf_page(second_run, _page())
    assert view._pdf_photo is None
    view.resume_pdf_preview()
    assert requests[-1] != second_run
    view.render_pdf_page(requests[-1], _page())
    assert view._pdf_photo is not None


def test_preview_mismatched_payload_fails_visibly(opened_view):
    _root, view, requests = opened_view
    view.render_cases((_item(),))
    view.render_pdf_page(requests[-1], _page("other-report"))
    assert view._pdf_photo is None
    assert "passt nicht" in view._lbl_pdf_status.cget("text")


def test_responsive_halves_and_fit_width_keep_workflow_visible(opened_view):
    root, view, requests = opened_view
    root.geometry("1100x720+0+0")
    view.pack(fill="both", expand=True)
    root.deiconify()
    root.update_idletasks()
    root.update()
    view.render_cases((_item(),))
    image = b"P6\n600 900\n255\n" + b"\xff" * (600 * 900 * 3)
    view.render_pdf_page(requests[-1], ReportPdfPage("a", 0, 3, 1.0, 600, 900, image))
    view._fit_pdf_width()
    assert requests[-1][4] == pytest.approx((view._pdf_canvas.winfo_width() - 18) / 600)
    for size in ("1100x720", "900x640"):
        root.geometry(size)
        root.update_idletasks()
        root.update()
        assert view._split.sashpos(0) == pytest.approx(view._split.winfo_width() / 2, abs=2)
        assert view._pdf_canvas.winfo_ismapped()
        assert view._tree.winfo_ismapped()
        assert view._btn_save.winfo_ismapped()
        assert view._btn_open_pdf.winfo_ismapped()
        assert view._btn_save.winfo_rooty() + view._btn_save.winfo_height() <= root.winfo_rooty() + root.winfo_height()


@pytest.mark.parametrize("width,height,initial_zoom", [(2000, 1000, 1.0), (10000, 10000, 3.0)])
def test_fit_width_renders_wide_or_already_capped_page_inside_canvas(opened_view, tmp_path, width, height, initial_zoom):
    root, view, requests = opened_view
    root.geometry("900x640+0+0")
    view.pack(fill="both", expand=True)
    root.deiconify()
    root.update_idletasks()
    root.update()
    path = tmp_path / "wide.pdf"
    _write_pdf(path, width=width, height=height)
    view.render_cases((_item(),))
    view._set_pdf_zoom(initial_zoom)
    initial = pdf_preview.render_pdf_page("a", str(path), page_index=0, zoom=initial_zoom)
    view.render_pdf_page(requests[-1], initial)
    assert view._pdf_photo is not None
    if width == 10000:
        assert initial.zoom < 0.25
    view._fit_pdf_width()
    request = requests[-1]
    assert 0 < request[4] < 0.25
    fitted = pdf_preview.render_pdf_page("a", str(path), page_index=0, zoom=request[4])
    assert fitted.width <= view._pdf_canvas.winfo_width() - 16
    assert fitted.width * fitted.height <= pdf_preview.MAX_PIXELS
    assert len(fitted.image_data) <= pdf_preview.MAX_IMAGE_BYTES
    view.render_pdf_page(request, fitted)
    assert view._pdf_photo is not None
    assert view._pdf_photo.width() <= view._pdf_canvas.winfo_width() - 16


def test_same_report_shortened_pdf_refresh_starts_from_first_page(opened_view, tmp_path):
    _root, view, requests = opened_view
    path = tmp_path / "changing.pdf"
    _write_pdf(path, width=200, height=300, pages=3)
    item = _item()
    view.render_cases((item,))
    view.render_pdf_page(requests[-1], pdf_preview.render_pdf_page("a", str(path), page_index=0, zoom=1))
    view._change_pdf_page(2)
    view.render_pdf_page(requests[-1], pdf_preview.render_pdf_page("a", str(path), page_index=2, zoom=1))
    assert view._lbl_pdf_page.cget("text") == "Seite 3 / 3"
    _write_pdf(path, width=200, height=300, pages=1)
    view.render_cases((item,))
    request = requests[-1]
    assert view.selected_item() == item
    assert request[3] == 0
    assert view._pdf_page_count == 0
    assert str(view._btn_pdf_previous.cget("state")) == "disabled"
    page = pdf_preview.render_pdf_page("a", str(path), page_index=request[3], zoom=request[4])
    view.render_pdf_page(request, page)
    assert view._lbl_pdf_page.cget("text") == "Seite 1 / 1"
    assert str(view._btn_pdf_previous.cget("state")) == "disabled"
    assert str(view._btn_pdf_next.cget("state")) == "disabled"
    assert view._pdf_photo is not None


class _Runner:
    shutdown = False

    def __init__(self):
        self.active = set()
        self.submissions = []

    def is_active(self, key):
        return key in self.active

    def submit(self, key, work, *, on_success, on_error):
        assert key not in self.active
        self.active.add(key)
        self.submissions.append((key, work, on_success, on_error))
        return True

    def complete(self, *, page=None, error=None):
        key, _work, success, failure = self.submissions[-1]
        self.active.remove(key)
        failure(error) if error is not None else success(page)


def _app(view):
    app = AnalyzerDesktopApp.__new__(AnalyzerDesktopApp)
    app._bootstrapped = True
    app._current_view = "validation"
    app._task_runner = _Runner()
    app._services = SimpleNamespace(results=SimpleNamespace(render_report_pdf_page=lambda report, **kwargs: _page(report, kwargs["page_index"], kwargs["zoom"])))
    app._views = {"validation": view}
    view._on_preview = app._request_validation_pdf
    return app


def test_shell_coalesces_fast_a_to_b_selection_and_navigation(opened_view):
    _root, view, _requests = opened_view
    app = _app(view)
    view.render_cases((_item(), _item("b", 2)))
    view._tree.selection_set("2")
    view._on_select(None)
    assert len(app._task_runner.submissions) == 1
    app._task_runner.complete(page=_page("a"))
    assert view._pdf_photo is None
    assert len(app._task_runner.submissions) == 2
    _key, work, _ok, _error = app._task_runner.submissions[-1]
    assert work().report_id == "b"
    app._task_runner.complete(page=_page("b"))
    assert view._pdf_photo is not None
    view._change_pdf_page(1)
    view._change_pdf_page(1)
    assert len(app._task_runner.submissions) == 3
    app._task_runner.complete(page=_page("b", 1))
    assert view._pdf_photo is None
    assert len(app._task_runner.submissions) == 4
    app._task_runner.complete(page=_page("b", 2))
    assert view._lbl_pdf_page.cget("text") == "Seite 3 / 3"
    assert str(view._btn_pdf_next.cget("state")) == "disabled"


def test_shell_renders_current_process_error_and_ignores_left_view(opened_view):
    _root, view, _requests = opened_view
    app = _app(view)
    view.render_cases((_item(),))
    app._task_runner.complete(error=PdfPreviewError("PDF ist beschaedigt."))
    assert "beschaedigt" in view._lbl_pdf_status.cget("text")
    view.render_cases((_item(),))
    view.suspend_pdf_preview()
    app._current_view = "results"
    app._validation_pdf_pending = None
    app._task_runner.complete(page=_page())
    assert view._pdf_photo is None
    assert len(app._task_runner.submissions) == 2


def test_page_two_timeout_allows_previous_to_recover_without_reselection(opened_view):
    _root, view, _requests = opened_view
    app = _app(view)
    item = _item()
    view.render_cases((item,))
    app._task_runner.complete(page=_page())
    view._change_pdf_page(1)
    app._task_runner.complete(error=PdfPreviewError("Die PDF-Vorschau hat das Zeitlimit ueberschritten."))
    assert view._pdf_photo is None
    assert view._pdf_page_index == 1
    assert view._pdf_page_count == 3
    assert view._lbl_pdf_page.cget("text") == "Seite 2 / 3"
    assert "Zeitlimit" in view._lbl_pdf_status.cget("text")
    assert str(view._btn_pdf_previous.cget("state")) == "normal"
    view._btn_pdf_previous.invoke()
    assert app._task_runner.submissions[-1][1]().page_index == 0
    assert view.selected_item() == item
    app._task_runner.complete(page=_page())
    assert view._pdf_photo is not None
    assert view._lbl_pdf_page.cget("text") == "Seite 1 / 3"
    assert str(view._btn_pdf_previous.cget("state")) == "disabled"


def test_empty_validation_refresh_discards_coalesced_request(opened_view):
    _root, view, _requests = opened_view
    app = _app(view)
    view.render_cases((_item(), _item("b", 2)))
    view._tree.selection_set("2")
    view._on_select(None)
    view.render_cases(())
    app._task_runner.complete(page=_page("a"))
    assert len(app._task_runner.submissions) == 1
    assert view._pdf_photo is None
    assert view.pdf_request() is None


@pytest.mark.parametrize("initial_state", ["normal", "zoomed"])
def test_normal_maximize_restores_previous_window_state_and_geometry(initial_state):
    calls = []
    current_state = [initial_state]

    def state(value=None):
        if value is not None:
            calls.append(("state", value))
            current_state[0] = value
        return current_state[0]

    app = SimpleNamespace(state=state, geometry=lambda value=None: calls.append(("geometry", value)) if value else "1180x760+30+40", attributes=lambda *args: calls.append(("attributes", *args)))
    AnalyzerDesktopApp._maximize_validation_window(app)
    assert current_state[0] == "zoomed"
    assert app._validation_window_restore == (initial_state, "1180x760+30+40")
    AnalyzerDesktopApp._maximize_validation_window(app)
    AnalyzerDesktopApp._restore_validation_window(app)
    assert current_state[0] == initial_state
    assert (("geometry", "1180x760+30+40") in calls) == (initial_state == "normal")
    assert app._validation_window_restore is None
    assert all("fullscreen" not in str(call) and "overrideredirect" not in str(call) for call in calls)


def test_unsupported_maximize_is_fail_safe():
    def unsupported(*args):
        if args:
            raise tk.TclError("unsupported")
        return "normal"

    app = SimpleNamespace(state=unsupported, geometry=lambda *_: "800x600+0+0", attributes=unsupported)
    AnalyzerDesktopApp._maximize_validation_window(app)
    AnalyzerDesktopApp._restore_validation_window(app)
    assert app._validation_window_restore is None
