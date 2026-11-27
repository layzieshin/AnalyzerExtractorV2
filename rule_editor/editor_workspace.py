"""Einstiegspunkt des Visual Rule Editors.

RuleEditorWorkspace haelt den gesamten Zustand (StringVars, Daten, Widget-Refs)
und genau einen RuleSuiteController zentral im __init__. Die Oberflaeche
besteht aus Inventar und Arbeitsbereich; die Funktionalitaet kommt aus
thematischen Mixins im Paket rule_editor/.
"""
from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk
from collections.abc import Callable, Sequence

from interfaces.tk.task_runner import TkTaskRunner
from interfaces.tk.view_models import integrity_summary

from rule_editor.draft_actions import DraftMixin
from rule_editor.field_actions import FieldsMixin
from rule_editor.guide import GuideMixin
from rule_editor.history_actions import HistoryMixin
from rule_editor.manage_actions import ManageMixin
from rule_editor.marking_actions import MarkingsMixin
from rule_editor.meta_actions import MetaMixin
from rule_editor.pdf_text_actions import PdfTextMixin
from rule_editor.regex_actions import RegexMixin
from rule_editor.release_actions import ReleaseMixin
from rule_editor.ui_builder import UiBuilderMixin


class RuleEditorWorkspace(
    UiBuilderMixin,
    GuideMixin,
    HistoryMixin,
    DraftMixin,
    FieldsMixin,
    MetaMixin,
    PdfTextMixin,
    MarkingsMixin,
    RegexMixin,
    ReleaseMixin,
    ManageMixin,
    ttk.Frame,
):
    def __init__(self, master: tk.Misc, project_root: str | Path, *, rules: object,
                 controller_factory: Callable | None = None,
                 initial_inventory: Sequence | None = None, on_close: Callable[[], None] | None = None,
                 embedded: bool = False, on_focus: Callable[[bool], None] | None = None) -> None:
        super().__init__(master, style="Content.TFrame")
        self.project_root = Path(project_root).resolve()
        self._rules = rules
        self._controller_factory = controller_factory
        self._fixed_controller = controller_factory is None
        self._embedded = embedded
        self._on_close = on_close
        self._on_focus = on_focus
        self._closed = False
        self._context_generation = 0
        self._inventory_generation = 0
        self._inventory_after_id = None
        self._inventory_pending = False
        self._inventory_items = ()
        self._proof_generation = 0
        self._proof_result = None
        self._proof_request = None
        self._proof_target = None
        self._proof_origin = None
        self._completion_visible = False
        self._activation_pending = False
        self._text_generation = 0
        self._marking_generation = 0
        self._marking_pending = None
        self._task_runner = TkTaskRunner(self)
        self.current_draft_path: str | None = None
        self.assay_block_text: str = ""

        self.fields_data: list[dict] = []
        self.column_mapping_data: dict[str, str] = {}

        self.var_root = tk.StringVar(master=self, value=str(self.project_root))
        self.var_root.trace_add("write", self._on_var_root_written)
        self.var_assay = tk.StringVar(master=self, value="")
        self.var_new_assay_key = tk.StringVar(master=self, value="")
        self.var_new_assay_name = tk.StringVar(master=self, value="")
        self.var_draft_path = tk.StringVar(master=self, value="")
        self.var_pdf = tk.StringVar(master=self, value="")
        self.var_lot_regex = tk.StringVar(master=self, value="")
        self.var_dedupe_fields = tk.StringVar(master=self, value="")
        self.var_excel_filename = tk.StringVar(master=self, value="{assay_name}.xlsx")
        self.var_sheet_template = tk.StringVar(master=self, value="{lot_id}")

        self.var_field_key = tk.StringVar(master=self, value="")
        self.var_field_regex = tk.StringVar(master=self, value="")
        self.var_field_required = tk.BooleanVar(master=self, value=False)
        self.var_field_excel_column = tk.StringVar(master=self, value="")
        self.var_field_dedupe = tk.BooleanVar(master=self, value=False)
        self.var_search_mode = tk.StringVar(master=self, value="none")
        self.var_search_mode_label = tk.StringVar(master=self, value="Gesamter Assay-Text")
        self.var_search_after = tk.StringVar(master=self, value="")
        self.var_search_line = tk.StringVar(master=self, value="")
        self.var_regex_group = tk.StringVar(master=self, value="1")

        self.var_col_key = tk.StringVar(master=self, value="")
        self.var_col_name = tk.StringVar(master=self, value="")

        self.var_hint = tk.StringVar(master=self, value="Bereit")
        self.var_field_heading = tk.StringVar(master=self, value="Feld bearbeiten")
        self.var_field_caption = tk.StringVar(master=self, value="Feld auswählen oder neu anlegen")
        self.var_field_count = tk.StringVar(master=self, value="0 konfiguriert")
        self.var_inventory_search = tk.StringVar(master=self, value="")

        self.assay_display_to_key: dict[str, str] = {}
        self.known_assay_keys: set[str] = set()
        self._busy = False
        self._suspend_dirty_tracking = False
        self._dirty = False
        self._selected_field_key: str | None = None
        self._field_form_dirty = False
        self._field_form_loading = False
        self._field_form_is_new = False
        self._field_form_return_key: str | None = None
        self._suppress_field_select = False
        self._field_selection_guard = False
        self._field_mutation_guard = False
        self._dialog_guard = False
        self._search_mode_applying = False
        self._undo_stack: list[dict] = []
        self._redo_stack: list[dict] = []
        self.var_autosave = tk.BooleanVar(master=self, value=True)
        self.var_last_autosave = tk.StringVar(master=self, value="-")
        self._autosave_after_id = None
        self._autosave_ms = 45000
        self._guide_window: tk.Toplevel | None = None
        self._guide_idx = 0
        self._guide_title_var: tk.StringVar | None = None
        self._guide_text_widget: tk.Text | None = None
        self.txt_field_preview: tk.Text | None = None
        self.tree_regex_results: ttk.Treeview | None = None
        self._regex_result_data: dict[str, dict[str, object]] = {}
        self._regex_result_counter = 0
        self._marking_panel_visible = False
        self._marking_sync_guard = False
        self._field_marking_data: dict[str, dict[str, object]] = {}
        self._visible_marking_keys: set[str] = set()
        self._visible_marking_keys: set[str] = set()
        self._field_marking_tags: set[str] = set()
        self._active_marking_key: str | None = None
        self.frame_marking_panel: tk.Frame | None = None
        self.tree_marking_legend: ttk.Treeview | None = None
        self.var_marking_status = tk.StringVar(master=self, value="Kein Assay-Text geladen.")
        self.btn_toggle_markings: tk.Button | None = None
        self.var_marking_selection = tk.StringVar(master=self, value="(keine Auswahl)")
        self.tree_rulesets: ttk.Treeview | None = None
        self.inventory_filter_vars = {
            "active": tk.BooleanVar(master=self, value=True),
            "draft": tk.BooleanVar(master=self, value=True),
            "inactive": tk.BooleanVar(master=self, value=True),
            "history": tk.BooleanVar(master=self, value=True),
            "trash": tk.BooleanVar(master=self, value=True),
        }
        self._inventory_by_iid: dict[str, dict[str, object]] = {}
        self.var_field_guidance = tk.StringVar(master=self, value="")

        self._build_ui()
        self._bind_shortcuts()
        if initial_inventory is None:
            self._request_inventory()
        else:
            self.render_inventory(initial_inventory)
        self._install_dirty_watchers()
        self.var_pdf.trace_add("write", self._on_test_choice_changed)
        self.var_draft_path.trace_add("write", self._on_test_choice_changed)
        self.var_inventory_search.trace_add("write", lambda *_: self._render_cached_inventory())
        for variable in (self.var_field_key, self.var_new_assay_name, self.var_new_assay_key):
            variable.trace_add("write", lambda *_: self._render_editor_identity())
        self._schedule_autosave()
        self._sync_authoring_controls()

    def _render_editor_identity(self) -> None:
        """Display existing identity and field metadata; never read the draft."""
        editing = self._active_page == "workspace"
        self.var_workspace_title.set((self.var_new_assay_name.get().strip() or "Entwurf bearbeiten") if editing else "Regelwerke")
        key = self.var_new_assay_key.get().strip()
        self.var_workspace_subtitle.set((f"Entwurf · Hersteller-ID {key}" if key else "Entwurf") if editing else "Regeln erstellen, prüfen und ausdrücklich aktivieren")
        if editing:
            self.rule_breadcrumb.pack(fill="x", before=self.rule_title_row, pady=(0, 6))
            self.lbl_loaded_assay_name.configure(style="RuleWorkplace.Title.TLabel")
            self.btn_inventory_new.grid_remove()
            self.lbl_status.grid_remove()
            self.editor_navigation.grid(row=0, column=1, columnspan=2, sticky="e", padx=(12, 0))
            self.rule_toolbar_eyebrow.pack_forget()
            self.editor_hint.pack_forget()
            if hasattr(self, "rule_root_controls"):
                self.rule_root_controls.pack_forget()
        else:
            self.rule_breadcrumb.pack_forget()
            self.editor_navigation.grid_remove()
            self.btn_inventory_new.grid()
            self.lbl_status.grid()
            self.editor_hint.pack(fill="x", padx=12, pady=(0, 4))
            if hasattr(self, "rule_root_controls"):
                self.rule_root_controls.pack(fill="x", pady=(6, 0))
        hits = sum(bool(row.get("matched")) for row in self._field_marking_data.values())
        self.var_field_count.set(f"{len(self.fields_data)} Felder" + (f" · {hits} Treffer" if self._field_marking_data else ""))
        selected = self.var_field_key.get().strip()
        field = next((field for field in self.fields_data if str(field.get("key")) == selected), None)
        self.var_field_heading.set(f"Feld {self.fields_data.index(field) + 1} von {len(self.fields_data)}" if field is not None else "Feld bearbeiten")
        self.var_field_caption.set(str(field.get("display_label") or field.get("label") or selected) if field is not None else "Feld auswählen oder neu anlegen")

    def _show_authoring_completion(self) -> None:
        self._completion_visible = True
        self._show_rule_results()
        self.editor_functions.grid()
        self._sync_authoring_controls()

    def _leave_editor_for_later(self) -> None:
        if self.prepare_leave():
            self.invalidate_context()
            self._show_page("inventory")

    def _on_var_root_written(self, *_args: object) -> None:
        text = self.var_root.get().strip()
        if not text:
            return
        self._bind_rules_controller(text)

    def _bind_rules_controller(self, root: str | Path) -> None:
        chosen = Path(root)
        resolved = chosen.resolve()
        current = getattr(self, "_rules", None)
        if current is not None and Path(current.project_root) == resolved:
            return
        if getattr(self, "_fixed_controller", False):
            return
        self.project_root = chosen
        self._rules = self._controller_factory(chosen)
        self._context_generation = getattr(self, "_context_generation", 0) + 1

    def _select_tab(self, tab_key: str) -> None:
        if tab_key == "draft":
            self._show_page("inventory")
        elif tab_key in {"meta", "validate", "log"}:
            self._show_advanced(tab_key)
        else:
            self._show_page("workspace")
            self._hide_advanced()
        self._set_active_step_button(tab_key)

    def _set_active_step_button(self, active_key: str) -> None:
        for key, btn in self._step_nav_buttons:
            if key == active_key:
                btn.config(relief=tk.SUNKEN)
            else:
                btn.config(relief=tk.RAISED)

    def _bind_shortcuts(self) -> None:
        self._shortcut_tag = f"RuleEditorWorkspace:{self}"
        self._shortcut_events = {"<Return>": self._on_enter, "<Escape>": lambda _event: self.on_cancel_field_edit(),
                                 "<Control-z>": lambda _event: self.on_undo(), "<Control-y>": lambda _event: self.on_redo()}
        for sequence, callback in self._shortcut_events.items():
            self.bind_class(self._shortcut_tag, sequence, lambda event, action=callback: action(event) or "break")

        def scope(widget):
            tags = widget.bindtags()
            widget.bindtags((tags[0], self._shortcut_tag, *tags[1:]))
            for child in widget.winfo_children():
                scope(child)

        scope(self)

    def _on_enter(self, _event: tk.Event) -> None:
        widget_name = str(self.focus_get())
        field_names = (
            "field_regex",
            "field_key",
            "field_excel",
            "field_search_mode",
            "field_search_after",
            "field_search_line",
        )
        if any(name in widget_name for name in field_names):
            self.on_commit_field_form()
            return
        self.on_test_regex()

    def _set_status(self, text: str) -> None:
        self.lbl_status.config(text=text)

    def _set_hint(self, text: str) -> None:
        self.var_hint.set(text)

    def _log(self, text: str) -> None:
        self.txt_log.insert(tk.END, text + "\n")
        self.txt_log.see(tk.END)

    def _set_busy(self, busy: bool, status: str) -> None:
        self._busy = busy
        self._set_status(status)
        self._sync_authoring_controls()

    def _on_test_choice_changed(self, *_args) -> None:
        self._text_generation += 1
        self._invalidate_authoring_test()
        self._invalidate_local_pdf()
        choice = self.var_pdf.get().strip(), self.var_draft_path.get().strip()
        if choice != getattr(self, "_loaded_text_choice", None):
            self._loaded_text_choice = choice
            self.assay_block_text = ""
            self.txt_block.delete("1.0", tk.END)
            self._clear_field_markings()
            self._refresh_field_grid()
            self._set_field_preview_text("")
        if hasattr(self, "var_pdf_filename"):
            self.var_pdf_filename.set(self.var_pdf.get().replace("\\", "/").rsplit("/", 1)[-1] or "Keine Test-PDF gewählt")

    def invalidate_context(self) -> None:
        self._context_generation += 1
        self._text_generation += 1
        self._invalidate_local_pdf()
        self._invalidate_authoring_test()

    def render_inventory(self, items: Sequence) -> None:
        self._inventory_generation += 1
        self._inventory_pending = False
        if self._inventory_after_id is not None:
            self.after_cancel(self._inventory_after_id)
            self._inventory_after_id = None
        self._inventory_items = tuple(items)
        self._render_cached_inventory()

    def _render_cached_inventory(self) -> None:
        self.btn_inventory_states.configure(text=f"Zustände · {sum(bool(variable.get()) for variable in self.inventory_filter_vars.values())}")
        selected = tuple(self.tree_rulesets.selection())
        DraftMixin._reload_assays(self, items=self._inventory_items)
        ManageMixin._refresh_ruleset_overview(self, items=self._inventory_items)
        retained = tuple(key for key in selected if self.tree_rulesets.exists(key))
        if retained:
            self.tree_rulesets.selection_set(retained)
            self._sync_inventory_primary_button()

    def _reload_assays(self) -> None:
        self._request_inventory()

    def _refresh_ruleset_overview(self) -> None:
        self._request_inventory()

    def _on_inventory_filter_changed(self, _event=None) -> None:
        self._render_cached_inventory()

    def _select_all_inventory_filters(self) -> None:
        for variable in self.inventory_filter_vars.values():
            variable.set(True)
        self._render_cached_inventory()

    def _clear_inventory_filters(self) -> None:
        for variable in self.inventory_filter_vars.values():
            variable.set(True)
        self.var_inventory_search.set("")
        self._render_cached_inventory()

    def _toggle_inventory_states(self) -> None:
        self._inventory_states_open = not self._inventory_states_open
        if self._inventory_states_open:
            self.inventory_state_options.pack(fill="x", pady=(0, 10), before=self.inventory_tree_frame)
        else:
            self.inventory_state_options.pack_forget()

    def _request_inventory(self) -> None:
        if self._closed:
            return
        self._inventory_generation += 1
        self._inventory_pending = True
        if self._inventory_after_id is None:
            self._inventory_after_id = self.after_idle(self._start_inventory_load)

    def _request_inventory_integrity(self) -> None:
        """Keep the existing inventory integrity action in the shared workspace."""
        if self._busy:
            self._set_hint("Eine Prüfung läuft bereits. Bitte kurz warten.")
            return
        rules, context = self._rules, self._context_generation
        self._set_busy(True, "Regelbestand wird geprüft …")

        def finish(report=None, error=None):
            if self._closed:
                return
            self._set_busy(False, "Bereit")
            if rules is self._rules and context == self._context_generation:
                if error is not None:
                    self._set_hint(f"Integritätsprüfung fehlgeschlagen: {error}")
                else:
                    total, failed = integrity_summary(report)
                    self._set_hint(f"Integrität: {failed} von {total} Prüfungen fehlgeschlagen." if failed else f"Integrität: alle {total} Prüfungen bestanden.")

        if not self._task_runner.submit("editor-integrity", rules.validate_rules_integrity,
                on_success=lambda report: finish(report=report), on_error=lambda error: finish(error=error)):
            self._set_busy(False, "Bereit")

    def _start_inventory_load(self) -> None:
        self._inventory_after_id = None
        if self._closed or not self._inventory_pending or self._task_runner.is_active("editor-inventory"):
            return
        self._inventory_pending = False
        generation, context, rules = self._inventory_generation, self._context_generation, self._rules

        def finish(items=None, error=None):
            if not self._closed and rules is self._rules and context == self._context_generation and generation == self._inventory_generation:
                if error is None:
                    self._inventory_items = tuple(items)
                    self._render_cached_inventory()
                else:
                    self._set_hint(f"Inventar konnte nicht geladen werden: {error}")
            if self._inventory_pending and not self._closed:
                self._start_inventory_load()

        self._task_runner.submit("editor-inventory", lambda: rules.list_inventory(kind="all"),
            on_success=lambda items: finish(items=items), on_error=lambda error: finish(error=error))

    def prepare_leave(self, *, closing: bool = False) -> bool:
        if self._activation_pending:
            messagebox.showinfo("Bitte warten", "Die Aktivierung wird abgeschlossen. Bitte kurz warten.", parent=self._dialog_parent())
            return False
        if closing and self._busy:
            messagebox.showinfo("Bitte warten", "Die Prüfung läuft noch. Bitte vor dem Wechsel kurz warten.", parent=self._dialog_parent())
            return False
        if not self._resolve_dirty_field_form():
            return False
        if not self._resolve_pending_meta_changes(save_label="speichern und wechseln", discard_label="verwerfen und wechseln", cancel_label="im Editor bleiben"):
            return False
        if self.current_draft_path and self._dirty:
            # Discard is a real reload, not a hidden still-dirty draft.
            return self.on_load_draft_into_editor(self.current_draft_path) is not False
        return True

    def _on_editor_close(self) -> None:
        if self._closed or not self.prepare_leave(closing=True):
            return
        if self._on_close is not None:
            self._on_close()
        else:
            self.destroy()

    def destroy(self) -> None:
        if getattr(self, "_closed", False):
            return
        self._closed = True
        self._proof_result = None
        self._proof_request = None
        for name in ("_inventory_after_id", "_autosave_after_id"):
            handle = getattr(self, name, None)
            if handle is not None:
                self.after_cancel(handle)
                setattr(self, name, None)
        self._task_runner.shutdown_runner(join_timeout_s=0.2)
        for sequence in self._shortcut_events:
            self.unbind_class(self._shortcut_tag, sequence)
        super().destroy()


