import tkinter as tk
from tkinter import ttk

import pytest

import rule_editor.manage_actions as manage_actions
import rule_editor_main


def test_inventory_filter_includes_inactive_label() -> None:
    assert "Inaktiv" in manage_actions._INVENTORY_FILTER_TO_KIND
    assert manage_actions._INVENTORY_FILTER_TO_KIND["Inaktiv"] == "inactive"


def test_rule_editor_window_exposes_lifecycle_handlers() -> None:
    try:
        app = rule_editor_main.RuleEditorWindow()
    except tk.TclError as exc:
        pytest.skip(f"Tk not available: {exc}")
    try:
        assert hasattr(app, "on_manage_deactivate_selected")
        assert hasattr(app, "on_manage_delete_selected")
        assert app.var_inventory_filter.get() == "Alle"
        assert "Inaktiv" in app.cmb_inventory_filter["values"]
    finally:
        app.destroy()
