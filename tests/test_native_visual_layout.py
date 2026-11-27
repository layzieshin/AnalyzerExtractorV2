from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk
from types import SimpleNamespace

import pytest

from interfaces.tk.desktop_theme import NAV_WIDTH, configure_desktop_theme
from interfaces.tk.view_models import DashboardRecentRow
from interfaces.tk.views.dashboard_view import DashboardView
from interfaces.tk.views.validation_view import ValidationView
from interfaces.tk.widgets.common import Card, OverflowScrollbar, ScrollableFrame, create_scrollable_tree
from src.application.api import ReportFieldValue, ReportPdfPage, ValidationQueueItem


@pytest.fixture
def native_root():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk not available: {exc}")
    root.withdraw()
    scaling = float(root.tk.call("tk", "scaling"))
    configure_desktop_theme(root)
    yield root
    root.tk.call("tk", "scaling", scaling)
    root.destroy()


def _settle(root):
    for _ in range(5):
        root.update_idletasks()
        root.update()


def _descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from _descendants(child)


def test_rounded_card_is_opt_in_decoration_with_real_ttk_controls(native_root):
    root = native_root
    root.geometry("600x300+0+0")
    rounded = Card(root, rounded=True, padding=16)
    rounded.pack(fill="both", expand=True, padx=12, pady=12)
    calls = []
    control = ttk.Button(rounded.body, text="Native action", command=lambda: calls.append(True))
    control.pack(anchor="w")
    root.deiconify()
    _settle(root)
    polygons = rounded._decoration.find_all()
    assert len(polygons) == 2
    assert all(rounded._decoration.type(item) == "polygon" for item in polygons)
    assert rounded._decoration.itemcget(polygons[-1], "smooth") == "true"
    assert rounded.body.winfo_x() >= 12 and rounded.body.winfo_y() >= 12
    assert rounded._decoration.cget("background") == "#f3f6fa"
    control.invoke()
    assert calls == [True]
    square = Card(root)
    assert square._rounded is False and not hasattr(square, "_decoration")


def test_overflow_scrollbars_are_independent_overlays_without_resize_feedback(native_root):
    root = native_root
    root.geometry("720x360+0+0")
    frame, tree = create_scrollable_tree(root, ("a", "b"), ("A", "B"), height=3, autohide=True)
    frame.pack(fill="both", expand=True)
    tree.column("a", width=150, stretch=False)
    tree.column("b", width=150, stretch=False)
    for index in range(2):
        tree.insert("", "end", iid=str(index), values=(index, "value"))
    root.deiconify()
    _settle(root)
    bars = {str(bar.cget("orient")): bar for bar in frame.winfo_children() if isinstance(bar, OverflowScrollbar)}
    size = tree.winfo_width(), tree.winfo_height()
    assert not any(bar.winfo_ismapped() for bar in bars.values())
    for index in range(2, 40):
        tree.insert("", "end", iid=str(index), values=(index, "value"))
    _settle(root)
    assert bars["vertical"].winfo_ismapped() and not bars["horizontal"].winfo_ismapped()
    tree.column("a", width=1100)
    _settle(root)
    assert all(bar.winfo_ismapped() for bar in bars.values())
    assert (tree.winfo_width(), tree.winfo_height()) == size
    assert bars["vertical"].winfo_width() == 8 and bars["horizontal"].winfo_height() == 8
    tree.xview_moveto(1)
    tree.yview_moveto(1)
    assert tree.xview()[0] > 0 and tree.yview()[0] > 0
    assert tree.bind_class("Treeview", "<Key-Down>")
    for key in tree.get_children()[2:]:
        tree.delete(key)
    tree.column("a", width=150)
    _settle(root)
    assert not any(bar.winfo_ismapped() for bar in bars.values())
    for _ in range(4):
        _settle(root)
        assert (tree.winfo_width(), tree.winfo_height()) == size
        assert not any(bar.winfo_ismapped() for bar in bars.values())


def test_main_scrollbar_only_appears_for_real_page_overflow(native_root):
    root = native_root
    root.geometry("700x400+0+0")
    scroller = ScrollableFrame(root, autohide=True)
    scroller.pack(fill="both", expand=True)
    content = ttk.Frame(scroller.body, height=100, width=300)
    content.pack()
    root.deiconify()
    _settle(root)
    assert not scroller._scrollbar.winfo_ismapped()
    width = scroller._canvas.winfo_width()
    content.configure(height=900)
    _settle(root)
    assert scroller._scrollbar.winfo_ismapped()
    assert scroller._canvas.winfo_width() == width
    scroller._canvas.yview_moveto(1)
    assert scroller._canvas.yview()[0] > 0
    content.configure(height=100)
    _settle(root)
    assert not scroller._scrollbar.winfo_ismapped()
    assert scroller._canvas.yview() == (0.0, 1.0)


def test_zero_visible_fraction_is_overflow_not_an_empty_viewport(native_root):
    root = native_root
    root.geometry("300x200+0+0")
    frame = ttk.Frame(root)
    frame.pack(fill="both", expand=True)
    scrollbar = OverflowScrollbar(frame, orient="vertical", command=lambda *_args: None)
    root.deiconify()
    scrollbar.set("0", "0")
    _settle(root)
    assert scrollbar.winfo_ismapped()
    scrollbar.set("0", "1")
    _settle(root)
    assert not scrollbar.winfo_ismapped()


def test_page_reconciliation_is_opt_in_and_does_not_watch_legacy_content(native_root):
    root = native_root
    scroller = ScrollableFrame(root)
    scroller.pack(fill="both", expand=True)
    ttk.Label(scroller.body, text="Legacy content").pack()
    _settle(root)
    assert scroller._auto_layout is False
    assert scroller._content_watchers == set() and scroller._content_refresh_id is None


@pytest.mark.parametrize("width,height,font_scale", [(1420, 930, 1.0), (960, 620, 1.25)])
def test_dashboard_bounded_native_list_has_no_nested_bars_and_keeps_details_and_context(native_root, width, height, font_scale):
    root = native_root
    root.tk.call("tk", "scaling", float(root.tk.call("tk", "scaling")) * font_scale)
    root.geometry(f"{width}x{height}+0+0")
    root.columnconfigure(1, weight=1)
    root.rowconfigure(1, weight=1)
    ttk.Frame(root, width=NAV_WIDTH, style="Nav.TFrame").grid(row=0, column=0, rowspan=2, sticky="ns")
    ttk.Frame(root, height=62, style="Header.TFrame").grid(row=0, column=1, sticky="ew")
    content = ttk.Frame(root, padding=(24, 22, 24, 18), style="Content.TFrame")
    content.grid(row=1, column=1, sticky="nsew")
    calls = []
    view = DashboardView(content, on_pick_and_process_pdfs=lambda: None, on_open_settings=lambda: None,
                         on_refresh=lambda: None, on_open_report=calls.append, on_open_selected_report=lambda: None,
                         on_open_results=lambda: None, on_open_validation=lambda: None)
    view.pack(fill="both", expand=True)
    rows = tuple(DashboardRecentRow(str(index), "Verarbeitung fehlgeschlagen" if index == 0 else "Fertig",
        "ANA_2026-11-26_0814.pdf", "1 Assay · Analyzer 1", "26.11.2026 08:14", "Ordnerimport",
        None if index == 0 else f"report-{index}") for index in range(10))
    view.render_recent_rows(rows)
    root.deiconify()
    _settle(root)
    assert len(view._tree.get_children()) == 5 and int(view._tree.cget("height")) == 5
    assert not any(isinstance(widget, ttk.Scrollbar) for widget in _descendants(view._recent_card))
    assert view._tree.xview() == (0.0, 1.0) and view._tree.yview() == (0.0, 1.0)
    font = tkfont.Font(root, font=ttk.Style(root).lookup("Recent.Treeview", "font"))
    assert font.measure(rows[0].file_name) + 12 <= int(view._tree.column("file", "width"))
    for key in view._tree.get_children():
        assert font.measure(view._tree.set(key, "status")) + 12 <= int(view._tree.column("status", "width"))
        assert view._tree.item(key, "image")
    assert set(view._tree.cget("displaycolumns")) >= {"file", "status", "details"}
    if width == 1420:
        assert set(view._tree.cget("displaycolumns")) >= {"time", "source"}
    else:
        assert "summary" not in tuple(view._tree.cget("displaycolumns"))
    view._tree.selection_set("0")
    view._update_open_result_button()
    assert "Ordnerimport" in view._lbl_recent_meta.cget("text") and rows[0].time_text in view._lbl_recent_meta.cget("text")
    assert rows[0].status in view._lbl_recent_meta.cget("text")
    assert str(view._btn_open_result.cget("state")) == "disabled"
    assert view._tree.set("0", "details") == "–"
    box = view._tree.bbox("1", "details")
    view._open_recent_details(SimpleNamespace(x=box[0] + 4, y=box[1] + 4))
    assert calls == ["report-1"] and view.selected_report_id() == "report-1"
    _settle(root)
    if width == 960:
        assert view._scrollable._scrollbar.winfo_ismapped()
        view._scroll_dashboard(SimpleNamespace(delta=-120))
        assert view._scrollable._canvas.yview()[0] > 0
    else:
        view.render_recent_rows(rows[:1])
        _settle(root)
        assert int(view._tree.cget("height")) == 1
        assert not view._scrollable._scrollbar.winfo_ismapped()


@pytest.mark.parametrize("extra_status", ["Wartet", "Verarbeitung fehlgeschlagen"])
def test_recent_disclosure_preserves_sixth_non_report_import_context_and_real_selection(native_root, extra_status):
    root = native_root
    root.geometry("1100x800+0+0")
    calls = []
    view = DashboardView(root, on_pick_and_process_pdfs=lambda: None, on_open_settings=lambda: None,
                         on_refresh=lambda: None, on_open_report=calls.append, on_open_selected_report=lambda: None,
                         on_open_results=lambda: None, on_open_validation=lambda: None)
    view.pack(fill="both", expand=True)
    rows = tuple(DashboardRecentRow(str(index), "Fertig", f"report-{index}.pdf", "Analyzer 1", "26.11.2026 08:14", "Manuell", f"report-{index}")
                 for index in range(5)) + (
        DashboardRecentRow("extra", extra_status, "sixth-pending-or-failed.pdf", "Felder nicht extrahiert: PC_IST", "26.11.2026 08:10", "Ordnerimport", None),
        DashboardRecentRow("real-extra", "Fertig", "seventh-real-report.pdf", "Analyzer 1", "26.11.2026 08:00", "Manuell", "report-7"),
    )
    view.render_recent_rows(rows)
    root.deiconify()
    _settle(root)
    assert len(view._tree.get_children()) == 5 and view._btn_more_recent.cget("text") == "Weitere Importe"
    view._btn_more_recent.invoke()
    _settle(root)
    assert len(view._tree.get_children()) == 7 and int(view._tree.cget("height")) == 7
    assert view._tree.exists("extra") and view._tree.set("extra", "details") == "–"
    view._tree.selection_set("extra")
    view._update_open_result_button()
    for text in ("sixth-pending-or-failed.pdf", extra_status, "PC_IST", "Ordnerimport", "26.11.2026 08:10"):
        assert text in view._lbl_recent_meta.cget("text")
    assert view.selected_report_id() is None and str(view._btn_open_result.cget("state")) == "disabled"
    view._btn_more_recent.invoke()
    _settle(root)
    assert len(view._tree.get_children()) == 5 and "Auswahl unter Weitere Importe" in view._lbl_recent_meta.cget("text")
    assert extra_status in view._lbl_recent_meta.cget("text") and view.selected_report_id() is None
    view._btn_more_recent.invoke()
    assert view._tree.selection() == ("extra",)
    view._tree.selection_set("real-extra")
    view._update_open_result_button()
    view._handle_open_report(None)
    assert calls == ["report-7"]
    view._btn_more_recent.invoke()
    assert view.selected_report_id() == "report-7" and str(view._btn_open_result.cget("state")) == "normal"
    assert "seventh-real-report.pdf" in view._lbl_recent_meta.cget("text")
    assert not any(isinstance(widget, ttk.Scrollbar) for widget in _descendants(view._recent_card))
    view.render_recent_rows(rows[:5])
    assert view.selected_report_id() is None and view._lbl_recent_meta.winfo_manager() == ""


def _native_validation(root, width=1420, height=930, font_scale=1.0):
    root.tk.call("tk", "scaling", float(root.tk.call("tk", "scaling")) * font_scale)
    root.geometry(f"{width}x{height}+0+0")
    root.columnconfigure(1, weight=1)
    root.rowconfigure(1, weight=1)
    ttk.Frame(root, width=NAV_WIDTH, style="Nav.TFrame").grid(row=0, column=0, rowspan=2, sticky="ns")
    ttk.Frame(root, height=62, style="Header.TFrame").grid(row=0, column=1, sticky="ew")
    content = ttk.Frame(root, padding=(24, 22, 24, 18), style="Content.TFrame")
    content.grid(row=1, column=1, sticky="nsew")
    requests = []
    view = ValidationView(content, on_refresh=lambda: None, on_save=lambda: None, on_open_pdf=lambda: None,
                          on_preview=requests.append, on_reanalyze=lambda: None, on_edit_rules=lambda: None)
    view.pack(fill="both", expand=True)
    fields = (ReportFieldValue("DATUM", "26.11.2026"), ReportFieldValue("PC_IST", "104,2"), ReportFieldValue("custom", "False"),
              ReportFieldValue("MEASURED", "26.11.2026 08:14"))
    first = ValidationQueueItem("a", 1, "ANA_2026-11-26_0814.pdf", "/a.pdf", "ANA", "ANA-2406", "Analyzer 1",
                                "2026-11-26T08:14:00Z", fields, selection_token="original:1", store_path="synthetic.sqlite3", assay_name="ANA Screen IgG")
    second = ValidationQueueItem("b", 2, "MPO_2026-11-26.pdf", "/b.pdf", "MPO", "MPO-2411", "Analyzer 2",
                                 "2026-11-26T08:21:00Z", fields, assay_name="Anti-MPO IgG")
    view.render_cases((first, second))
    root.deiconify()
    _settle(root)
    return view, requests, first, second


def _assert_inside(widget, container):
    assert widget.winfo_ismapped(), str(widget)
    box = widget.winfo_rootx(), widget.winfo_rooty(), widget.winfo_width(), widget.winfo_height()
    outer = container.winfo_rootx(), container.winfo_rooty(), container.winfo_width(), container.winfo_height()
    label = widget.cget("text") if "text" in widget.keys() else str(widget)
    assert box[0] >= outer[0] and box[0] + box[2] <= outer[0] + outer[2], (label, box, outer)
    assert box[1] >= outer[1] and box[1] + box[3] <= outer[1] + outer[3], (label, box, outer)


@pytest.mark.parametrize("width,height,font_scale", [(1420, 930, 1.0), (960, 620, 1.25)])
def test_validation_native_cards_keep_list_toolbar_actions_and_friendly_raw_bound_values(native_root, width, height, font_scale):
    root = native_root
    view, _requests, first, second = _native_validation(root, width, height, font_scale)
    assert not view._focus_mode and view._list_card.winfo_ismapped()
    assert int(view._tree.cget("height")) == 2 and view._tree.yview() == (0.0, 1.0)
    assert view._tree.xview() == (0.0, 1.0)
    assert int(view._tree.column("report", "width")) >= 210
    font = tkfont.Font(root, font=ttk.Style(root).lookup("Treeview", "font"))
    assert font.measure(first.file_name) + 12 <= int(view._tree.column("report", "width"))
    assert view._pdf_card._rounded and view._workflow_card._rounded
    for widget in (view._btn_pdf_previous, view._btn_pdf_next, view._btn_pdf_fit, view._btn_pdf_zoom_in,
                   view._btn_pdf_zoom_out, view._btn_open_pdf):
        _assert_inside(widget, view._pdf_card)
    for widget in (view._btn_save, view._btn_reanalyze, view._btn_edit_rules):
        _assert_inside(widget, view._workflow_card)
    _assert_inside(view._btn_focus, view)
    if width == 1420:
        assert {int(widget.grid_info()["row"]) for widget in (view._pdf_title, view._pdf_navigation, view._pdf_zoom_bar, view._btn_open_pdf)} == {0}
    style = ttk.Style(root)
    assert style.lookup(view._btn_save.cget("style"), "background") == "#175ba4"
    assert style.lookup(view._btn_save.cget("style"), "foreground") == "#ffffff"
    assert view.selected_item() is first and first.fields[1] == ReportFieldValue("PC_IST", "104,2")
    row = next(key for key, raw in view._field_keys_by_row.items() if raw == "PC_IST")
    assert view._fields.set(row, "field") == ("Positiv · IST" if width == 960 else "Positive Kontrolle · IST")
    assert view._fields.set(row, "old") == "104,2"
    unknown = next(key for key, raw in view._field_keys_by_row.items() if raw == "custom")
    assert view._fields.set(unknown, "field") == "custom" and view._fields.set(unknown, "old") == "False"
    view._fields.selection_set(row)
    view._show_selected_field_key()
    assert view._field_metadata_menu.entrycget(0, "label") == "Positive Kontrolle · IST"
    assert view._field_metadata_menu.entrycget(1, "label") == "Feldschlüssel: PC_IST"
    _settle(root)
    _assert_inside(view._tabs, view._workflow_card)
    view._fields.yview_moveto(0)
    _settle(root)
    box = view._fields.bbox(view._fields.get_children()[0])
    assert box and box[1] + box[3] <= view._fields.winfo_height(), (box, view._fields.winfo_height())
    assert view._fields.xview() == (0.0, 1.0)
    assert view._field_label(SimpleNamespace(field_key="private_key", display_label="Konfigurierter Name")) == "Konfigurierter Name"
    assert view._field_label(SimpleNamespace(field_key="MEASURED")) == "Messzeitpunkt"
    assert first.selection_token == "original:1" and first.store_path == "synthetic.sqlite3"


def test_direct_focus_is_one_explicit_intent_and_disclosure_survives_filter_and_refresh(native_root):
    root = native_root
    view, _requests, first, second = _native_validation(root)
    view.begin_direct_loading()
    view.render_cases((first, second), direct_case=first)
    assert view._focus_mode and not view._list_card.winfo_manager()
    view.set_focus_mode(False)
    view._filters["status"].select_values(("Offen",))
    view.render_cases((first, second), direct_case=first)
    _settle(root)
    assert not view._focus_mode and view._list_card.winfo_ismapped()
    view.set_focus_mode(True)
    view.render_cases((first, second), direct_case=first)
    assert view._focus_mode


def test_native_navigation_reopens_worklist_without_changing_case_or_write_actions(native_root):
    from interfaces.tk.test_app import AnalyzerDesktopApp

    root = native_root
    view, _requests, first, _second = _native_validation(root)
    content = view.master
    view.pack_forget()
    content.columnconfigure(0, weight=1)
    content.rowconfigure(0, weight=1)
    dashboard = ttk.Frame(content)
    app = SimpleNamespace(VIEW_KEYS=("dashboard", "validation"), _current_view="dashboard", _views={"dashboard": dashboard, "validation": view},
                          _nav_buttons={}, _maximize_validation_window=lambda: None, _restore_validation_window=lambda: None)
    view.set_focus_mode(True)
    AnalyzerDesktopApp.show_view(app, "validation", refresh=False)
    _settle(root)
    assert view._list_card.winfo_ismapped() and not view._focus_mode
    assert view.selected_item() is first and view._btn_save.cget("text") == "Validierung speichern"
    view.set_focus_mode(True)
    AnalyzerDesktopApp.show_view(app, "dashboard", refresh=False)
    AnalyzerDesktopApp.show_view(app, "validation", refresh=False)
    _settle(root)
    assert not view._focus_mode and view.selected_item() is first


def test_pdf_axes_and_fit_only_show_real_overflow_and_keep_raw_values(native_root):
    root = native_root
    view, requests, first, _second = _native_validation(root)
    view.set_focus_mode(True)
    _settle(root)
    size = view._pdf_canvas.winfo_width(), view._pdf_canvas.winfo_height()
    bars = {str(widget.cget("orient")): widget for widget in view._pdf_canvas.master.winfo_children() if isinstance(widget, OverflowScrollbar)}

    def page(width, height, zoom=1.0):
        return ReportPdfPage(first.report_id, 0, 2, zoom, width, height, b"P6\n" + f"{width} {height}\n255\n".encode() + b"\xff" * width * height * 3)

    view.render_pdf_page(view.pdf_request(), page(100, 100))
    _settle(root)
    size = view._pdf_canvas.winfo_width(), view._pdf_canvas.winfo_height()
    assert view._lbl_pdf_status.winfo_manager() == ""
    assert not any(widget.winfo_ismapped() for widget in bars.values())
    view.render_pdf_page(view.pdf_request(), page(size[0] + 200, 100))
    _settle(root)
    assert bars["horizontal"].winfo_ismapped() and not bars["vertical"].winfo_ismapped()
    view._scroll_pdf(SimpleNamespace(delta=-120), axis="x")
    assert view._pdf_canvas.xview()[0] > 0
    view._fit_pdf_width()
    request = requests[-1]
    fitted_width = int((size[0] + 200) * request[4])
    view.render_pdf_page(request, page(fitted_width, 100, request[4]))
    _settle(root)
    assert not bars["horizontal"].winfo_ismapped()
    view.render_pdf_page(view.pdf_request(), page(100, size[1] + 200, request[4]))
    _settle(root)
    assert bars["vertical"].winfo_ismapped() and not bars["horizontal"].winfo_ismapped()
    view._scroll_pdf(SimpleNamespace(delta=-120))
    assert view._pdf_canvas.yview()[0] > 0
    assert (view._pdf_canvas.winfo_width(), view._pdf_canvas.winfo_height()) == size
    assert view.selected_item().fields == first.fields and view.selected_item().selection_token == "original:1"


def test_initial_pdf_fit_is_once_current_and_does_not_upscale_or_override_manual_zoom(native_root):
    root = native_root
    view, requests, first, second = _native_validation(root)

    def page(width, height=100):
        return ReportPdfPage(first.report_id, 0, 1, 1, width, height, b"P6\n" + f"{width} {height}\n255\n".encode() + b"\xff" * width * height * 3)

    width = view._pdf_canvas.winfo_width()
    original = view.pdf_request()
    view.render_pdf_page(original, page(width + 200))
    assert view._pdf_photo is not None
    _settle(root)
    assert requests[-1] != original and requests[-1][4] == pytest.approx((width - 18) / (width + 200))
    assert first.file_name in view._lbl_pdf_filename.cget("text") and "Revision 0" in view._lbl_pdf_filename.cget("text")
    view.render_pdf_error(view.pdf_request(), "Synthetischer Renderfehler")
    assert first.file_name in view._lbl_pdf_filename.cget("text") and "Revision 0" in view._lbl_pdf_filename.cget("text")

    view.render_cases((second,))
    current = view.pdf_request()
    fitting = ReportPdfPage(second.report_id, 0, 1, 1, 100, 100, b"P6\n100 100\n255\n" + b"\xff" * 30000)
    count = len(requests)
    view.render_pdf_page(current, fitting)
    _settle(root)
    assert len(requests) == count and view.pdf_request() == current

    view.render_cases((first,))
    view.render_pdf_page(view.pdf_request(), page(width + 200))
    view._set_pdf_zoom(1.25)
    manual = view.pdf_request()
    count = len(requests)
    _settle(root)
    assert view.pdf_request() == manual and manual[4] == 1.25 and len(requests) == count


def test_direct_refresh_preserves_disclosed_worklist_and_initial_fit_ignores_changed_case(native_root):
    from interfaces.tk.test_app import AnalyzerDesktopApp

    root = native_root
    view, requests, first, second = _native_validation(root)
    view.begin_direct_loading()
    view.render_cases((first, second), direct_case=first)
    view.set_focus_mode(False)
    captured = []
    app = SimpleNamespace(_require_services=lambda: True, _current_view="validation", _validation_direct_target=("a", 1, "synthetic.sqlite3", "original:1"),
                          _begin_direct_validation=lambda target, **intent: captured.append(intent))
    AnalyzerDesktopApp.refresh_current_view(app)
    assert captured == [{"focus": False}]
    view.begin_direct_loading(focus=False)
    view.render_cases((first, second), direct_case=first)
    _settle(root)
    assert not view._focus_mode and view._list_card.winfo_ismapped()
    width = view._pdf_canvas.winfo_width() + 200
    view.render_pdf_page(view.pdf_request(), ReportPdfPage(first.report_id, 0, 1, 1, width, 100,
        b"P6\n" + f"{width} 100\n255\n".encode() + b"\xff" * width * 100 * 3))
    view.render_cases((second,))
    current, count = view.pdf_request(), len(requests)
    _settle(root)
    assert view.pdf_request() == current and current[1] == second.report_id and len(requests) == count
