"""HistoryMixin: Dirty-Tracking, Auto-Save, Undo/Redo."""
from __future__ import annotations

from datetime import datetime

from src.rulesuite.api import load_draft, save_draft


class HistoryMixin:
    def _install_dirty_watchers(self) -> None:
        for var in (
            self.var_new_assay_key,
            self.var_new_assay_name,
            self.var_lot_regex,
            self.var_dedupe_fields,
            self.var_excel_filename,
            self.var_sheet_template,
            self.var_field_key,
            self.var_field_regex,
            self.var_search_mode,
            self.var_search_after,
            self.var_search_line,
        ):
            var.trace_add("write", self._on_form_changed)

    def _on_form_changed(self, *_args: object) -> None:
        if self._suspend_dirty_tracking:
            return
        if self.current_draft_path:
            self._dirty = True

    def _schedule_autosave(self) -> None:
        self.after(self._autosave_ms, self._autosave_tick)

    def _autosave_tick(self) -> None:
        try:
            if self.var_autosave.get() and self._dirty and self.current_draft_path and not self._busy:
                self._save_meta_to_draft(push_undo=False)
                ts = datetime.now().strftime("%H:%M:%S")
                self.var_last_autosave.set(ts)
                self._dirty = False
                self._log(f"[AUTOSAVE] Draft gespeichert um {ts}")
        except Exception as e:
            self._log(f"[AUTOSAVE-ERROR] {e}")
        finally:
            self._schedule_autosave()

    def _capture_draft_snapshot(self) -> dict | None:
        if not self.current_draft_path:
            return None
        try:
            return load_draft(self.current_draft_path)
        except Exception:
            return None

    def _push_undo_snapshot(self) -> None:
        snap = self._capture_draft_snapshot()
        if snap is None:
            return
        self._undo_stack.append(snap)
        if len(self._undo_stack) > 50:
            self._undo_stack = self._undo_stack[-50:]
        self._redo_stack.clear()

    def _restore_snapshot(self, snap: dict) -> None:
        if not self.current_draft_path:
            return
        save_draft(self.current_draft_path, snap)
        self._suspend_dirty_tracking = True
        try:
            self._apply_data_to_widgets(snap)
        finally:
            self._suspend_dirty_tracking = False
        self._dirty = False

    def on_undo(self) -> None:
        if not self._undo_stack:
            self._set_hint("Undo-Stack ist leer.")
            return
        current = self._capture_draft_snapshot()
        if current is not None:
            self._redo_stack.append(current)
        snap = self._undo_stack.pop()
        self._restore_snapshot(snap)
        self._set_hint("Undo ausgeführt.")

    def on_redo(self) -> None:
        if not self._redo_stack:
            self._set_hint("Redo-Stack ist leer.")
            return
        current = self._capture_draft_snapshot()
        if current is not None:
            self._undo_stack.append(current)
        snap = self._redo_stack.pop()
        self._restore_snapshot(snap)
        self._set_hint("Redo ausgeführt.")
