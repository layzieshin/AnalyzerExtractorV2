from dataclasses import replace
from types import SimpleNamespace
import tkinter as tk

import pytest

from interfaces.tk import desktop_theme
from interfaces.tk.test_app import AnalyzerDesktopApp
from src.application.api import AssayIdentityCandidateItem, AssayIdentityCaseItem, AssayIdentitySourceItem
from src.application.api import AssayIdentityRetryResult
from interfaces.tk.views.changes_view import ChangesView
from test_desktop_ui_v21 import _fake_services, _make_app_stub


def _item(key="(cc33)", *, second_candidate=False, draft="", retry=False, complete=False):
    candidates = (AssayIdentityCandidateItem("(aa11)", "Eigenes Anzeigeprofil", "1" * 64),)
    if second_candidate:
        candidates += (AssayIdentityCandidateItem("(bb22)", "Anderer bekannter Assay", "2" * 64),)
    return AssayIdentityCaseItem("case-" + key, "db.sqlite3", "token-" + key,
        "ANA Screen IgG", key, "Erledigt" if complete else "Verarbeitung offen" if retry else "Offen", candidates,
        (AssayIdentitySourceItem("source-" + key, "a" * 16, "synthetic.pdf", "ANA_NEU_2026-11-27.pdf", "a" * 64, "D1",
            "Verarbeitet" if complete else "Offen", "Neue Herstellerkennung – bitte zuordnen.", complete, True),),
        draft_path=draft, source_assay_key="(aa11)" if draft else "", can_retry=retry, completed=complete)


def _settle(root):
    for _ in range(6):
        root.update_idletasks()
        root.update()


@pytest.mark.parametrize("width,height,scale", [(1420, 930, 1.0), (960, 620, 1.25)])
def test_changes_native_shell_filter_identity_columns_and_scroll_reachability(tmp_path, monkeypatch, width, height, scale):
    original = desktop_theme.configure_desktop_theme
    before_scaling = []

    def configure(root):
        before_scaling.append(float(root.tk.call("tk", "scaling")))
        root.tk.call("tk", "scaling", before_scaling[-1] * scale)
        original(root)

    monkeypatch.setattr(desktop_theme, "configure_desktop_theme", configure)
    app = None
    try:
        app = AnalyzerDesktopApp(tmp_path, services=_fake_services())
        app.geometry(f"{width}x{height}+0+0")
        app.show_view("changes", refresh=False)
        view = app._views["changes"]
        items = (_item(), _item("(dd44)", complete=True))
        view.render_cases(items, store_path="db.sqlite3")
        _settle(app)
        assert app._nav_buttons["changes"].winfo_ismapped()
        assert tuple(view.tree_cases.get_children()) == tuple(item.case_id for item in items)
        assert view.tree_cases.item(items[0].case_id, "values")[:2] == ("ANA Screen IgG", "(cc33)")
        assert view.tree_cases.item(items[1].case_id, "values")[:2] == ("ANA Screen IgG", "(dd44)")
        assert sum(view.tree_cases.column(key, "width") for key in view.tree_cases.cget("columns")) <= view.tree_cases.winfo_width()
        assert view.tree_cases.xview() == (0.0, 1.0)
        box = view.tree_cases.bbox(items[1].case_id)
        assert box and box[1] + box[3] <= view.tree_cases.winfo_height()
        view.status_filter.select_values(("Erledigt",))
        _settle(app)
        assert tuple(view.tree_cases.get_children()) == (items[1].case_id,)
        view.btn_clear_filters.invoke()
        _settle(app)
        assert not view.status_filter.selected_values and len(view.tree_cases.get_children()) == 2
        view.tree_cases.selection_set(items[0].case_id)
        view._select_case()
        _settle(app)
        assert view.selected_candidate().assay_key == "(aa11)"
        assert str(view.btn_confirm_copy.cget("state")) == "normal"
        view._page._canvas.yview_moveto(1)
        _settle(app)
        top = view._page._canvas.winfo_rooty()
        bottom = top + view._page._canvas.winfo_height()
        for button in (view.btn_confirm_copy, view.btn_confirm_blank):
            assert button.winfo_ismapped() and top <= button.winfo_rooty()
            assert button.winfo_rooty() + button.winfo_height() <= bottom
        if width == 1420:
            assert abs(view._left.winfo_y() - view._right.winfo_y()) <= 1
            assert not view._page._scrollbar.winfo_ismapped()
        else:
            assert view._right.winfo_y() > view._left.winfo_y()
    finally:
        if app is not None:
            app.tk.call("tk", "scaling", before_scaling[0])
            app.destroy()


def test_changes_ambiguous_choice_idempotent_selection_and_store_reset(tmp_path):
    app = AnalyzerDesktopApp(tmp_path, services=_fake_services())
    try:
        app.show_view("changes", refresh=False)
        view = app._views["changes"]
        item = _item(second_candidate=True)
        view.render_cases((item,), store_path="db.sqlite3")
        _settle(app)
        assert view.selected_candidate() is None
        assert str(view.btn_confirm_copy.cget("state")) == "disabled"
        context = view.selection_context()
        view._select_case()
        assert view.selection_context() == context
        view.candidate_combo.current(0)
        assert view.selected_candidate().assay_name == "Eigenes Anzeigeprofil"
        assert view.selection_context() != context
        view.invalidate_store_context()
        assert view.selected_case() is None and not view.tree_cases.get_children()
        assert str(view.btn_retry.cget("state")) == "disabled"
    finally:
        app.destroy()


@pytest.mark.parametrize("view_key", ["results", "settings", "diagnostics", "rules", "validation"])
def test_other_views_never_read_identity_catalogue(view_key):
    app = _make_app_stub(current_view=view_key)
    def forbid(*args, **kwargs):
        raise AssertionError("unrelated menu must not read identity cases")
    app._services.rules.get_identity_case_count = forbid
    app._services.rules.list_identity_case_items = forbid
    payload = app._load_view_payload(view_key)
    assert "identity_cases" not in payload and "identity_open_count" not in payload


def test_dashboard_badge_read_error_is_unknown_not_zero_and_keeps_dashboard_payload():
    app = _make_app_stub(current_view="dashboard")
    app._services.rules.get_identity_case_count = lambda *, store_path: (_ for _ in ()).throw(ValueError("synthetic corrupt catalogue"))
    payload = app._load_view_payload("dashboard")
    assert payload["identity_open_count"] is None and payload["identity_count_error"]
    assert "recent" in payload and "settings" in payload


def _bound_stub(items):
    app = _make_app_stub(current_view="changes")
    app.project_root = "."
    state = {"selected": items[0], "generation": 0, "items": tuple(items), "rendered": [], "opened": [], "confirmed": []}
    def render(items, *, store_path):
        state["items"] = tuple(items)
        state["rendered"].append(tuple(items))
        state["selected"] = next((item for item in items if item.case_id == state["selected"].case_id), None)
    view = SimpleNamespace(selected_case=lambda: state["selected"], selected_source=lambda: state["selected"].sources[0],
        selected_candidate=lambda: state["selected"].candidates[0],
        selection_context=lambda: (state["generation"], state["selected"].case_id),
        set_busy=lambda busy: state.__setitem__("busy", busy), set_feedback=lambda text: state.__setitem__("feedback", text), render_cases=render)
    app._views["changes"] = view
    app._views["rules"] = SimpleNamespace(bind_editor=lambda *_args: None, _identity_context=None,
        open_identity_draft=lambda payload, **intent: state["opened"].append((payload, intent)))
    def show(key, *, refresh=True):
        app._current_view = key
        app._navigation_generation += 1
    app.show_view = show
    app._services.rules.confirm_identity_case = lambda case_id, **intent: state["confirmed"].append((case_id, intent))
    app._services.rules.get_identity_editor_context = lambda case_id, **binding: {"draft_path": "new.draft.json", "draft_data": {}, "test_pdf": "synthetic.pdf"}
    app._services.rules.list_identity_case_items = lambda *, store_path: state["items"]
    return app, view, state


@pytest.mark.parametrize("change", ["selection", "selection_aba", "store_aba"])
def test_identity_handoff_completion_cannot_hijack_another_selection_or_store(change):
    first, second = _item(), _item("(dd44)")
    app, view, state = _bound_stub((first, second))
    app._confirm_identity_case("copy")
    payload = app._task_runner.submissions[0][1]()
    if change == "store_aba":
        app._store_generation += 2
    else:
        state["selected"], state["generation"] = second, 1
        if change == "selection_aba":
            state["selected"], state["generation"] = first, 2
    app._task_runner.invoke_success(result=payload)
    assert state["confirmed"][0][0] == first.case_id
    assert state["confirmed"][0][1]["assay_name"] == "Eigenes Anzeigeprofil"
    assert not state["opened"] and app._current_view == "changes"
    assert view.selected_case().case_id == (first.case_id if change != "selection" else second.case_id)


def test_identity_confirmation_rechecks_modal_selection_before_dispatch():
    first, second = _item(), _item("(dd44)")
    app, view, state = _bound_stub((first, second))
    def confirm(*args, **kwargs):
        state["selected"], state["generation"] = second, 1
        return True
    app._show_confirm_dialog = confirm
    app._confirm_identity_case("blank")
    assert not app._task_runner.submissions and not state["confirmed"]


def test_identity_activation_callback_uses_case_facade_and_returns_actual_state_once():
    first = _item(draft="new.draft.json", retry=True)
    app, view, state = _bound_stub((first,))
    app._current_view = "rules"
    context = {"case_id": first.case_id, "store_path": first.store_path, "identity_token": first.identity_token,
               "assay_key": first.assay_key, "store_generation": app._store_generation}
    app._views["rules"]._identity_context = context
    completed = replace(first, status="Erledigt", completed=True, can_retry=False)
    calls = []
    app._services.rules.retry_identity_case = lambda case_id, **binding: calls.append((case_id, binding)) or AssayIdentityRetryResult(case_id, first.store_path, (completed,))
    app._identity_rule_activated({**context, "draft_path": first.draft_path})
    app._identity_rule_activated({**context, "draft_path": first.draft_path})
    assert len(app._task_runner.submissions) == 1
    app._task_runner.invoke_success()
    assert calls == [(first.case_id, {"store_path": first.store_path, "expected_identity_token": first.identity_token})]
    assert app._current_view == "changes" and state["selected"].completed


def test_old_generic_case_refresh_cannot_repaint_after_case_mutation():
    first = _item()
    app, view, state = _bound_stub((first,))
    app.refresh_current_view()
    old_payload = app._task_runner.submissions[0][1]()
    app._confirm_identity_case("copy")
    payload = app._task_runner.submissions[1][1]()
    payload["identity_cases"] = (replace(first, draft_path="new.draft.json", status="Entwurf"),)
    app._task_runner.invoke_success(index=1, result=payload)
    rendered = list(state["rendered"])
    app._task_runner.invoke_success(index=0, result=old_payload)
    assert state["rendered"] == rendered and rendered[-1][0].status == "Entwurf"


def test_changes_render_same_canonical_store_preserves_selection_despite_windows_case():
    invalidated = []
    stub = SimpleNamespace(_store_path="I:\\Project\\A.sqlite3", _by_id={},
        invalidate_store_context=lambda: invalidated.append(True), status_filter=SimpleNamespace(set_options=lambda _values: None), _apply_filters=lambda: None)
    item = replace(_item(), store_path="i:\\project\\a.sqlite3")
    ChangesView.render_cases(stub, (item,), store_path="i:\\project\\a.sqlite3")
    assert not invalidated and stub._by_id[item.case_id] == item


@pytest.mark.parametrize("action", ["confirm", "pdf"])
def test_changed_selection_before_worker_start_cannot_create_or_open_old_case(action):
    first, second = _item(), _item("(dd44)")
    app, view, state = _bound_stub((first, second))
    opened = []
    app._services.rules.open_identity_pdf = lambda *args, **binding: opened.append((args, binding))
    if action == "confirm":
        app._confirm_identity_case("copy")
    else:
        app._open_identity_pdf()
    state["selected"], state["generation"] = second, 1
    app._task_runner.invoke_success()
    assert not state["confirmed"] and not opened


def test_store_aba_before_retry_worker_dispatch_cannot_write_original_store():
    first = _item(retry=True)
    app, view, state = _bound_stub((first,))
    calls = []
    app._services.rules.retry_identity_case = lambda *args, **kwargs: calls.append((args, kwargs))
    app._retry_identity_case()
    app._store_generation += 2
    app._task_runner.invoke_success()
    assert not calls and not state["rendered"]


def test_case_bound_editor_activation_explains_and_dispatches_followup_once(tmp_path, monkeypatch):
    from test_rule_editor_phase6_layout import _proof_editor, _finish_editor_tasks

    root, editor, rules, draft, pdf = _proof_editor(tmp_path)
    scaling = float(root.tk.call("tk", "scaling"))
    context = {"case_id": "real-case-intent", "assay_key": "(1111)", "draft_path": str(draft)}
    messages, followed = [], []
    try:
        editor._identity_case_context = context
        editor._identity_activation_callback = followed.append
        monkeypatch.setattr("rule_editor.release_actions.messagebox.askyesno", lambda title, text, **kwargs: messages.append(text) or True)
        editor.on_preview()
        _finish_editor_tasks(root, editor)
        editor.on_activate()
        editor.on_activate()
        _finish_editor_tasks(root, editor)
        assert len(messages) == 1 and "ausschließlich die betroffenen PDF-Importaufträge" in messages[0]
        assert "bleiben unter Änderungen offen" in messages[0]
        assert followed == [context]
    finally:
        root.tk.call("tk", "scaling", scaling)
        root.destroy()
